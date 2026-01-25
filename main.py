# main.py

from fastapi import FastAPI, HTTPException
from scraper import scrape_and_store
from lstm_model import predict_future
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

app = FastAPI(title="DSE Stock API")

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
collection = client["dse"]["prices"]

# ---------------- STARTUP ----------------

@app.on_event("startup")
def startup_job():
    print("🚀 API started → running daily scraper")

    try:
        scrape_and_store()
        print("✅ Daily scraper finished successfully")
    except Exception as e:
        print("⚠️ Scraper failed on startup")
        print(str(e))
        traceback.print_exc()

# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "API running"}

# ---------------- HISTORY ----------------
@app.get("/stocks/history/{symbol}")
def history(symbol: str, limit: int = 60):
    data = list(
        collection.find(
            {"symbol": symbol.upper()},
            {"_id": 0}
        )
        .sort("timestamp", 1)
        .limit(limit)
    )

    if not data:
        raise HTTPException(404, "No data found")

    return data

# ---------------- PREDICTION ----------------
@app.get("/stocks/predict/{symbol}")
def predict(symbol: str):
    result, error = predict_future(symbol.upper())

    if error:
        raise HTTPException(400, error)

    return {
        "symbol": symbol.upper(),
        "last_close": result["last_close"],
        "future_7_days": result["future_7_days"],
    }

# ---------------- COMBINED ENDPOINT (IMPORTANT) ----------------
@app.get("/stocks/forecast/{symbol}")
def forecast(symbol: str):
    history = list(
        collection.find(
            {"symbol": symbol.upper()},
            {"_id": 0}
        )
        .sort("timestamp", 1)
        .limit(60)
    )

    if not history:
        raise HTTPException(404, "No data")

    result, error = predict_future(symbol.upper())
    if error:
        raise HTTPException(400, error)

    return {
        "symbol": symbol.upper(),
        "history": history,
        "last_close": result["last_close"],
        "future_7_days": result["future_7_days"],
    }
