from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from dashboard.auth import get_current_user_id
from exporter.db import store
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

def get_admin_user(user_id: int = Depends(get_current_user_id)):
    user = store.get_user_by_id(user_id)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

@router.get("/sales")
def get_sales(admin=Depends(get_admin_user)):
    return store.get_sales_stats()

@router.get("/settings")
def get_settings(admin=Depends(get_admin_user)):
    keys = [
        "free_credits",
        # Brand & Theme
        "brand_name", "support_email", "business_address", "logo_url", "brand_color",
        # Payments
        "stripe_secret_key", "stripe_publishable_key", "stripe_starter_price", "stripe_pro_price",
        "razorpay_key_id", "razorpay_key_secret", "razorpay_starter_price", "razorpay_pro_price",
        # Tax
        "gstin", "gst_rate",
        # Auth
        "google_client_id", "google_client_secret",
        # Scraping System Settings
        "scraping_workers", "scraping_min_delay", "scraping_max_delay", "scraping_max_retries", "scraping_proxies",
    ]
    return {key: store.get_setting(key, "") for key in keys}

class SettingUpdate(BaseModel):
    key: str
    value: str

@router.post("/settings")
def update_setting(req: SettingUpdate, admin=Depends(get_admin_user)):
    store.set_setting(req.key, req.value)
    return {"status": "success"}

@router.get("/customers")
def get_customers(admin=Depends(get_admin_user)):
    return store.get_customers()

class GiftCredits(BaseModel):
    credits: int

@router.post("/customers/{customer_id}/gift")
def gift_credits(customer_id: int, req: GiftCredits, admin=Depends(get_admin_user)):
    store.add_credits(customer_id, req.credits)
    return {"status": "success"}

