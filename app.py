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
