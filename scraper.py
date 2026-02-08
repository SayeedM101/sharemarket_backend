# scraper.py
from dotenv import load_dotenv
load_dotenv()

import os
import time
from datetime import datetime, date
from pymongo import MongoClient

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ---------- MONGODB ----------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
price_col = client["dse"]["prices"]

# ---------- HELPERS ----------
def to_float(val):
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return None

# ---------- SCRAPER ----------
def scrape_and_store():
    print("🌐 Running DSE daily OHLC scraper")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get("https://www.dsebd.org/latest_share_price_scroll_l.php")
        time.sleep(5)

        rows = driver.find_elements(By.CSS_SELECTOR, "table.shares-table tbody tr")

        market_date = date.today()
        day_ts = datetime.combine(market_date, datetime.min.time())

        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 10:
                continue

            symbol = cols[1].text.strip().upper()
            close = to_float(cols[2].text)
            high = to_float(cols[3].text)
            low = to_float(cols[4].text)
            volume = to_float(cols[9].text) or 0.0

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
            else:
                price_col.insert_one({
                    "symbol": symbol,
                    "date": market_date.isoformat(),
                    "timestamp": day_ts,
                    "open": None,  # not available from source
                    "high": high or close,
                    "low": low or close,
                    "close": close,
                    "volume": volume
                })

        print("✅ OHLC stored safely")

    finally:
        driver.quit()


if __name__ == "__main__":
    scrape_and_store()