@router.get("/customers/{customer_id}/invoice", response_class=HTMLResponse)
def get_customer_invoice(customer_id: int, admin=Depends(get_admin_user)):
    data = store.get_customer_invoice(customer_id)
    if not data:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Pull brand & tax settings
    brand_name    = store.get_setting("brand_name", "Pipeline SaaS") or "Pipeline SaaS"
    support_email = store.get_setting("support_email", "support@pipeline.io") or "support@pipeline.io"
    address_raw   = store.get_setting("business_address", "") or ""
    logo_url      = store.get_setting("logo_url", "") or ""
    brand_color   = store.get_setting("brand_color", "#2563eb") or "#2563eb"
    gstin         = store.get_setting("gstin", "") or ""
    gst_rate_str  = store.get_setting("gst_rate", "0") or "0"
    gst_rate      = float(gst_rate_str) if gst_rate_str else 0.0

    invoice_number = f"INV-{customer_id:04d}-{datetime.now().strftime('%Y%m')}"
    generated_date = datetime.now().strftime("%d %b %Y")

    # Build address HTML
    address_html = address_raw.replace("\n", "<br>") if address_raw else "—"
    gstin_html = f'<span style="font-size:11px;opacity:0.7;">GSTIN: {gstin}</span>' if gstin else ""

    # Logo
    logo_html = f'<img src="{logo_url}" alt="Logo" style="max-height:40px;margin-bottom:6px;display:block;" />' if logo_url else ""

    rows_html = ""
    subtotal = 0.0
    if data["transactions"]:
        for i, tx in enumerate(data["transactions"], 1):
            pre_tax = tx["amount_usd"] / (1 + gst_rate / 100) if gst_rate > 0 else tx["amount_usd"]
            gst_amt = tx["amount_usd"] - pre_tax
            subtotal += tx["amount_usd"]

            color_bg = "#e8f5e9" if tx["gateway"] == "razorpay" else "#e3f2fd"
            color_fg = "#2e7d32" if tx["gateway"] == "razorpay" else "#1565c0"
            gateway_badge = f'<span style="background:{color_bg};color:{color_fg};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">{tx["gateway"].title()}</span>'
            gst_cell = f'${gst_amt:.2f} <span style="font-size:10px;color:#94a3b8;">({gst_rate:.0f}%)</span>' if gst_rate > 0 else "—"

            rows_html += f"""
            <tr style="border-bottom:1px solid #f0f0f0;">
              <td style="padding:12px 16px;color:#666;">#{i}</td>
              <td style="padding:12px 16px;font-family:monospace;font-size:12px;color:#888;">TXN-{tx["id"]}</td>
              <td style="padding:12px 16px;">{tx["date"]}</td>
              <td style="padding:12px 16px;">{gateway_badge}</td>
              <td style="padding:12px 16px;font-weight:600;color:#2d6a4f;">{tx["credits"]:,} Credits</td>
              <td style="padding:12px 16px;text-align:center;">{gst_cell}</td>
              <td style="padding:12px 16px;text-align:right;font-weight:700;">${tx["amount_usd"]:.2f}</td>
            </tr>"""
    else:
        rows_html = '<tr><td colspan="7" style="padding:32px;text-align:center;color:#aaa;">No transactions found for this customer.</td></tr>'

    gst_col_header = f'<th style="padding:12px 16px;text-align:center;">GST ({gst_rate:.0f}%)</th>' if gst_rate > 0 else '<th style="padding:12px 16px;text-align:center;">Tax</th>'
    total_gst = subtotal - (subtotal / (1 + gst_rate / 100)) if gst_rate > 0 else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Invoice {invoice_number} — {brand_name}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', sans-serif; background: #f8f9fa; color: #1a1a2e; }}
    .page {{ max-width: 860px; margin: 40px auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 40px rgba(0,0,0,0.08); }}
    .header {{ background: linear-gradient(135deg, {brand_color}dd 0%, {brand_color} 100%); color: white; padding: 48px; position: relative; overflow: hidden; }}
    .header::after {{ content: ''; position: absolute; top: -60px; right: -60px; width: 240px; height: 240px; background: rgba(255,255,255,0.05); border-radius: 50%; }}
    .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 36px; }}
    .brand-block .brand-name {{ font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
    .brand-block .brand-address {{ font-size: 12px; opacity: 0.75; margin-top: 6px; line-height: 1.6; max-width: 260px; }}
    .invoice-badge {{ background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.2); border-radius: 12px; padding: 12px 22px; text-align: right; }}
    .invoice-badge .label {{ font-size: 11px; opacity: 0.7; text-transform: uppercase; letter-spacing: 1px; }}
    .invoice-badge .number {{ font-size: 18px; font-weight: 700; margin-top: 2px; }}
    .header-meta {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 20px; }}
    .meta-item .label {{ font-size: 10px; opacity: 0.6; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }}
    .meta-item .value {{ font-size: 13px; font-weight: 600; word-break: break-word; }}
    .body {{ padding: 48px; }}
    .section-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    thead tr {{ background: #f8fafc; }}
    thead th {{ padding: 12px 16px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: #64748b; text-align: left; }}
    .totals-row td {{ padding: 14px 16px; font-size: 13px; border-top: 1px solid #e2e8f0; }}
    .grand-total td {{ padding: 16px; font-size: 15px; font-weight: 800; background: #f0f9ff; border-top: 2px solid {brand_color}33; }}
    .grand-total td:last-child {{ text-align: right; color: {brand_color}; font-size: 20px; }}
    .footer {{ border-top: 1px solid #f0f0f0; padding: 24px 48px; display: flex; justify-content: space-between; align-items: center; background: #fafafa; }}
    .footer p {{ font-size: 12px; color: #94a3b8; }}
    .print-btn {{ background: {brand_color}; color: white; border: none; padding: 10px 24px; border-radius: 8px; font-family: inherit; font-weight: 600; font-size: 13px; cursor: pointer; }}
    @media print {{
      body {{ background: white; }}
      .page {{ box-shadow: none; margin: 0; border-radius: 0; }}
      .print-btn {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div class="header-top">
        <div class="brand-block">
          {logo_html}
          <div class="brand-name">{brand_name}</div>
          <div class="brand-address">{address_html}<br>{gstin_html}</div>
        </div>
        <div class="invoice-badge">
          <div class="label">Invoice</div>
          <div class="number">{invoice_number}</div>
        </div>
      </div>
      <div class="header-meta">
        <div class="meta-item">
          <div class="label">Bill To</div>
          <div class="value">{data["email"]}</div>
        </div>
        <div class="meta-item">
          <div class="label">Customer ID</div>
          <div class="value">#{customer_id:04d}</div>
        </div>
        <div class="meta-item">
          <div class="label">Member Since</div>
          <div class="value">{data["member_since"]}</div>
        </div>
        <div class="meta-item">
          <div class="label">Generated On</div>
          <div class="value">{generated_date}</div>
        </div>
      </div>
    </div>

    <div class="body">
      <div class="section-title">Transaction History</div>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Reference</th>
            <th>Date</th>
            <th>Gateway</th>
            <th>Credits</th>
            {gst_col_header}
            <th style="text-align:right;">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
        <tfoot>
          {"" if gst_rate == 0 else f'''
          <tr class="totals-row">
            <td colspan="5"></td>
            <td style="color:#64748b;">GST ({gst_rate:.0f}%) included</td>
            <td style="text-align:right;color:#7c3aed;">${total_gst:.2f}</td>
          </tr>
          <tr class="totals-row">
            <td colspan="5"></td>
            <td style="color:#64748b;">Net (excl. GST)</td>
            <td style="text-align:right;">${(subtotal - total_gst):.2f}</td>
          </tr>'''}
          <tr class="grand-total">
            <td colspan="4" style="color:#64748b;font-size:13px;">
              Credits Balance: <strong style="color:#1a1a2e;">{data["credits"]:,}</strong>
            </td>
            <td colspan="2" style="color:#64748b;font-size:13px;">Total Paid (incl. tax)</td>
            <td style="text-align:right;">${data["total_spent_usd"]:.2f}</td>
          </tr>
        </tfoot>
      </table>
    </div>

    <div class="footer">
      <p>Thank you for using {brand_name}. For support: {support_email}</p>
      <button class="print-btn" onclick="window.print()">&#x2399; Print / Save PDF</button>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)
