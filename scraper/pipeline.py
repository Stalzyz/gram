"""Orchestrates the full lead-enrichment run:

1. Read input CSV of usernames/profile URLs
2. Seed SQLite progress store (skips profiles already marked 'success' -> resume)
3. Multi-threaded workers pull pending usernames off a queue
4. For each: Graph API lookup -> website scrape -> optional screenshot
5. Save result to SQLite immediately (progress-after-every-profile)
6. Caller can export CSV/XLSX from the SQLite store at any time, including
   mid-run or after a crash.
"""
import os
import queue
import threading
import time
from datetime import datetime, timezone

import pandas as pd

from utils.logger import get_logger
from utils.validators import extract_username, normalize_url
from exporter.db import ResultStore
from scraper.instagram_client import InstagramBusinessClient, InstagramAPIError
from scraper.website_scraper import WebsiteScraper
from scraper.screenshot import capture_homepage_screenshot

logger = get_logger()

class SkipFilterError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(self.reason)

class PipelineStats:
    """In-memory counters the dashboard polls; backed up by the DB stats too."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active_workers = 0
        self.started_at = None
        self.durations = []  # seconds per completed profile, for ETA estimation

    def worker_started(self):
        with self.lock:
            self.active_workers += 1

    def worker_stopped(self):
        with self.lock:
            self.active_workers -= 1

    def record_duration(self, seconds: float):
        with self.lock:
            self.durations.append(seconds)
            if len(self.durations) > 200:
                self.durations.pop(0)

    def avg_duration(self) -> float:
        with self.lock:
            if not self.durations:
                return 0.0
            return sum(self.durations) / len(self.durations)


class LeadPipeline:
    def __init__(self, config: dict):
        self.config = config
        self.store = ResultStore(config["paths"]["db_path"])
        self.ig_client = InstagramBusinessClient(config)
        self.website_scraper = WebsiteScraper(config)
        self.stats = PipelineStats()
        self.screenshots_dir = config["paths"]["screenshots_dir"]
        self.capture_screenshots = config["website"]["capture_screenshot"]

    # ---------------------------------------------------------------- input

    def load_usernames(self, input_csv: str) -> list:
        df = pd.read_csv(input_csv)
        col = df.columns[0]  # accepts 'username' or 'profile_url' as the first column
        usernames = []
        for raw in df[col].dropna().tolist():
            try:
                usernames.append(extract_username(str(raw)))
            except ValueError as exc:
                logger.warning(f"Skipping invalid input row '{raw}': {exc}")
        return usernames

    # ------------------------------------------------------------- per-item

    def _process_one(self, username: str) -> dict:
        profile_url = f"https://www.instagram.com/{username}/"
        row = {
            "Instagram Username": username,
            "Profile URL": profile_url,
            "Last Scraped Date": datetime.now(timezone.utc).isoformat(),
        }

        ig_data = self.ig_client.fetch_business_profile(username)  # raises on failure
        
        followers = ig_data.get("followers_count", 0)
        website = normalize_url(ig_data.get("website", ""))
        
        if getattr(self, "prefs", {}).get("min_followers", 0) > followers:
            raise SkipFilterError("low_followers")
            
        if getattr(self, "prefs", {}).get("require_website", False) and not website:
            raise SkipFilterError("no_website")

        row.update({
            "Profile Name": ig_data.get("name", ""),
            "Business Category": ig_data.get("category_name", ""),
            "Followers": followers,
            "Following": ig_data.get("follows_count", ""),
            "Posts Count": ig_data.get("media_count", ""),
            "Bio": ig_data.get("biography", ""),
            "Website URL": website,
            "External Website": website,
            "Profile Image URL": ig_data.get("profile_picture_url", ""),
            "Verified Account": "unknown",  # not exposed by the Graph API
            "Contact Button Available": "Yes" if website else "No",
        })

        site_result = self.website_scraper.scrape(website) if website else {}
        row.update({
            "Email": site_result.get("email", ""),
            "Phone Number": site_result.get("phone", ""),
            "WhatsApp Number": site_result.get("whatsapp", ""),
            "Address": site_result.get("address", ""),
            "Facebook Page": site_result.get("facebook_page", ""),
            "Ecommerce Platform": (
                "Shopify" if site_result.get("is_shopify") else
                "WooCommerce" if site_result.get("is_woocommerce") else
                site_result.get("other_ecommerce_platform", "")
            ),
            "Meta Pixel Detected": "Yes" if site_result.get("has_meta_pixel") else "No",
            "Google Analytics Detected": "Yes" if site_result.get("has_google_analytics") else "No",
            "Live Chat Widget": site_result.get("live_chat_widget", ""),
        })

        screenshot_path = ""
        if website and self.capture_screenshots and site_result.get("website_reachable"):
            screenshot_path = capture_homepage_screenshot(
                website,
                self.screenshots_dir,
                f"{username}_website.png",
                self.config["website"]["screenshot_viewport"],
            )
        row["Website Screenshot Path"] = screenshot_path
        row["Scrape Status"] = "success"
        row["Scrape Error"] = site_result.get("error", "")
        return row

    # ---------------------------------------------------------------- workers

    def _worker(self, work_queue: "queue.Queue", max_retries: int, user_id: int, campaign: str):
        self.stats.worker_started()
        try:
            while True:
                try:
                    username = work_queue.get_nowait()
                except queue.Empty:
                    return

                started = time.time()
                try:
                    result = self._process_one(username)
                    self.store.mark_success(user_id, campaign, username, result)
                    logger.info(f"Success: [{campaign}] {username}")
                except InstagramAPIError as exc:
                    self.store.mark_failed(user_id, campaign, username, str(exc))
                    logger.error(f"Failed (Instagram API): [{campaign}] {username}: {exc}")
                except SkipFilterError as exc:
                    self.store.mark_skipped(user_id, campaign, username, exc.reason)
                    logger.info(f"Skipped (Filters): [{campaign}] {username}: {exc.reason}")
                except Exception as exc:
                    self.store.mark_failed(user_id, campaign, username, str(exc))
                    logger.error(f"Failed (unexpected): [{campaign}] {username}: {exc}")
                finally:
                    self.stats.record_duration(time.time() - started)
                    work_queue.task_done()
        finally:
            self.stats.worker_stopped()

    def run(self, user_id: int, input_csv: str, workers: int = 4, resume: bool = True, campaign: str = "default"):
        self.prefs = self.store.get_user_preferences(user_id)
        usernames = self.load_usernames(input_csv)
        if not usernames:
            logger.warning("No valid usernames found in input CSV.")
            return

        if not resume:
            self.store.reset_all(user_id, campaign)
        self.store.seed_pending(user_id, campaign, usernames)

        pending = self.store.pending_usernames(user_id, campaign)
        logger.info(
            f"Loaded {len(usernames)} usernames; {len(pending)} pending "
            f"({len(usernames) - len(pending)} already completed - resume={resume})"
        )

        work_queue: "queue.Queue" = queue.Queue()
        for u in pending:
            work_queue.put(u)

        self.stats.started_at = time.time()
        max_retries = self.config["pipeline"]["max_retries"]

        threads = [
            threading.Thread(target=self._worker, args=(work_queue, max_retries, user_id, campaign), daemon=True)
            for _ in range(max(1, workers))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        logger.info("Pipeline run complete.")

    # --------------------------------------------------------------- exports

    def export(self, user_id: int, output_dir: str, campaign: str = "default") -> dict:
        from exporter.csv_exporter import export_csv
        from exporter.excel_exporter import export_excel

        os.makedirs(output_dir, exist_ok=True)
        results = self.store.all_results(user_id, campaign)
        csv_path = export_csv(results, os.path.join(output_dir, "leads.csv"))
        xlsx_path = export_excel(results, os.path.join(output_dir, "leads.xlsx"))
        return {"csv": csv_path, "xlsx": xlsx_path, "count": len(results)}

    def eta_seconds(self, user_id: int, campaign: str = "default") -> float:
        stats = self.store.stats(user_id, campaign)
        avg = self.stats.avg_duration()
        workers = max(1, self.stats.active_workers)
        remaining = stats["pending"]
        if avg == 0 or remaining == 0:
            return 0.0
        return (remaining * avg) / workers
