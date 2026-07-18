"""Extract publicly listed contact details from a business's own website."""
import re
import phonenumbers
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
WHATSAPP_LINK_RE = re.compile(
    r"(?:https?://)?(?:api\.)?(?:wa\.me|whatsapp\.com/send)\S*", re.IGNORECASE
)

# Common footer/header labels that precede a street address
ADDRESS_HINT_TAGS = ["address"]
ADDRESS_HINT_CLASSES = ["address", "location", "footer-address", "store-address"]

# Emails to ignore - obvious placeholders/tracking pixels/etc.
JUNK_EMAIL_SUBSTRINGS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com")


def extract_emails(html: str, default_region: str = None) -> list:
    soup = BeautifulSoup(html, "lxml")
    text_candidates = set()

    # mailto: links first - most reliable
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("mailto:"):
            addr = a["href"].split(":", 1)[1].split("?")[0].strip()
            if addr:
                text_candidates.add(addr)

    # fallback: regex over visible text
    visible_text = soup.get_text(separator=" ")
    for match in EMAIL_RE.findall(visible_text):
        text_candidates.add(match)

    cleaned = [
        e for e in text_candidates
        if not any(junk in e.lower() for junk in JUNK_EMAIL_SUBSTRINGS)
    ]
    return sorted(cleaned)


def extract_phone_numbers(html: str, default_region: str = "US") -> list:
    soup = BeautifulSoup(html, "lxml")
    found = set()

    # tel: links first
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            found.add(a["href"].split(":", 1)[1].strip())

    visible_text = soup.get_text(separator=" ")
    try:
        for match in phonenumbers.PhoneNumberMatcher(visible_text, default_region):
            found.add(phonenumbers.format_number(
                match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            ))
    except Exception:
        pass  # phonenumbers can be picky about malformed input; don't crash the pipeline

    return sorted(found)


def extract_whatsapp_numbers(html: str) -> list:
    """Look for wa.me / whatsapp click-to-chat links and pull the number out."""
    links = set(WHATSAPP_LINK_RE.findall(html))
    numbers = set()
    for link in links:
        digits = re.search(r"(?:wa\.me/|phone=)(\d{6,15})", link)
        if digits:
            numbers.add("+" + digits.group(1))
        else:
            numbers.add(link)  # keep the raw link if we can't parse a number out
    return sorted(numbers)


def extract_address(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag_name in ADDRESS_HINT_TAGS:
        tag = soup.find(tag_name)
        if tag and tag.get_text(strip=True):
            return " ".join(tag.get_text(separator=" ").split())

    for cls in ADDRESS_HINT_CLASSES:
        tag = soup.find(attrs={"class": re.compile(cls, re.IGNORECASE)})
        if tag and tag.get_text(strip=True):
            return " ".join(tag.get_text(separator=" ").split())

    return ""


def extract_facebook_page(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "facebook.com" in href.lower() and "sharer" not in href.lower():
            return href
    return ""
