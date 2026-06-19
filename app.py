import os
from datetime import date, timedelta

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from vnstock import Fundamental, Market, Reference, register_user
except Exception as import_error:
    Fundamental = None
    Market = None
    Reference = None
    register_user = None
    VNSTOCK_IMPORT_ERROR = import_error
else:
    VNSTOCK_IMPORT_ERROR = None


app = Flask(__name__)
CORS(app)

_market = None
_reference = None
_fundamental = None
_vnstock_registered = False


def normalize_symbol(raw_symbol):
    return "".join(
        char for char in str(raw_symbol or "").strip().upper() if char.isalnum() or char in "._-"
    )


def dataframe_to_records(df):
    if df is None:
        return []
    return df.where(df.notna(), None).to_dict(orient="records")


def pick_number(record, candidates):
    for key in candidates:
        value = record.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
    return None


def ensure_vnstock():
    global _fundamental, _market, _reference, _vnstock_registered

    if VNSTOCK_IMPORT_ERROR:
        raise RuntimeError(f"Cannot import vnstock: {VNSTOCK_IMPORT_ERROR}")

    if not _vnstock_registered and os.getenv("VNSTOCK_API_KEY"):
        register_user(api_key=os.getenv("VNSTOCK_API_KEY"))
        _vnstock_registered = True

    if _market is None:
        _market = Market()
    if _reference is None:
        _reference = Reference()
    if _fundamental is None:
        _fundamental = Fundamental()

    return _market, _reference, _fundamental


def require_action_key():
    configured_key = os.getenv("ACTION_API_KEY")
    if not configured_key:
        return None

    auth_header = request.headers.get("authorization", "")
    bearer_token = auth_header.removeprefix("Bearer ").removeprefix("bearer ")
    query_token = request.args.get("api_key")

    if bearer_token == configured_key or query_token == configured_key:
        return None

    return jsonify({"error": "Unauthorized", "message": "Missing or invalid API key"}), 401


def provider_mode():
    return os.getenv("DATA_PROVIDER", "vnstock").lower()


def demo_price(symbol):
    base = sum(ord(char) for char in symbol)
    price = 10000 + (base % 250) * 120
    change = ((base % 21) - 10) * 10
    change_percent = round((change / price) * 100, 2)
    return {
        "symbol": symbol,
        "exchange": "DEMO",
        "price": price,
        "change": change,
        "changePercent": change_percent,
        "volume": 1000000 + (base % 1000) * 900,
        "updatedAt": date.today().isoformat(),
        "provider": "demo",
    }


def get_vnstock_price(symbol):
    market, _, _ = ensure_vnstock()
    df = market.equity.quote(symbol=symbol)
    records = dataframe_to_records(df)

    if not records:
        raise RuntimeError(f"No price data returned for {symbol}")

    record = records[0]
    price = pick_number(record, ["price", "lastPrice", "matchPrice", "close", "last_price"])
    reference_price = pick_number(record, ["refPrice", "referencePrice", "reference_price"])
    change = pick_number(record, ["change", "priceChange"])
    change_percent = pick_number(record, ["changePercent", "pctChange", "priceChangePercent"])

    if change is None and price is not None and reference_price is not None:
        change = price - reference_price
    if change_percent is None and change is not None and reference_price:
        change_percent = round((change / reference_price) * 100, 2)

    return {
        "symbol": symbol,
        "exchange": record.get("exchange") or record.get("board") or record.get("floor"),
        "price": price,
        "change": change,
        "changePercent": change_percent,
        "volume": pick_number(record, ["volume", "matchVolume", "totalVolume"]),
        "updatedAt": record.get("time") or record.get("tradingDate") or date.today().isoformat(),
        "provider": "vnstock",
        "raw": record,
    }


def get_vnstock_history(symbol):
    market, _, _ = ensure_vnstock()
    end = date.today()
    start = end - timedelta(days=120)
    df = market.equity.ohlcv(symbol=symbol, start=start.isoformat(), end=end.isoformat())
    records = dataframe_to_records(df)
    return {"symbol": symbol, "timeframe": "daily", "candles": records, "provider": "vnstock"}


def get_vnstock_fundamental(symbol):
    _, reference, fundamental = ensure_vnstock()
    profile = dataframe_to_records(reference.company.info(symbol=symbol))

    try:
        ratios = dataframe_to_records(fundamental.equity.ratios(symbol=symbol, period="year"))
    except Exception:
        ratios = []

    return {"symbol": symbol, "profile": profile, "ratios": ratios[:12], "provider": "vnstock"}


