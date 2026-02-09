# scraper.py
from dotenv import load_dotenv
load_dotenv()

import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from pymongo import MongoClient

# ---------- MONGODB ----------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
price_col = client["dse"]["prices"]

URL = "https://www.dsebd.org/latest_share_price_scroll_l.php"

# ---------- HELPERS ----------
def to_float(val):
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return None

# ---------- SCRAPER ----------
def scrape_and_store():
    print("🌐 Running DSE scraper (no Selenium)")

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("table.shares-table tbody tr")

    market_date = date.today()
    day_ts = datetime.combine(market_date, datetime.min.time())

    inserted = 0
    updated = 0

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 10:
            continue

        symbol = cols[1].get_text(strip=True).upper()
        close = to_float(cols[2].get_text())
        high = to_float(cols[3].get_text())
        low = to_float(cols[4].get_text())
        volume = to_float(cols[9].get_text()) or 0.0

        if not symbol or close is None:
            continue

        existing = price_col.find_one({
            "symbol": symbol,
            "date": market_date.isoformat()
        })

        if existing:
            price_col.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "high": max(existing["high"], high or close),
                        "low": min(existing["low"], low or close),
                        "close": close,
                        "volume": volume
                    }
                }
            )
            updated += 1
        else:
            price_col.insert_one({
                "symbol": symbol,
                "date": market_date.isoformat(),
                "timestamp": day_ts,
                "open": None,
                "high": high or close,
                "low": low or close,
                "close": close,
                "volume": volume
            })
            inserted += 1

    print(f"✅ Done | Inserted: {inserted}, Updated: {updated}")

    return {
        "inserted": inserted,
        "updated": updated,
        "date": market_date.isoformat()
    }
