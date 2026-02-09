from fastapi import FastAPI, HTTPException
from datetime import datetime
from pymongo import MongoClient
import os

from scraper import scrape_and_store
from sentiment_scraper import scrape_market_sentiment
from lstm_model import calculate_and_store_mse

from dotenv import load_dotenv
load_dotenv()

# ---------------- CONFIG ----------------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

price_col = client["dse"]["prices"]
market_sentiment_col = client["dse"]["market_sentiment"]

app = FastAPI()


# ---------------- STARTUP ----------------
@app.on_event("startup")
def startup():
    print("🚀 API starting...")

    print("📈 Running PRICE scraper...")
    scrape_and_store()

    print("📰 Running MARKET SENTIMENT scraper...")
    scrape_market_sentiment(days=30)

    print("✅ Scrapers finished")

    
    calculate_and_store_mse()


# ---------------- FORECAST API ----------------
@app.get("/stocks/forecast/{symbol}")
def stock_forecast(symbol: str):
    symbol = symbol.upper()

    prices = list(
        price_col.find(
            {"symbol": symbol},
            {"_id": 0, "date": 1, "close": 1}
        ).sort("date", 1)
    )

    if len(prices) < 10:
        raise HTTPException(status_code=404, detail="Not enough price data")

    history = [
        {
            "date": p["date"],
            "price": float(p["close"])
        }
        for p in prices
        if p.get("close") is not None
    ]

    # 🔮 Dummy LSTM output (replace later)
    last_price = history[-1]["price"]
    future_7_days = [
        round(last_price * (1 + i * 0.01), 2)
        for i in range(1, 8)
    ]

    return {
        "symbol": symbol,
        "history": history,
        "future7Days": future_7_days
    }


# ---------------- DEBUG SENTIMENT ----------------
@app.get("/market/sentiment")
def get_market_sentiment():
    docs = list(
        market_sentiment_col.find(
            {},
            {"_id": 0, "date": 1, "sentiment": 1}
        ).sort("date", 1)
    )
    return docs