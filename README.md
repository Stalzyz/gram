# Instagram Business Lead Enrichment Pipeline

## What this is (and isn't)

This project pulls **public business-profile data from Instagram's official Graph API**
(Business Discovery), then **enriches each lead by scraping the business's own public
website** (a normal website, not Instagram) for contact details, e-commerce platform,
tracking pixels, and live chat widgets.

It deliberately does **not**:
- Automate a browser against instagram.com to scrape profile pages
- Rotate proxies or randomize delays *against Instagram* to avoid rate limiting / detection
- Attempt to read the private "Email/Call/WhatsApp" contact-button fields, which
  Instagram does not expose even via its API
- Bypass logins, CAPTCHAs, or any authentication/anti-bot mechanism

Why: Instagram's Terms of Service prohibit automated scraping of the site regardless of
whether the fields are publicly visible, and building retry/proxy-rotation logic aimed at
Instagram specifically is designed to evade its rate limits and bot detection — i.e. its
access controls — even when the underlying data is "public." The Graph API is Meta's
sanctioned, ToS-compliant path to the same public business-profile fields (name, bio,
website, follower/media counts, category), so that's what this pipeline uses for the
Instagram side. Everything below the Instagram layer (the business's own website) is a
plain public site with no comparable platform restriction, so that part can be scraped
directly and thoroughly.

## What you get

| Field | Source |
|---|---|
| Username, Name, Category, Bio, Website, Followers, Following, Media count, Profile picture URL | Instagram Graph API (Business Discovery) |
| Verified status | Not exposed by the Graph API — recorded as `unknown` |
| Email / Phone / WhatsApp number | Parsed from the linked website (home + contact page) |
| Facebook Page link | Parsed from the linked website's footer/social links |
| Shopify / WooCommerce / custom store detection | Parsed from website HTML/headers |
| Meta Pixel / Google Analytics detection | Parsed from website `<script>` tags |
| Live chat widget detection | Parsed from website HTML (Intercom, Tawk.to, Crisp, Drift, Zendesk, etc.) |
| Website homepage screenshot | Playwright, against the business's own site |
| Instagram profile screenshot | **Not included** — would require automating instagram.com itself |

## Requirements

1. A Meta Developer App with **Instagram Graph API** access.
2. A Facebook Page connected to an Instagram **Business or Creator** account — this
   account is the "querying" identity used for Business Discovery lookups. You can only
   look up *other* public Business/Creator accounts this way; personal accounts are not
   returned.
3. A long-lived Page access token with `instagram_basic` (and, depending on your app's
   review status, `business_management`) permission.

See [Meta's Instagram Business Discovery docs](https://developers.facebook.com/docs/instagram-api/guides/business-discovery)
for how to obtain these.

## Project layout

```
ig_lead_pipeline/
├── main.py                  # CLI entrypoint
├── config/config.yaml       # workers, delays, output paths, feature toggles
├── scraper/
│   ├── instagram_client.py  # Graph API business_discovery calls
│   ├── website_scraper.py   # fetch + parse the linked website
│   ├── contact_extractor.py # email/phone/whatsapp regex + contact-page crawl
│   ├── tech_detector.py     # Shopify/Woo/custom, GA, Meta Pixel, live chat
│   ├── screenshot.py        # Playwright homepage screenshot
│   └── pipeline.py          # orchestration, resume, threading
├── exporter/
│   ├── db.py                 # SQLite progress + results store
│   ├── csv_exporter.py
│   └── excel_exporter.py
├── dashboard/
│   ├── app.py                # FastAPI dashboard
│   └── templates/index.html
├── utils/
│   ├── logger.py
│   ├── retry.py
│   ├── rate_limiter.py
│   ├── validators.py
│   └── proxy_manager.py       # for the *website* scraping step only
├── data/input/sample_input.csv
├── data/output/
├── logs/
├── tests/
├── requirements.txt
├── .env.example
└── docker/
```

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env                # fill in your Meta credentials
```

## Input

CSV with one column, `username` or `profile_url`:

```csv
username
example_store
https://www.instagram.com/another_store/
```

## Run

```bash
python main.py --input data/input/sample_input.csv --workers 4
```

Resume after interruption (default — progress is tracked in SQLite automatically):

```bash
python main.py --input data/input/sample_input.csv --resume
```

Force a clean re-run:

```bash
python main.py --input data/input/sample_input.csv --no-resume
```

Export existing results without re-scraping:

```bash
python main.py --export-only
```

## Dashboard

```bash
uvicorn dashboard.app:app --reload --port 8000
```

Open http://localhost:8000 — shows profiles processed, success rate, failed profiles,
active workers, ETA, log tail, and export buttons (CSV/XLSX).

## Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

Runs the dashboard on port 8000; run the pipeline itself with:

```bash
docker compose -f docker/docker-compose.yml run pipeline python main.py --input data/input/sample_input.csv
```

## Tests

```bash
pytest tests/ -v
```

## Rate limiting & etiquette

- The Graph API calls respect Meta's documented rate limits (`utils/rate_limiter.py`
  backs off on 429/`OAuthException` codes 4/17/32).
- Website scraping (a normal public site) uses randomized delays and honors
  `robots.txt` by default (`config.yaml: respect_robots_txt: true`) — turn this off only
  for sites you own or have permission to crawl aggressively.
- Proxy rotation (`utils/proxy_manager.py`) applies only to the website-scraping step,
  not to Instagram/Meta API calls.
