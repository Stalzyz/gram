import os
import tempfile

import pandas as pd
import pytest

from scraper.pipeline import LeadPipeline
from scraper.instagram_client import InstagramAPIError


def build_config(tmp_dir):
    return {
        "pipeline": {
            "workers": 2,
            "min_delay_seconds": 0,
            "max_delay_seconds": 0,
            "max_retries": 1,
            "retry_backoff_base": 1.0,
            "respect_robots_txt": False,
            "request_timeout_seconds": 5,
        },
        "paths": {
            "input_default": "data/input/sample_input.csv",
            "output_dir": os.path.join(tmp_dir, "output"),
            "db_path": os.path.join(tmp_dir, "output", "pipeline.sqlite3"),
            "screenshots_dir": os.path.join(tmp_dir, "output", "screenshots"),
            "log_dir": os.path.join(tmp_dir, "logs"),
        },
        "instagram": {
            "graph_api_base": "https://graph.facebook.com",
            "fields": ["username", "name", "biography", "website",
                       "followers_count", "follows_count", "media_count",
                       "profile_picture_url", "category_name"],
        },
        "website": {
            "fetch_contact_page": False,
            "contact_page_keywords": ["contact"],
            "capture_screenshot": False,
            "screenshot_viewport": {"width": 1280, "height": 800},
            "user_agent": "TestBot/1.0",
        },
    }


@pytest.fixture
def tmp_input_csv():
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "input.csv")
    pd.DataFrame({"username": ["shopstore1", "shopstore2"]}).to_csv(path, index=False)
    return path, tmp_dir


def test_pipeline_success_path(tmp_input_csv, monkeypatch):
    input_csv, tmp_dir = tmp_input_csv
    config = build_config(tmp_dir)
    pipeline = LeadPipeline(config)

    def fake_fetch(self, username):
        return {
            "username": username,
            "name": f"{username} Inc",
            "biography": "We sell things",
            "website": "",
            "followers_count": 1000,
            "follows_count": 10,
            "media_count": 50,
            "profile_picture_url": "https://example.com/pic.jpg",
            "category_name": "Retail",
        }

    monkeypatch.setattr(
        "scraper.instagram_client.InstagramBusinessClient.fetch_business_profile",
        fake_fetch,
    )

    pipeline.run(input_csv=input_csv, workers=2, resume=True)

    stats = pipeline.store.stats()
    assert stats["success"] == 2
    assert stats["failed"] == 0

    results = pipeline.store.all_results()
    usernames = {r["Instagram Username"] for r in results}
    assert usernames == {"shopstore1", "shopstore2"}


def test_pipeline_handles_failures(tmp_input_csv, monkeypatch):
    input_csv, tmp_dir = tmp_input_csv
    config = build_config(tmp_dir)
    pipeline = LeadPipeline(config)

    def fake_fetch_fail(self, username):
        raise InstagramAPIError("account is private or not a business account")

    monkeypatch.setattr(
        "scraper.instagram_client.InstagramBusinessClient.fetch_business_profile",
        fake_fetch_fail,
    )

    pipeline.run(input_csv=input_csv, workers=2, resume=True)

    stats = pipeline.store.stats()
    assert stats["failed"] == 2
    assert stats["success"] == 0


def test_pipeline_resume_skips_completed(tmp_input_csv, monkeypatch):
    input_csv, tmp_dir = tmp_input_csv
    config = build_config(tmp_dir)
    pipeline = LeadPipeline(config)

    calls = []

    def fake_fetch(self, username):
        calls.append(username)
        return {
            "username": username, "name": username, "biography": "", "website": "",
            "followers_count": 1, "follows_count": 1, "media_count": 1,
            "profile_picture_url": "", "category_name": "",
        }

    monkeypatch.setattr(
        "scraper.instagram_client.InstagramBusinessClient.fetch_business_profile",
        fake_fetch,
    )

    pipeline.run(input_csv=input_csv, workers=1, resume=True)
    assert len(calls) == 2

    # Second run with resume=True should not re-call already-succeeded profiles
    pipeline.run(input_csv=input_csv, workers=1, resume=True)
    assert len(calls) == 2  # unchanged


def test_export_produces_csv_and_xlsx(tmp_input_csv, monkeypatch):
    input_csv, tmp_dir = tmp_input_csv
    config = build_config(tmp_dir)
    pipeline = LeadPipeline(config)

    def fake_fetch(self, username):
        return {
            "username": username, "name": username, "biography": "", "website": "",
            "followers_count": 1, "follows_count": 1, "media_count": 1,
            "profile_picture_url": "", "category_name": "",
        }

    monkeypatch.setattr(
        "scraper.instagram_client.InstagramBusinessClient.fetch_business_profile",
        fake_fetch,
    )

    pipeline.run(input_csv=input_csv, workers=1, resume=True)
    summary = pipeline.export(config["paths"]["output_dir"])

    assert os.path.exists(summary["csv"])
    assert os.path.exists(summary["xlsx"])
    assert summary["count"] == 2
