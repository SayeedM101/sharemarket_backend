# sentiment_scraper.py
from dotenv import load_dotenv
load_dotenv()

import os
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from sentiment_model import analyze_sentiment

# ---------- ENV ----------
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

if not NEWS_API_KEY:
    raise RuntimeError("NEWS_API_KEY missing in .env")

# ---------- DB ----------
client = MongoClient(MONGO_URI)
sentiment_col = client["dse"]["market_sentiment"]

# ---------- CONFIG ----------
NEWS_URL = "https://newsapi.org/v2/everything"

QUERY = (
    "Bangladesh stock market OR Dhaka Stock Exchange OR DSE market"
)

def scrape_market_sentiment(days: int = 30):
    print("📰 Scraping MARKET sentiment (last 30 days)")

    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    params = {
        "q": QUERY,
        "from": from_date,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": 100,
        "apiKey": NEWS_API_KEY,
    }

    res = requests.get(NEWS_URL, params=params, timeout=30)
    res.raise_for_status()

    articles = res.json().get("articles", [])

    if not articles:
        print("⚠️ No market news found")
        return

    daily_scores = {}

    for art in articles:
        text = f"{art.get('title','')} {art.get('description','')}"
        score = analyze_sentiment(text)

        if score == 0.0:
            continue

        date = art["publishedAt"][:10]

        daily_scores.setdefault(date, []).append(score)

    inserted = 0

    for day, scores in daily_scores.items():
        avg = round(sum(scores) / len(scores), 4)

        sentiment_col.update_one(
            {"date": day},
            {
                "$set": {
                    "sentiment": avg,
                    "count": len(scores),
                    "source": "NewsAPI"
                }
            },
            upsert=True
        )
        inserted += 1

    print(f"✅ Stored market sentiment for {inserted} days")


if __name__ == "__main__":
    scrape_market_sentiment()
