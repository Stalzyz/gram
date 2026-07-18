"""Input parsing / validation helpers."""
import re

_USERNAME_FROM_URL_RE = re.compile(
    r"instagram\.com/([A-Za-z0-9_.]+)/?", re.IGNORECASE
)


def extract_username(value: str) -> str:
    """Accepts either a bare username or a full instagram.com URL and
    returns the bare username."""
    value = value.strip()
    if not value:
        raise ValueError("Empty username/URL value")

    match = _USERNAME_FROM_URL_RE.search(value)
    if match:
        username = match.group(1)
    else:
        username = value.lstrip("@")

    # Basic sanity check on Instagram username character set
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", username):
        raise ValueError(f"'{value}' does not look like a valid Instagram username")

    return username


def normalize_url(url: str) -> str:
    """Ensure a URL has a scheme; return '' if input is empty/invalid."""
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url
