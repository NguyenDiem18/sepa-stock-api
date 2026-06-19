import cors from "cors";
import express from "express";

const app = express();
const port = Number(process.env.PORT || 3000);

app.use(cors());
app.use(express.json());

function normalizeSymbol(rawSymbol) {
  return String(rawSymbol || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9._-]/g, "");
}

function requireApiKey(req, res, next) {
  const configuredKey = process.env.ACTION_API_KEY;

  if (!configuredKey) {
    return next();
  }

  const authHeader = req.get("authorization") || "";
  const bearerToken = authHeader.replace(/^Bearer\s+/i, "");
  const queryToken = req.query.api_key;

  if (bearerToken === configuredKey || queryToken === configuredKey) {
    return next();
  }

  return res.status(401).json({
    error: "Unauthorized",
    message: "Missing or invalid API key"
  });
}

function demoPrice(symbol) {
  const base = [...symbol].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const price = 10000 + (base % 250) * 120;
  const change = ((base % 21) - 10) * 10;
  const changePercent = Number(((change / price) * 100).toFixed(2));

  return {
    symbol,
    exchange: "DEMO",
    price,
    change,
    changePercent,
    volume: 1000000 + (base % 1000) * 900,
    updatedAt: new Date().toISOString(),
    provider: "demo"
  };
}

function demoHistory(symbol) {
  const today = new Date();
  const seed = [...symbol].reduce((sum, char) => sum + char.charCodeAt(0), 0);

  return {
    symbol,
    timeframe: "daily",
    candles: Array.from({ length: 60 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (59 - index));

      const close = 10000 + seed * 8 + index * 45 + Math.sin(index / 3) * 350;
      const open = close - Math.sin(index / 2) * 160;
      const high = Math.max(open, close) + 220;
      const low = Math.min(open, close) - 180;

      return {
        date: date.toISOString().slice(0, 10),
        open: Math.round(open),
        high: Math.round(high),
        low: Math.round(low),
        close: Math.round(close),
        volume: 800000 + index * 12000
      };
    }),
    provider: "demo"
  };
}

function demoFundamental(symbol) {
  return {
    symbol,
    pe: 14.2,
    pb: 2.1,
    roe: 18.4,
    roa: 2.7,
    eps: 4250,
    revenueGrowth: 11.8,
    profitGrowth: 15.3,
    debtToEquity: 0.62,
    provider: "demo"
  };
}

function demoFinancialIndicators(symbol) {
  return {
    symbol,
    trend: {
      ema20: 24780,
      ema50: 23920,
      ema200: 21840,
      relativeStrength: 72
    },
    volatility: {
      atr14: 530,
      beta: 1.08
    },
    liquidity: {
      averageVolume20: 1850000,
      turnover20: 46200000000
    },
    provider: "demo"
  };
}

function demoMarketCap(symbol) {
  return {
    symbol,
    marketCap: 12500000000000,
    freeFloatMarketCap: 8100000000000,
    sharesOutstanding: 500000000,
    currency: "VND",
    provider: "demo"
  };
}

function calculateSepaScore(price, fundamentals, indicators) {
  const trendScore = price.price > indicators.trend.ema50 ? 25 : 12;
  const growthScore = fundamentals.profitGrowth >= 10 ? 25 : 10;
  const qualityScore = fundamentals.roe >= 15 && fundamentals.debtToEquity <= 1 ? 25 : 12;
  const liquidityScore = indicators.liquidity.averageVolume20 >= 1000000 ? 25 : 12;
  const total = trendScore + growthScore + qualityScore + liquidityScore;

  return {
    total,
    rating: total >= 80 ? "pass" : total >= 60 ? "watchlist" : "fail",
    components: {
      trendScore,
      growthScore,
      qualityScore,
      liquidityScore
    },
    notes: [
      "Demo scoring only. Replace the data provider with licensed market data before using for real analysis.",
      "This API does not provide investment advice."
    ]
  };
}

async function fetchCustomProvider(path, symbol) {
  const baseUrl = process.env.MARKET_DATA_BASE_URL;

  if (!baseUrl) {
    throw new Error("MARKET_DATA_BASE_URL is required when DATA_PROVIDER=custom");
  }

  const url = new URL(`${baseUrl.replace(/\/$/, "")}/${path}/${symbol}`);
  const headers = {
    accept: "application/json"
  };

  if (process.env.MARKET_DATA_API_KEY) {
    headers.authorization = `Bearer ${process.env.MARKET_DATA_API_KEY}`;
  }

  const response = await fetch(url, { headers });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Provider error ${response.status}: ${body.slice(0, 300)}`);
  }

  return response.json();
}

async function getProviderData(path, symbol) {
  if (process.env.DATA_PROVIDER === "custom") {
    return fetchCustomProvider(path, symbol);
  }

  const handlers = {
    price: demoPrice,
    history: demoHistory,
    fundamental: demoFundamental,
    "financial-indicators": demoFinancialIndicators,
    "market-cap": demoMarketCap
  };

  return handlers[path](symbol);
}

async function handleProviderRoute(req, res, path) {
  try {
    const symbol = normalizeSymbol(req.params.symbol);

    if (!symbol) {
      return res.status(400).json({
        error: "Bad Request",
        message: "Symbol is required"
      });
    }

    const data = await getProviderData(path, symbol);
    return res.json(data);
  } catch (error) {
    return res.status(502).json({
      error: "Market data provider failed",
      message: error.message
    });
  }
}

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    provider: process.env.DATA_PROVIDER || "demo",
    updatedAt: new Date().toISOString()
  });
});

app.get("/price/:symbol", requireApiKey, (req, res) => handleProviderRoute(req, res, "price"));
app.get("/history/:symbol", requireApiKey, (req, res) => handleProviderRoute(req, res, "history"));
app.get("/fundamental/:symbol", requireApiKey, (req, res) => handleProviderRoute(req, res, "fundamental"));
app.get("/financial-indicators/:symbol", requireApiKey, (req, res) => handleProviderRoute(req, res, "financial-indicators"));
app.get("/market-cap/:symbol", requireApiKey, (req, res) => handleProviderRoute(req, res, "market-cap"));

app.get("/sepa-score/:symbol", requireApiKey, async (req, res) => {
  try {
    const symbol = normalizeSymbol(req.params.symbol);

    if (!symbol) {
      return res.status(400).json({
        error: "Bad Request",
        message: "Symbol is required"
      });
    }

    const [price, fundamentals, indicators, marketCap] = await Promise.all([
      getProviderData("price", symbol),
      getProviderData("fundamental", symbol),
      getProviderData("financial-indicators", symbol),
      getProviderData("market-cap", symbol)
    ]);

    return res.json({
      symbol,
      score: calculateSepaScore(price, fundamentals, indicators),
      price,
      fundamentals,
      indicators,
      marketCap,
      updatedAt: new Date().toISOString()
    });
  } catch (error) {
    return res.status(502).json({
      error: "SEPA score failed",
      message: error.message
    });
  }
});

app.listen(port, () => {
  console.log(`SEPA stock API listening on port ${port}`);
});
