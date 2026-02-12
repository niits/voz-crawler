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
from .parser import PageData, PostData

__all__ = [
    "VozCrawler",
    "PageCache",
    "PageData",
    "PostData",
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
