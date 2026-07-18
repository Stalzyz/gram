"""Detect e-commerce platform, analytics/pixels, and live chat widgets
from a website's public HTML - simple, well-known signature matching."""
import re

SHOPIFY_SIGNATURES = [
    r"cdn\.shopify\.com",
    r"Shopify\.theme",
    r"shopify-section",
    r"myshopify\.com",
]

WOOCOMMERCE_SIGNATURES = [
    r"woocommerce",
    r"wp-content/plugins/woocommerce",
    r"wc-ajax",
]

GENERIC_ECOMMERCE_SIGNATURES = {
    "BigCommerce": [r"bigcommerce\.com", r"cdn\d*\.bigcommerce\.com"],
    "Magento": [r"Mage\.Cookies", r"/skin/frontend/", r"magento"],
    "Wix Stores": [r"wixstores", r"static\.wixstatic\.com"],
    "Squarespace Commerce": [r"squarespace-commerce", r"static1\.squarespace\.com"],
}

META_PIXEL_SIGNATURES = [r"connect\.facebook\.net/.+/fbevents\.js", r"fbq\('init'"]
GOOGLE_ANALYTICS_SIGNATURES = [r"gtag\('config'", r"googletagmanager\.com/gtag/js", r"UA-\d{4,10}-\d+", r"google-analytics\.com/analytics\.js"]

LIVE_CHAT_SIGNATURES = {
    "Intercom": [r"widget\.intercom\.io"],
    "Tawk.to": [r"embed\.tawk\.to"],
    "Crisp": [r"client\.crisp\.chat"],
    "Drift": [r"js\.driftt\.com"],
    "Zendesk Chat": [r"static\.zdassets\.com", r"zopim"],
    "LiveChat": [r"cdn\.livechatinc\.com"],
    "Tidio": [r"code\.tidio\.co"],
}


def _any_match(html: str, patterns: list) -> bool:
    return any(re.search(p, html, re.IGNORECASE) for p in patterns)


def detect_ecommerce_platform(html: str) -> dict:
    """Returns dict with shopify/woocommerce booleans and a custom-platform label."""
    result = {
        "is_shopify": _any_match(html, SHOPIFY_SIGNATURES),
        "is_woocommerce": _any_match(html, WOOCOMMERCE_SIGNATURES),
        "other_platform": "",
    }
    if not result["is_shopify"] and not result["is_woocommerce"]:
        for name, patterns in GENERIC_ECOMMERCE_SIGNATURES.items():
            if _any_match(html, patterns):
                result["other_platform"] = name
                break
    return result


def detect_meta_pixel(html: str) -> bool:
    return _any_match(html, META_PIXEL_SIGNATURES)


def detect_google_analytics(html: str) -> bool:
    return _any_match(html, GOOGLE_ANALYTICS_SIGNATURES)


def detect_live_chat(html: str) -> str:
    for name, patterns in LIVE_CHAT_SIGNATURES.items():
        if _any_match(html, patterns):
            return name
    return ""


def detect_whatsapp_widget(html: str) -> bool:
    return bool(re.search(r"wa\.me|whatsapp\.com/send|whatsapp-widget", html, re.IGNORECASE))
