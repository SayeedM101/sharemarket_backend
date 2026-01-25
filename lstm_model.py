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
LOOKBACK_DAYS = 10        # ⚠️ unchanged
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
pred_col = client["dse"]["predictions"]

# ---------------- DATA ----------------
def get_daily_close(symbol: str):
    cursor = prices_col.find(
        {"symbol": symbol},
        {"_id": 0, "close": 1}
    ).sort("timestamp", 1)

    return [
        float(d["close"])
        for d in cursor
        if d.get("close") and d["close"] > 0
    ]


# ---------------- MODEL UTILS ----------------
def model_path(symbol: str):
    today = datetime.utcnow().date().isoformat()
    return os.path.join(MODEL_DIR, f"{symbol}_{today}.keras")


def build_model():
    model = Sequential([
        LSTM(64, input_shape=(LOOKBACK_DAYS, 1)),
        Dense(1)
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


# ---------------- MAIN PREDICTION ----------------
def predict_future(symbol: str):
    symbol = symbol.upper()
    today = datetime.utcnow().date().isoformat()

    # 🔹 1. Return cached prediction if exists
    cached = pred_col.find_one({"symbol": symbol, "date": today})
    if cached:
        return {
            "last_close": cached["last_close"],
            "future_7_days": cached["future_7_days"],
            "confidence": cached["confidence"],
        }, None

    closes = get_daily_close(symbol)
    if len(closes) < LOOKBACK_DAYS + FUTURE_DAYS:
        return None, "Not enough data"

    closes = np.array(closes, dtype=np.float32).reshape(-1, 1)

    # -------- SCALING --------
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(closes)

    # -------- SEQUENCES --------
    X, y = [], []
    for i in range(LOOKBACK_DAYS, len(scaled)):
        X.append(scaled[i - LOOKBACK_DAYS:i])
        y.append(scaled[i])

    X, y = np.array(X), np.array(y)

    split = int(len(X) * 0.9)
    X_train, y_train = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    # -------- LOAD OR TRAIN MODEL --------
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

    # -------- CONFIDENCE (RESIDUALS) --------
    val_preds = model.predict(X_val, verbose=0).flatten()
    residuals = scaler.inverse_transform(
        (y_val.flatten() - val_preds).reshape(-1, 1)
    ).flatten()

    sigma = np.std(residuals)
    confidence = [float(sigma)] * FUTURE_DAYS

    # -------- FUTURE FORECAST --------
    future_scaled = []
    last_seq = scaled[-LOOKBACK_DAYS:].reshape(1, LOOKBACK_DAYS, 1)

    for _ in range(FUTURE_DAYS):
        next_val = model.predict(last_seq, verbose=0)[0][0]
        future_scaled.append(next_val)
        last_seq = np.concatenate(
            [last_seq[:, 1:, :], [[[next_val]]]],
            axis=1
        )

    future = scaler.inverse_transform(
        np.array(future_scaled).reshape(-1, 1)
    ).flatten()

    result = {
        "symbol": symbol,
        "date": today,
        "last_close": float(closes[-1][0]),
        "future_7_days": future.tolist(),
        "confidence": confidence,
        "created_at": datetime.utcnow()
    }

    # 🔹 2. Persist daily prediction
    pred_col.insert_one(result)

    return {
        "last_close": result["last_close"],
        "future_7_days": result["future_7_days"],
        "confidence": result["confidence"],
    }, None
