# scraper.py (SELENIUM VERSION – GUARANTEED)

from dotenv import load_dotenv
load_dotenv()

import os
import time
from datetime import datetime
from pymongo import MongoClient

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- MONGODB ----------------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
collection = client["dse"]["prices"]

# ---------------- HELPERS ----------------
def to_float(val):
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return None

# ---------------- SCRAPER ----------------
def scrape_and_store():
    print("🌐 Launching browser for DSE scrape...")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.get("https://www.dsebd.org/latest_share_price_scroll_l.php")
        time.sleep(5)  # 🔑 wait for JS

        rows = driver.find_elements(By.CSS_SELECTOR, "table.shares-table tbody tr")

        today = datetime.utcnow().date().isoformat()
        now = datetime.utcnow()

        stocks = []

        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 10:
                continue

            symbol = cols[1].text.strip().upper()
            ltp = to_float(cols[2].text)
            high = to_float(cols[3].text)
            low = to_float(cols[4].text)
            volume = to_float(cols[9].text) or 0.0

            if not symbol or ltp is None:
                continue

            stocks.append({
                "symbol": symbol,
                "open": ltp,
                "high": high,
                "low": low,
                "close": ltp,
                "volume": volume,
                "date": today,
                "timestamp": now
            })

        print(f"📊 Parsed {len(stocks)} stocks")

        upserted = 0
        for stock in stocks:
            res = collection.update_one(
                {"symbol": stock["symbol"], "date": stock["date"]},
                {"$set": stock},
                upsert=True
            )
            if res.upserted_id:
                upserted += 1

        print(f"✅ Upserted {upserted} records")

    finally:
        driver.quit()
