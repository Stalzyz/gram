#!/usr/bin/env python3
"""CLI entrypoint for the Instagram business lead enrichment pipeline."""
import argparse
import sys

import yaml
from dotenv import load_dotenv

from scraper.pipeline import LeadPipeline
from utils.logger import get_logger

load_dotenv()
logger = get_logger()


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Instagram business lead enrichment pipeline")
    parser.add_argument("--input", default=None, help="Path to input CSV of usernames/profile URLs")
    parser.add_argument("--workers", type=int, default=None, help="Number of concurrent workers")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--resume", dest="resume", action="store_true", default=True,
                         help="Resume from last successful profile (default)")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                         help="Ignore prior progress and start fresh")
    parser.add_argument("--export-only", action="store_true",
                         help="Skip scraping; just export current DB contents to CSV/XLSX")
    args = parser.parse_args()

    config = load_config(args.config)
    pipeline = LeadPipeline(config)

    if args.export_only:
        summary = pipeline.export(config["paths"]["output_dir"])
        logger.info(f"Exported {summary['count']} results -> {summary['csv']}, {summary['xlsx']}")
        return

    input_csv = args.input or config["paths"]["input_default"]
    workers = args.workers or config["pipeline"]["workers"]

    try:
        # CLI execution runs as system/admin user (user_id=1)
        pipeline.run(user_id=1, input_csv=input_csv, workers=workers, resume=args.resume)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user - progress up to the last completed profile is saved. "
                        "Re-run with --resume to continue.")
        sys.exit(130)

    summary = pipeline.export(config["paths"]["output_dir"])
    logger.info(f"Exported {summary['count']} results -> {summary['csv']}, {summary['xlsx']}")


if __name__ == "__main__":
    main()
