# lstm_model.py

import os
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ----------------
LOOKBACK_DAYS = 10
FUTURE_DAYS = 7
EPOCHS = 25
BATCH_SIZE = 16

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

# ---------------- MONGODB ----------------
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI not set")

client = MongoClient(MONGO_URI)
prices_col = client["dse"]["prices"]
sentiment_col = client["dse"]["sentiment"]
pred_col = client["dse"]["predictions"]

# ---------------- DATA ----------------
def get_price_sentiment_series(symbol: str):
    prices = list(
        prices_col.find(
            {"symbol": symbol, "close": {"$gt": 0}},
            {"_id": 0, "date": 1, "close": 1}
        ).sort("date", 1)
    )

    if not prices:
        return []

    sentiment_by_date = {}
    for s in sentiment_col.find({"symbol": "MARKET"}, {"_id": 0}):
        d = s.get("date")
        if d and isinstance(s.get("sentiment"), (int, float)):
            sentiment_by_date.setdefault(d, []).append(float(s["sentiment"]))

    daily_sentiment = {
        d: sum(v) / len(v) for d, v in sentiment_by_date.items()
    }

    series = []
    last_sentiment = 0.0

    for p in prices:
        day = p["date"]
        if day in daily_sentiment:
            last_sentiment = daily_sentiment[day]

        series.append([
            float(p["close"]),
            float(last_sentiment)
        ])

    return np.array(series, dtype=np.float32)


# ---------------- MODEL UTILS ----------------
def model_path(symbol: str):
    today = datetime.utcnow().date().isoformat()
    return os.path.join(MODEL_DIR, f"{symbol}_{today}.keras")


def build_model():
    model = Sequential([
        LSTM(64, input_shape=(LOOKBACK_DAYS, 2)),
        Dense(1)
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


# ---------------- MAIN PREDICTION ----------------
def predict_future(symbol: str):
    symbol = symbol.upper()
    today = datetime.utcnow().date().isoformat()

    cached = pred_col.find_one({"symbol": symbol, "date": today})
    if cached:
        return {
            "last_close": cached["last_close"],
            "future_7_days": cached["future_7_days"],
            "confidence": cached["confidence"],
        }, None

    data = get_price_sentiment_series(symbol)
    if len(data) < LOOKBACK_DAYS + FUTURE_DAYS:
        return None, "Not enough data"

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(data)

    X, y = [], []
    for i in range(LOOKBACK_DAYS, len(scaled)):
        X.append(scaled[i - LOOKBACK_DAYS:i])
        y.append(scaled[i][0])  # predict CLOSE only

    X, y = np.array(X), np.array(y)

    split = int(len(X) * 0.9)
    X_train, y_train = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    path = model_path(symbol)

    if os.path.exists(path):
        model = load_model(path)
    else:
        model = build_model()
        model.fit(
            X_train,
            y_train,
            epochs=EPOCHS,
            batch_size=BATCH_SIZE,
            verbose=0
        )
        model.save(path)

    val_preds = model.predict(X_val, verbose=0).flatten()
    residuals = y_val - val_preds
    sigma = float(np.std(residuals))
    confidence = [sigma] * FUTURE_DAYS

    last_seq = scaled[-LOOKBACK_DAYS:].reshape(1, LOOKBACK_DAYS, 2)
    future_scaled = []

    for _ in range(FUTURE_DAYS):
        next_close = model.predict(last_seq, verbose=0)[0][0]
        future_scaled.append(next_close)

        next_step = np.array([[next_close, last_seq[0, -1, 1]]])
        next_step = scaler.transform(next_step)

        last_seq = np.concatenate(
            [last_seq[:, 1:, :], next_step.reshape(1, 1, 2)],
            axis=1
        )

    future = scaler.inverse_transform(
        np.column_stack([future_scaled, np.zeros(FUTURE_DAYS)])
    )[:, 0]

    result = {
        "symbol": symbol,
        "date": today,
        "last_close": float(data[-1][0]),
        "future_7_days": future.tolist(),
        "confidence": confidence,
        "created_at": datetime.utcnow()
    }

    pred_col.insert_one(result)

    return {
        "last_close": result["last_close"],
        "future_7_days": result["future_7_days"],
        "confidence": result["confidence"],
    }, None
