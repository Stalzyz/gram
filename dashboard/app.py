"""FastAPI dashboard: run status, success rate, failed profiles, ETA,
log tail, and CSV/XLSX export/download endpoints.

Run with: uvicorn dashboard.app:app --reload --port 8000
"""
import os
import threading

import yaml
from fastapi import FastAPI, BackgroundTasks, Depends
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from scraper.pipeline import LeadPipeline
from utils.logger import tail_log
from dashboard.auth import router as auth_router, get_current_user_id
from dashboard.billing import router as billing_router
from dashboard.admin import router as admin_router

CONFIG_PATH = os.environ.get("IG_PIPELINE_CONFIG", "config/config.yaml")

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

app = FastAPI(title="IG Lead Pipeline Dashboard")
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(billing_router, prefix="/api/billing", tags=["billing"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

pipeline = LeadPipeline(CONFIG)
_run_lock = threading.Lock()
_run_thread = None

from exporter.db import store
@app.get("/api/config/auth")
def get_auth_config():
    return {"google_client_id": store.get_setting("google_client_id", "")}

@app.get("/api/config/pricing")
def get_pricing_config():
    stripe_key    = store.get_setting("stripe_secret_key",     "") or ""
    rzp_key_id    = store.get_setting("razorpay_key_id",       "") or ""
    rzp_key_sec   = store.get_setting("razorpay_key_secret",   "") or ""
    return {
        "stripe_active":          bool(stripe_key),
        "razorpay_active":        bool(rzp_key_id and rzp_key_sec),
        "stripe_starter_price":   store.get_setting("stripe_starter_price",   "1000"),
        "stripe_pro_price":       store.get_setting("stripe_pro_price",       "4000"),
        "razorpay_starter_price": store.get_setting("razorpay_starter_price", "80000"),
        "razorpay_pro_price":     store.get_setting("razorpay_pro_price",     "320000"),
        "starter_credits":        store.get_setting("starter_credits",        "1,000"),
        "pro_credits":            store.get_setting("pro_credits",            "5,000"),
    }

@app.get("/api/config/brand")
def get_brand_config():
    return {
        "brand_name": store.get_setting("brand_name", ""),
        "brand_color": store.get_setting("brand_color", ""),
        "logo_url": store.get_setting("logo_url", "")
    }


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stats")
def api_stats(campaign: str = "default", user_id: int = Depends(get_current_user_id)):
    db_stats = pipeline.store.stats(user_id, campaign)
    total = db_stats["total"] or 1
    success_rate = round((db_stats["success"] / total) * 100, 1)
    eta = pipeline.eta_seconds(user_id, campaign)
    return JSONResponse({
        "processed": db_stats["success"] + db_stats["failed"],
        "total": db_stats["total"],
        "success": db_stats["success"],
        "failed": db_stats["failed"],
        "pending": db_stats["pending"],
        "success_rate_pct": success_rate,
        "active_workers": pipeline.stats.active_workers,
        "eta_seconds": round(eta, 1),
        "failed_profiles": db_stats["failed_profiles"],
    })

from typing import Optional

class UserPreferences(BaseModel):
    min_followers: int = 0
    max_followers: Optional[int] = None
    location_keywords: Optional[str] = None
    require_shopify: bool = False
    require_woocommerce: bool = False
    require_meta_pixel: bool = False
    target_categories: Optional[str] = None
    require_website: bool = False
    deep_enrichment: bool = False

@app.get("/api/user/preferences")
def api_get_preferences(user_id: int = Depends(get_current_user_id)):
    return pipeline.store.get_user_preferences(user_id)

@app.post("/api/user/preferences")
def api_set_preferences(prefs: UserPreferences, user_id: int = Depends(get_current_user_id)):
    pipeline.store.set_user_preferences(user_id, prefs.dict())
    return {"status": "success"}

@app.get("/api/user/campaigns")
def api_get_campaigns(user_id: int = Depends(get_current_user_id)):
    return pipeline.store.get_user_campaigns(user_id)

@app.get("/api/logs")
def api_logs(lines: int = 150):
    log_dir = CONFIG["paths"]["log_dir"]
    return JSONResponse({"lines": tail_log(log_dir, n_lines=lines)})


@app.post("/api/run")
def api_run(input_csv: str, workers: int = None, resume: bool = True, campaign: str = "default", user_id: int = Depends(get_current_user_id), background_tasks: BackgroundTasks = None):
    """Kick off a pipeline run in the background (non-blocking for the dashboard)."""
    global _run_thread

    # Calculate exact cost based on the number of leads in the CSV (1 credit per 10 leads)
    # Subtract 1 for the header row
    try:
        with open(input_csv, 'r', encoding='utf-8') as f:
            lines = sum(1 for line in f)
        lead_count = max(0, lines - 1)
        cost = (lead_count + 9) // 10  # Ceiling division by 10
    except FileNotFoundError:
        cost = 0

    if not pipeline.store.deduct_credits(user_id, cost):
        return JSONResponse({"status": "insufficient_credits", "required": cost}, status_code=402)

    with _run_lock:
        if _run_thread and _run_thread.is_alive():
            return JSONResponse({"status": "already_running"}, status_code=409)

        # Pull from DB setting if available, else default config
        db_workers = pipeline.store.get_setting("scraping_workers")
        if db_workers and db_workers.isdigit():
            default_w = int(db_workers)
        else:
            default_w = CONFIG["pipeline"]["workers"]
            
        w = workers or default_w
        _run_thread = threading.Thread(
            target=pipeline.run,
            kwargs={"user_id": user_id, "input_csv": input_csv, "workers": w, "resume": resume, "campaign": campaign},
            daemon=True,
        )
        _run_thread.start()

    return JSONResponse({"status": "started"})


@app.get("/api/export/csv")
def export_csv_endpoint(campaign: str = "default", user_id: int = Depends(get_current_user_id)):
    summary = pipeline.export(user_id, CONFIG["paths"]["output_dir"], campaign=campaign)
    return FileResponse(summary["csv"], filename=f"{campaign}_leads.csv", media_type="text/csv")


@app.get("/api/export/xlsx")
def export_xlsx_endpoint(campaign: str = "default", user_id: int = Depends(get_current_user_id)):
    summary = pipeline.export(user_id, CONFIG["paths"]["output_dir"], campaign=campaign)
    return FileResponse(
        summary["xlsx"],
        filename=f"{campaign}_leads.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


from pydantic import BaseModel
import csv

class DiscoverRequest(BaseModel):
    keyword: str
    limit: int = 50

@app.post("/api/discover")
def api_discover(req: DiscoverRequest):
    from scraper.discovery_dorks import DorkScraper
    scraper = DorkScraper()
    usernames = scraper.discover_leads(keyword=req.keyword, limit=req.limit)
    
    if not usernames:
        return JSONResponse({"status": "error", "message": "No usernames found. Query might be too niche or blocked."}, status_code=400)
        
    output_path = "data/input/discovered_leads.csv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['username'])
        for username in usernames:
            writer.writerow([username])
            
    return JSONResponse({"status": "success", "count": len(usernames), "csv_path": output_path})

