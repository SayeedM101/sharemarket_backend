# sentiment_model.py
from textblob import TextBlob

def analyze_sentiment(text: str) -> float:
    """
    Returns sentiment polarity between -1 and +1
    """
    if not text or len(text.strip()) < 20:
        return 0.0

    try:
        blob = TextBlob(text)
        polarity = float(blob.sentiment.polarity)

        # remove tiny noise
        if abs(polarity) < 0.05:
            return 0.0

        return round(polarity, 4)

    except Exception:
        return 0.0
