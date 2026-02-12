"""Voz forum crawler with caching and structured parsing."""

from .cache import PageCache
from .crawler import VozCrawler
from .exceptions import (
    CacheError,
    CacheReadError,
    CacheWriteError,
    CloudflareBlockedError,
    HTTPError,
    NetworkError,
    PageOutOfRangeError,
    PageParsingError,
    ThreadNotFoundError,
    VozCrawlerError,
)
from .graph import (
    GraphStats,
    ReplyEdge,
    build_reply_graph,
    compute_graph_stats,
    edges_to_dataframe,
    extract_reply_edges,
    plot_reply_graph,
)
from .parser import PageData, PostData

__all__ = [
    "VozCrawler",
    "PageCache",
    "PageData",
    "PostData",
    "ReplyEdge",
    "GraphStats",
    "extract_reply_edges",
    "edges_to_dataframe",
    "build_reply_graph",
    "compute_graph_stats",
    "plot_reply_graph",
    "VozCrawlerError",
    "NetworkError",
    "HTTPError",
    "CloudflareBlockedError",
    "PageParsingError",
    "ThreadNotFoundError",
    "PageOutOfRangeError",
    "CacheError",
    "CacheReadError",
    "CacheWriteError",
]


def main() -> None:
    print("Hello from voz-crawler!")
