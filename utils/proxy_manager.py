"""Proxy rotation for scraping *target businesses' own websites*.

Not used for any call to Instagram/Meta's Graph API.
"""
import itertools
import os


class ProxyManager:
    def __init__(self, proxies=None):
        proxies = proxies or self._from_env()
        self._cycle = itertools.cycle(proxies) if proxies else None

    @staticmethod
    def _from_env():
        raw = os.getenv("WEBSITE_PROXIES", "")
        return [p.strip() for p in raw.split(",") if p.strip()]

    def next(self):
        """Return the next proxy dict for `requests`, or None if none configured."""
        if not self._cycle:
            return None
        proxy_url = next(self._cycle)
        return {"http": proxy_url, "https": proxy_url}

    @property
    def enabled(self):
        return self._cycle is not None
