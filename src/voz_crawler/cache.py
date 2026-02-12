"""Simple disk-based HTML cache for crawled pages."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .exceptions import CacheReadError, CacheWriteError

DEFAULT_CACHE_DIR = Path(".voz_cache")
DEFAULT_TTL = 3600  # 1 hour


class PageCache:
    """File-system cache keyed by URL.

    Each entry is stored as a JSON file containing the HTML and metadata.

    Parameters
    ----------
    cache_dir:
        Directory to store cache files.  Created automatically.
    ttl:
        Time-to-live in seconds.  ``0`` means entries never expire.
    enabled:
        Set to ``False`` to disable caching entirely (reads always miss).
    """

    def __init__(
        self,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        ttl: int = DEFAULT_TTL,
        *,
        enabled: bool = True,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.enabled = enabled

        if self.enabled:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise CacheWriteError(
                    f"Cannot create cache directory {self.cache_dir}: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str) -> str | None:
        """Return cached HTML for *url*, or ``None`` on miss / expired."""
        if not self.enabled:
            return None

        path = self._key_path(url)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise CacheReadError(f"Corrupted cache entry for {url}: {exc}") from exc

        # Check TTL
        if self.ttl > 0:
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at > self.ttl:
                path.unlink(missing_ok=True)
                return None

        return data.get("html")

    def put(self, url: str, html: str) -> None:
        """Store *html* for *url* in the cache."""
        if not self.enabled:
            return

        path = self._key_path(url)
        payload = {
            "url": url,
            "cached_at": time.time(),
            "html": html,
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            raise CacheWriteError(f"Failed to write cache for {url}: {exc}") from exc

    def invalidate(self, url: str) -> bool:
        """Remove a single cache entry.  Returns ``True`` if it existed."""
        path = self._key_path(url)
        if path.exists():
            path.unlink(missing_ok=True)
            return True
        return False

    def clear(self) -> int:
        """Remove **all** cache entries.  Returns the number of files deleted."""
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _key_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{digest}.json"
