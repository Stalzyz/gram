"""Fetch a business's own public website and run contact/tech extraction on it.

This targets ordinary third-party business websites (not Instagram), so
proxy rotation and randomized delays here are about being a polite, low-impact
crawler - not about evading any platform's bot detection.
"""
import requests
import urllib.parse as urlparse

from utils.logger import get_logger
from utils.rate_limiter import RandomDelay
from utils.retry import with_retries
from utils.proxy_manager import ProxyManager
from scraper import contact_extractor, tech_detector

logger = get_logger()


class RobotsBlocked(Exception):
    pass


def _robots_allow(url: str, user_agent: str) -> bool:
    try:
        from robotexclusionrulesparser import RobotExclusionRulesParser

        parsed = urlparse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        resp = requests.get(robots_url, timeout=8)
        if resp.status_code != 200:
            return True  # no robots.txt / unreachable -> assume allowed
        parser = RobotExclusionRulesParser()
        parser.parse(resp.text)
        return parser.is_allowed(user_agent, url)
    except Exception:
        return True  # fail open - don't block a run over a flaky robots.txt fetch


class WebsiteScraper:
    def __init__(self, config: dict):
        self.config = config["website"]
        self.pipeline_config = config["pipeline"]
        self.delay = RandomDelay(
            self.pipeline_config["min_delay_seconds"],
            self.pipeline_config["max_delay_seconds"],
        )
        self.proxy_manager = ProxyManager()
        self.timeout = self.pipeline_config["request_timeout_seconds"]
        self.user_agent = self.config["user_agent"]
        self.respect_robots = self.pipeline_config["respect_robots_txt"]

    @with_retries(max_attempts=3, base_seconds=2.0, exceptions=(requests.RequestException,))
    def _get(self, url: str) -> requests.Response:
        headers = {"User-Agent": self.user_agent}
        proxies = self.proxy_manager.next()
        resp = requests.get(url, headers=headers, timeout=self.timeout, proxies=proxies)
        resp.raise_for_status()
        return resp

    def _find_contact_page_url(self, homepage_url: str, homepage_html: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(homepage_html, "lxml")
        keywords = self.config["contact_page_keywords"]
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(kw in href for kw in keywords):
                return urlparse.urljoin(homepage_url, a["href"])
        return ""

    def scrape(self, website_url: str) -> dict:
        """Fetch homepage (+ contact page if found) and extract everything."""
        result = {
            "website_reachable": False,
            "email": "",
            "phone": "",
            "whatsapp": "",
            "address": "",
            "facebook_page": "",
            "is_shopify": False,
            "is_woocommerce": False,
            "other_ecommerce_platform": "",
            "has_meta_pixel": False,
            "has_google_analytics": False,
            "live_chat_widget": "",
            "has_whatsapp_widget": False,
            "error": "",
        }

        if not website_url:
            return result

        if self.respect_robots and not _robots_allow(website_url, self.user_agent):
            result["error"] = "Blocked by robots.txt"
            logger.info(f"robots.txt disallows fetching {website_url}; skipping")
            return result

        try:
            self.delay.wait()
            homepage_resp = self._get(website_url)
        except Exception as exc:
            result["error"] = f"Failed to fetch homepage: {exc}"
            logger.error(f"{website_url}: {exc}")
            return result

        result["website_reachable"] = True
        homepage_html = homepage_resp.text
        combined_html = homepage_html

        contact_html = ""
        if self.config.get("fetch_contact_page", True):
            contact_url = self._find_contact_page_url(website_url, homepage_html)
            if contact_url and contact_url.rstrip("/") != website_url.rstrip("/"):
                try:
                    self.delay.wait()
                    contact_resp = self._get(contact_url)
                    contact_html = contact_resp.text
                    combined_html += contact_html
                except Exception as exc:
                    logger.warning(f"Could not fetch contact page {contact_url}: {exc}")

        emails = contact_extractor.extract_emails(combined_html)
        phones = contact_extractor.extract_phone_numbers(combined_html)
        whatsapp_numbers = contact_extractor.extract_whatsapp_numbers(combined_html)
        address = contact_extractor.extract_address(combined_html)
        fb_page = contact_extractor.extract_facebook_page(combined_html)

        ecommerce = tech_detector.detect_ecommerce_platform(combined_html)

        result.update({
            "email": emails[0] if emails else "",
            "phone": phones[0] if phones else "",
            "whatsapp": whatsapp_numbers[0] if whatsapp_numbers else "",
            "address": address,
            "facebook_page": fb_page,
            "is_shopify": ecommerce["is_shopify"],
            "is_woocommerce": ecommerce["is_woocommerce"],
            "other_ecommerce_platform": ecommerce["other_platform"],
            "has_meta_pixel": tech_detector.detect_meta_pixel(combined_html),
            "has_google_analytics": tech_detector.detect_google_analytics(combined_html),
            "live_chat_widget": tech_detector.detect_live_chat(combined_html),
            "has_whatsapp_widget": tech_detector.detect_whatsapp_widget(combined_html),
            "raw_html": combined_html,
        })
        return result
