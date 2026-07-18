"""Client for Meta's Instagram Graph API - Business Discovery.

This is the sanctioned, ToS-compliant way to read public fields (name, bio,
website, follower/media counts, category) from *other* public Business or
Creator Instagram accounts. It does not touch instagram.com directly and
does not expose private contact-button data (email/phone/whatsapp) -
Instagram simply doesn't return those fields via the API, by design.

Docs: https://developers.facebook.com/docs/instagram-api/guides/business-discovery
"""
import os
import requests

from utils.logger import get_logger
from utils.retry import with_retries

logger = get_logger()


class InstagramAPIError(Exception):
    pass


class RateLimitedError(InstagramAPIError):
    """Raised on Meta rate-limit responses so callers can back off."""


class InstagramBusinessClient:
    def __init__(self, config: dict):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.ig_user_id = os.getenv("META_IG_USER_ID")
        self.api_version = os.getenv(
            "META_GRAPH_API_VERSION", config["instagram"].get("graph_api_version", "v19.0")
        )
        self.base_url = config["instagram"]["graph_api_base"]
        self.fields = config["instagram"]["fields"]

        if not self.access_token or not self.ig_user_id:
            logger.warning(
                "META_ACCESS_TOKEN / META_IG_USER_ID not set - Instagram lookups will fail. "
                "See .env.example."
            )

    @with_retries(max_attempts=3, base_seconds=2.0, exceptions=(RateLimitedError,))
    def fetch_business_profile(self, username: str) -> dict:
        """Look up a single public Business/Creator account by username.

        Returns a dict of the fields configured in config.yaml, or raises
        InstagramAPIError if the account can't be resolved (private, not a
        business/creator account, doesn't exist, etc.).
        """
        if not self.access_token or not self.ig_user_id:
            raise InstagramAPIError("Missing META_ACCESS_TOKEN / META_IG_USER_ID")

        field_list = ",".join(self.fields)
        url = f"{self.base_url}/{self.api_version}/{self.ig_user_id}"
        params = {
            "fields": f"business_discovery.username({username}){{{field_list}}}",
            "access_token": self.access_token,
        }

        resp = requests.get(url, params=params, timeout=15)
        payload = resp.json()

        if resp.status_code == 429 or self._is_rate_limit_error(payload):
            logger.warning(f"Rate limited by Graph API for username={username}")
            raise RateLimitedError(str(payload))

        if resp.status_code != 200 or "error" in payload:
            err = payload.get("error", {})
            raise InstagramAPIError(
                f"Graph API error for '{username}': {err.get('message', payload)}"
            )

        discovery = payload.get("business_discovery")
        if not discovery:
            raise InstagramAPIError(
                f"'{username}' is not a public Business/Creator account, or does not exist"
            )

        return discovery

    @staticmethod
    def _is_rate_limit_error(payload: dict) -> bool:
        err = payload.get("error", {})
        # Meta uses error codes 4 (app rate limit), 17 (user rate limit), 32 (page rate limit)
        return err.get("code") in (4, 17, 32)
