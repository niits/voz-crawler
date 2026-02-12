"""Custom exceptions for voz-crawler."""


class VozCrawlerError(Exception):
    """Base exception for all voz-crawler errors."""


# === Network / HTTP errors ===


class NetworkError(VozCrawlerError):
    """Failed to reach the server (DNS, timeout, connection reset, etc.)."""


class HTTPError(VozCrawlerError):
    """Server returned a non-2xx status code."""

    def __init__(self, status_code: int, url: str, message: str = "") -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(
            message or f"HTTP {status_code} for {url}"
        )


class CloudflareBlockedError(HTTPError):
    """Cloudflare challenge could not be solved (403 / captcha)."""

    def __init__(self, url: str) -> None:
        super().__init__(status_code=403, url=url, message=f"Cloudflare blocked request to {url}")


# === Content / parsing errors ===


class PageParsingError(VozCrawlerError):
    """The HTML structure was not what the parser expected."""

    def __init__(self, url: str, detail: str = "") -> None:
        self.url = url
        super().__init__(f"Failed to parse page {url}: {detail}")


class ThreadNotFoundError(VozCrawlerError):
    """The thread URL returned 404 or does not exist."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Thread not found: {url}")


class PageOutOfRangeError(VozCrawlerError):
    """Requested page number exceeds the thread's page count."""

    def __init__(self, page: int, max_page: int, url: str) -> None:
        self.page = page
        self.max_page = max_page
        self.url = url
        super().__init__(
            f"Page {page} out of range (thread has {max_page} pages): {url}"
        )


# === Cache errors ===


class CacheError(VozCrawlerError):
    """Something went wrong reading / writing the cache."""


class CacheReadError(CacheError):
    """Failed to read a cached entry."""


class CacheWriteError(CacheError):
    """Failed to write a cache entry."""
