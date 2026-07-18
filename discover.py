import argparse
import os
import csv
from scraper.discovery_dorks import DorkScraper
from utils.logger import get_logger

logger = get_logger()

def main():
    parser = argparse.ArgumentParser(description="Discover Instagram leads via Search Engine Dorks.")
    parser.add_argument("--query", type=str, required=True, help="Target keyword (e.g., 'clothing brand')")
    parser.add_argument("--platform", type=str, default="", help="Optional e-commerce platform filter (e.g., 'myshopify.com')")
    parser.add_argument("--limit", type=int, default=50, help="Number of usernames to discover")
    parser.add_argument("--output", type=str, default="data/input/discovered_leads.csv", help="Output CSV path")
    args = parser.parse_args()

    scraper = DorkScraper()
    
    logger.info(f"Starting discovery for '{args.query}' (Platform: {args.platform or 'Any'}) - Limit: {args.limit}")
    
    usernames = scraper.discover_leads(keyword=args.query, platform=args.platform, limit=args.limit)
    
    if not usernames:
        logger.warning("No usernames discovered. Search engines might be blocking the requests, or the query is too niche.")
        return
        
    logger.info(f"Discovered {len(usernames)} unique usernames. Saving to {args.output}...")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Write to CSV
    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['username'])
        for username in usernames:
            writer.writerow([username])
            
    logger.info(f"Success! You can now run the pipeline: python main.py --input {args.output}")

if __name__ == "__main__":
    main()
