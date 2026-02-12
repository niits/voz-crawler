"""Reply graph construction and visualization for Voz threads."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import networkx as nx
import pandas as pd


_QUOTE_RE = re.compile(r'<quote\s+author="([^"]+)"(?:\s+post_id="(\d+)")?>')


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReplyEdge:
    """A single reply relationship between two posts."""

    from_post_id: str
    from_username: str
    to_post_id: str
    to_username: str


@dataclass
class GraphStats:
    """Summary statistics for a reply graph."""

    num_nodes: int
    num_edges: int
    top_quoted_posts: list[tuple[str, str, int]]  # (post_id, username, count)
    top_quoted_users: list[tuple[str, int]]  # (username, total_count)
    top_repliers: list[tuple[str, int]]  # (username, total_count)


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------


def extract_reply_edges(
    df: pd.DataFrame,
    *,
    exclude_self_quotes: bool = True,
) -> list[ReplyEdge]:
    """Extract reply edges from a posts DataFrame by parsing ``<quote>`` tags.

    Parameters
    ----------
    df:
        DataFrame produced by :meth:`VozCrawler.pages_to_dataframe`.
    exclude_self_quotes:
        If ``True`` (default), skip quotes where the author quotes themselves.

    Returns
    -------
    list[ReplyEdge]
        Directed edges from the replying post to the quoted post.
    """
    post_user_map: dict[str, str] = {}
    for _, row in df.iterrows():
        post_user_map[str(row["post_id"])] = row["username"]

    edges: list[ReplyEdge] = []
    for _, row in df.iterrows():
        quotes = _QUOTE_RE.findall(row["content_text"])
        for quoted_author, quoted_post_id in quotes:
            if exclude_self_quotes and quoted_author == row["username"]:
                continue
            if quoted_post_id and quoted_post_id in post_user_map:
                edges.append(
                    ReplyEdge(
                        from_post_id=str(row["post_id"]),
                        from_username=row["username"],
                        to_post_id=quoted_post_id,
                        to_username=quoted_author,
                    )
                )
    return edges


def edges_to_dataframe(edges: list[ReplyEdge]) -> pd.DataFrame:
    """Convert a list of :class:`ReplyEdge` to a DataFrame."""
    from dataclasses import asdict

    return pd.DataFrame([asdict(e) for e in edges])


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_reply_graph(
    df: pd.DataFrame,
    edges: list[ReplyEdge],
) -> nx.DiGraph:
    """Build a directed graph where nodes are posts and edges are replies.

    Parameters
    ----------
    df:
        Posts DataFrame (from :meth:`VozCrawler.pages_to_dataframe`).
    edges:
        Reply edges (from :func:`extract_reply_edges`).

    Returns
    -------
    nx.DiGraph
        Graph with post IDs as nodes.  Each node has ``username`` and
        ``page`` attributes.  Each edge represents a quote/reply.
    """
    G = nx.DiGraph()

    for _, row in df.iterrows():
        pid = str(row["post_id"])
        G.add_node(pid, username=row["username"], page=int(row["page"]))

    for edge in edges:
        if G.has_node(edge.from_post_id) and G.has_node(edge.to_post_id):
            G.add_edge(edge.from_post_id, edge.to_post_id)

    return G


def compute_graph_stats(G: nx.DiGraph, *, top_n: int = 10) -> GraphStats:
    """Compute summary statistics for a reply graph.

    Parameters
    ----------
    G:
        Directed graph from :func:`build_reply_graph`.
    top_n:
        Number of top entries to include in each ranking.
    """
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # Top quoted posts
    sorted_posts = sorted(in_deg.items(), key=lambda x: x[1], reverse=True)
    top_quoted_posts = [
        (pid, G.nodes[pid].get("username", "?"), cnt)
        for pid, cnt in sorted_posts[:top_n]
        if cnt > 0
    ]

    # Aggregate by user
    user_quoted: Counter[str] = Counter()
    user_replies: Counter[str] = Counter()
    for pid, cnt in in_deg.items():
        user_quoted[G.nodes[pid].get("username", "?")] += cnt
    for pid, cnt in out_deg.items():
        user_replies[G.nodes[pid].get("username", "?")] += cnt

    return GraphStats(
        num_nodes=G.number_of_nodes(),
        num_edges=G.number_of_edges(),
        top_quoted_posts=top_quoted_posts,
        top_quoted_users=user_quoted.most_common(top_n),
        top_repliers=user_replies.most_common(top_n),
    )


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def plot_reply_graph(
    G: nx.DiGraph,
    *,
    figsize: tuple[int, int] = (22, 22),
    title: str = "Reply Graph (Post-level)",
    min_degree_label: int = 2,
    top_n_legend: int = 15,
    seed: int = 42,
) -> None:
    """Plot the reply graph with matplotlib.

    Parameters
    ----------
    G:
        Directed graph from :func:`build_reply_graph`.
    figsize:
        Figure size.
    title:
        Plot title.
    min_degree_label:
        Minimum in-degree to show a label on the node.
    top_n_legend:
        Number of top users to show in the legend.
    seed:
        Random seed for the spring layout.
    """
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    matplotlib.rcParams["font.family"] = ["Arial Unicode MS", "sans-serif"]

    # Remove isolated nodes for cleaner visualisation
    nodes_with_edges = set()
    for u, v in G.edges():
        nodes_with_edges.add(u)
        nodes_with_edges.add(v)
    H = G.subgraph(nodes_with_edges).copy()

    if H.number_of_nodes() == 0:
        print("No reply edges to visualise.")
        return

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(title, fontsize=18, fontweight="bold", pad=20)

    # Colour by user
    usernames = sorted(set(nx.get_node_attributes(H, "username").values()))
    user_color_map = {u: i for i, u in enumerate(usernames)}
    cmap = plt.cm.tab20
    node_colors = [
        cmap(user_color_map[H.nodes[n]["username"]] % 20) for n in H.nodes()
    ]

    # Size by in-degree
    in_deg = dict(H.in_degree())
    node_sizes = [in_deg[n] * 200 + 80 for n in H.nodes()]

    # Layout
    pos = nx.spring_layout(H, k=1.8, iterations=80, seed=seed)

    # Edges
    nx.draw_networkx_edges(
        H,
        pos,
        ax=ax,
        alpha=0.25,
        edge_color="gray",
        arrows=True,
        arrowsize=10,
        connectionstyle="arc3,rad=0.1",
        width=0.8,
    )

    # Nodes
    nx.draw_networkx_nodes(
        H,
        pos,
        ax=ax,
        node_size=node_sizes,
        node_color=node_colors,
        alpha=0.85,
        edgecolors="white",
        linewidths=1.0,
    )

    # Labels
    labels: dict[str, str] = {}
    for n in H.nodes():
        if in_deg[n] >= min_degree_label:
            labels[n] = f"{H.nodes[n]['username']}\n#{n}"
        elif in_deg[n] >= 1:
            labels[n] = f"#{n}"
    nx.draw_networkx_labels(
        H, pos, labels=labels, ax=ax, font_size=6, font_weight="bold"
    )

    # Legend – aggregate quotes per user
    user_quoted: Counter[str] = Counter()
    for pid in H.nodes():
        user_quoted[H.nodes[pid]["username"]] += in_deg[pid]
    legend_elements = []
    for user, cnt in user_quoted.most_common(top_n_legend):
        if user in user_color_map:
            color = cmap(user_color_map[user] % 20)
            legend_elements.append(
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    color="w",
                    markerfacecolor=color,
                    markersize=8,
                    label=f"{user} ({cnt})",
                )
            )
    if legend_elements:
        ax.legend(
            handles=legend_elements,
            loc="upper left",
            title="Top users (quotes)",
            fontsize=7,
            title_fontsize=9,
        )

    ax.axis("off")
    plt.tight_layout()
    plt.show()
