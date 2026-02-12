"""High-level crawler for Voz forum threads."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import cloudscraper
import pandas as pd
from requests.exceptions import ConnectionError, RequestException, Timeout

from .cache import DEFAULT_CACHE_DIR, DEFAULT_TTL, PageCache
from .exceptions import (
    CloudflareBlockedError,
    HTTPError,
    NetworkError,
    PageOutOfRangeError,
    PageParsingError,
    ThreadNotFoundError,
)
from .parser import PageData, PostData, parse_thread_page

logger = logging.getLogger(__name__)

BASE_URL = "https://voz.vn"
_THREAD_URL_RE = re.compile(
    r"^https?://voz\.vn/t/[\w%-]+\.(\d+)/?",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_page_url(thread_url: str, page: int) -> str:
    """Append ``/page-N`` to a base thread URL (strip existing page suffix)."""
    # Normalise: remove trailing slash, remove existing /page-N
    url = re.sub(r"/page-\d+/?$", "", thread_url.rstrip("/"))
    if page <= 1:
        return url + "/"
    return f"{url}/page-{page}"


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class VozCrawler:
    """Crawl a Voz thread, one page at a time, with caching.

    Parameters
    ----------
    cache_dir:
        Where to store cached HTML.  Defaults to ``.voz_cache``.
    cache_ttl:
        Cache time-to-live in seconds.  ``0`` = never expires.
    cache_enabled:
        Set ``False`` to skip caching entirely.
    delay:
        Seconds to sleep between HTTP requests (politeness).
    """

    def __init__(
        self,
        *,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        cache_ttl: int = DEFAULT_TTL,
        cache_enabled: bool = True,
        delay: float = 1.0,
    ) -> None:
        self._scraper = cloudscraper.create_scraper()
        self._cache = PageCache(
            cache_dir=cache_dir, ttl=cache_ttl, enabled=cache_enabled
        )
        self.delay = delay
        self._last_request_at: float = 0.0

    # ------------------------------------------------------------------
    # Low-level fetch
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Sleep if needed to respect ``self.delay``."""
        if self.delay <= 0:
            return
        elapsed = time.time() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
        """Fetch the raw HTML for *url*, using cache when available.

        Raises
        ------
        ThreadNotFoundError
            If the server returns 404.
        CloudflareBlockedError
            If Cloudflare blocks the request (403).
        HTTPError
            For any other non-2xx status.
        NetworkError
            For connection / timeout / DNS failures.
        """
        # Try cache first
        if use_cache:
            cached = self._cache.get(url)
            if cached is not None:
                logger.debug("Cache HIT for %s", url)
                return cached

        # Fetch from network
        self._throttle()
        try:
            response = self._scraper.get(url, timeout=30)
            self._last_request_at = time.time()
        except (Timeout, ConnectionError) as exc:
            raise NetworkError(f"Connection failed for {url}: {exc}") from exc
        except RequestException as exc:
            raise NetworkError(f"Request error for {url}: {exc}") from exc

        # Handle status codes
        if response.status_code == 404:
            raise ThreadNotFoundError(url)
        if response.status_code == 403:
            raise CloudflareBlockedError(url)
        if response.status_code >= 400:
            raise HTTPError(response.status_code, url)

        html = response.text
        self._cache.put(url, html)
        return html

    # ------------------------------------------------------------------
    # Page-level crawling
    # ------------------------------------------------------------------

    def crawl_page(self, thread_url: str, page: int = 1) -> PageData:
        """Crawl a single page of a thread.

        Parameters
        ----------
        thread_url:
            Base thread URL (without ``/page-N``).
        page:
            1-based page number.

        Returns
        -------
        PageData
            Parsed page with posts and pagination info.

        Raises
        ------
        PageOutOfRangeError
            If *page* exceeds the thread's page count.
        """
        url = _build_page_url(thread_url, page)
        html = self.fetch_html(url)
        page_data = parse_thread_page(html, thread_url=url)

        # Validate page range — Voz silently redirects to last page if
        # the requested page is too high, so we compare:
        if page > page_data.total_pages:
            raise PageOutOfRangeError(page, page_data.total_pages, thread_url)

        return page_data

    def crawl_pages(
        self,
        thread_url: str,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> list[PageData]:
        """Crawl a range of pages and return them as a list.

        Parameters
        ----------
        thread_url:
            Base thread URL.
        start_page:
            First page to crawl (1-based, default 1).
        end_page:
            Last page to crawl (inclusive).  ``None`` = crawl to the end.

        Returns
        -------
        list[PageData]
            One entry per successfully crawled page.
        """
        # Discover total pages from the first request
        first = self.crawl_page(thread_url, start_page)
        results: list[PageData] = [first]

        last = end_page if end_page is not None else first.total_pages
        if last > first.total_pages:
            last = first.total_pages

        for p in range(start_page + 1, last + 1):
            page_data = self.crawl_page(thread_url, p)
            results.append(page_data)

        return results

    # ------------------------------------------------------------------
    # Convenience: all posts → DataFrame
    # ------------------------------------------------------------------

    @staticmethod
    def pages_to_dataframe(pages: list[PageData]) -> pd.DataFrame:
        """Flatten a list of `PageData` into a single DataFrame."""
        from dataclasses import asdict

        records = []
        for page in pages:
            for post in page.posts:
                row = asdict(post)
                row["page"] = page.current_page
                records.append(row)

        df = pd.DataFrame(records)
        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df["image_count"] = df["images"].apply(len)
            df["link_count"] = df["links"].apply(len)
        return df

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> int:
        """Remove all cached entries.  Returns count of deleted files."""
        return self._cache.clear()

    def invalidate_page(self, thread_url: str, page: int = 1) -> bool:
        """Invalidate the cache for a specific page."""
        url = _build_page_url(thread_url, page)
        return self._cache.invalidate(url)