def get_vnstock_indicators(symbol):
    history = get_vnstock_history(symbol)
    candles = history.get("candles", [])
    closes = []
    volumes = []

    for candle in candles:
        close = pick_number(candle, ["close", "Close"])
        volume = pick_number(candle, ["volume", "Volume"])
        if isinstance(close, (int, float)):
            closes.append(close)
        if isinstance(volume, (int, float)):
            volumes.append(volume)

    def sma(length):
        if len(closes) < length:
            return None
        return round(sum(closes[-length:]) / length, 2)

    average_volume20 = None
    if len(volumes) >= 20:
        average_volume20 = round(sum(volumes[-20:]) / 20, 2)

    return {
        "symbol": symbol,
        "trend": {
            "ma20": sma(20),
            "ma50": sma(50),
            "lastClose": closes[-1] if closes else None,
        },
        "liquidity": {
            "averageVolume20": average_volume20,
        },
        "provider": "vnstock",
    }


def get_vnstock_market_cap(symbol):
    fundamental = get_vnstock_fundamental(symbol)
    profile = fundamental.get("profile", [])
    first = profile[0] if profile else {}
    return {
        "symbol": symbol,
        "marketCap": pick_number(first, ["marketCap", "market_cap", "marketCapitalization"]),
        "sharesOutstanding": pick_number(first, ["sharesOutstanding", "outstandingShare", "shares"]),
        "currency": "VND",
        "provider": "vnstock",
        "raw": first,
    }


def calculate_sepa_score(price, fundamentals, indicators):
    current_price = price.get("price")
    ma50 = indicators.get("trend", {}).get("ma50")
    average_volume20 = indicators.get("liquidity", {}).get("averageVolume20")

    trend_score = 25 if current_price and ma50 and current_price > ma50 else 12
    liquidity_score = 25 if average_volume20 and average_volume20 >= 1000000 else 12
    quality_score = 18 if fundamentals.get("ratios") else 10
    data_score = 25 if price.get("provider") == "vnstock" else 10
    total = trend_score + liquidity_score + quality_score + data_score

    return {
        "total": total,
        "rating": "pass" if total >= 80 else "watchlist" if total >= 60 else "fail",
        "components": {
            "trendScore": trend_score,
            "liquidityScore": liquidity_score,
            "qualityScore": quality_score,
            "dataScore": data_score,
        },
        "notes": [
            "Score is a simplified SEPA-style screening score, not investment advice.",
            "Use provider raw data for deeper analysis.",
        ],
    }


def get_price(symbol):
    if provider_mode() == "demo":
        return demo_price(symbol)
    return get_vnstock_price(symbol)


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "provider": provider_mode(),
            "vnstockReady": VNSTOCK_IMPORT_ERROR is None,
            "updatedAt": date.today().isoformat(),
        }
    )


@app.get("/price/<symbol>")
def price(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        return jsonify(get_price(symbol))
    except Exception as error:
        return jsonify({"error": "Price lookup failed", "message": str(error)}), 502


@app.get("/history/<symbol>")
def history(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        if provider_mode() == "demo":
            return jsonify({"symbol": symbol, "candles": [], "provider": "demo"})
        return jsonify(get_vnstock_history(symbol))
    except Exception as error:
        return jsonify({"error": "History lookup failed", "message": str(error)}), 502


@app.get("/fundamental/<symbol>")
def fundamental(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        if provider_mode() == "demo":
            return jsonify({"symbol": symbol, "provider": "demo"})
        return jsonify(get_vnstock_fundamental(symbol))
    except Exception as error:
        return jsonify({"error": "Fundamental lookup failed", "message": str(error)}), 502


@app.get("/financial-indicators/<symbol>")
def financial_indicators(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        if provider_mode() == "demo":
            return jsonify({"symbol": symbol, "provider": "demo"})
        return jsonify(get_vnstock_indicators(symbol))
    except Exception as error:
        return jsonify({"error": "Indicators lookup failed", "message": str(error)}), 502


@app.get("/market-cap/<symbol>")
def market_cap(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        if provider_mode() == "demo":
            return jsonify({"symbol": symbol, "provider": "demo"})
        return jsonify(get_vnstock_market_cap(symbol))
    except Exception as error:
        return jsonify({"error": "Market cap lookup failed", "message": str(error)}), 502


@app.get("/sepa-score/<symbol>")
def sepa_score(symbol):
    auth_error = require_action_key()
    if auth_error:
        return auth_error

    symbol = normalize_symbol(symbol)
    try:
        price_data = get_price(symbol)
        fundamentals = get_vnstock_fundamental(symbol) if provider_mode() != "demo" else {"symbol": symbol}
        indicators = get_vnstock_indicators(symbol) if provider_mode() != "demo" else {"symbol": symbol}
        market_cap_data = get_vnstock_market_cap(symbol) if provider_mode() != "demo" else {"symbol": symbol}

        return jsonify(
            {
                "symbol": symbol,
                "score": calculate_sepa_score(price_data, fundamentals, indicators),
                "price": price_data,
                "fundamentals": fundamentals,
                "indicators": indicators,
                "marketCap": market_cap_data,
                "updatedAt": date.today().isoformat(),
            }
        )
    except Exception as error:
        return jsonify({"error": "SEPA score failed", "message": str(error)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")))
