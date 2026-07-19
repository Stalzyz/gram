import yaml
from scraper.website_scraper import WebsiteScraper

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

scraper = WebsiteScraper(config)
res = scraper.scrape("https://www.crustveganbakery.com/")
print("Scrape Result:", res)
