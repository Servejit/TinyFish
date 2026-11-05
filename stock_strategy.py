import json
import math
import re
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

SEARCH_URL = "https://api.search.tinyfish.ai"
AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"


def _valid_url(url):
    return isinstance(url, str) and url.startswith(("https://", "http://"))


def _search_stock_sources(api_key, query):
    response = requests.get(
        SEARCH_URL,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        params={"query": query},
        timeout=35,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"TinyFish Search HTTP {response.status_code}: {response.text[:900]}")
    payload = response.json()
    results = []
    seen = set()

    def walk(value):
        if isinstance(value, dict):
            url = value.get("url") or value.get("link") or value.get("href")
            if _valid_url(url):
                url = url.rstrip("/")
                if url not in seen:
                    seen.add(url)
                    results.append({
                        "url": url,
                        "title": str(value.get("title") or value.get("name") or "")[:240],
                        "snippet": str(value.get("snippet") or value.get("description") or value.get("content") or "")[:500],
                    })
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    preferred = ("nseindia.com", "bseindia.com", "sebi.gov.in", "zerodha.com/varsity",
                 "tradingview.com", "screener.in", "investopedia.com")
    results.sort(key=lambda x: sum(domain in x["url"].lower() for domain in preferred), reverse=True)
    return results[:8]


def _run_stock_research(api_key, url, goal, progress):
    response = requests.post(
        AGENT_URL,
        headers={"X-API-Key": api_key, "Content-Type": "application/json", "Accept": "text/event-stream"},
        json={"url": url, "goal": goal},
        stream=True,
        timeout=(20, 600),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"TinyFish Agent HTTP {response.status_code}: {response.text[:1200]}")
    events, final = [], None
    lines = []
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if not raw.startswith("data:"):
                continue
            raw = raw[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                event = {"message": raw}
            events.append(event)
            kind = str(event.get("type") or event.get("event") or "UPDATE").upper()
            detail = event.get("purpose") or event.get("message") or event.get("status") or ""
            lines.append(f"**{kind}:** {detail}" if detail else f"**{kind}**")
            progress.markdown("\n\n".join(lines[-12:]))
            if kind in ("COMPLETE", "FAILED", "ERROR"):
                final = event
                if kind in ("FAILED", "ERROR"):
                    break
    finally:
        response.close()
    if final is None:
        raise RuntimeError("TinyFish stream ended without a final event. Check the TinyFish run history.")
    status = str(final.get("status") or final.get("type") or "").upper()
    if status in ("FAILED", "ERROR"):
        raise RuntimeError(str(final.get("error") or final))
    result = final.get("resultJson")
    if result is None:
        result = final.get("result")
    if result is None:
        result = final
    return result, events


def _clean_ohlcv(frame):
    frame = frame.copy()
    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    aliases = {"datetime": "date", "timestamp": "date", "adj_close": "close", "adjclose": "close"}
    frame = frame.rename(columns={k: v for k, v in aliases.items() if k in frame.columns and v not in frame.columns})
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError("CSV must contain Open, High, Low and Close columns. Missing: " + ", ".join(missing))
    for col in required + (["volume"] if "volume" in frame.columns else []):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=required)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        frame = frame.set_index("date")
    else:
        frame = frame.reset_index(drop=True)
    if len(frame) < 30:
        raise ValueError("Please upload at least 30 valid OHLC rows.")
    return frame


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _backtest(frame, strategy, fast, slow, rsi_low, rsi_high, fee_bps):
    data = frame.copy()
    close = data["close"]
    if strategy == "SMA crossover":
        data["fast"] = close.rolling(fast).mean()
        data["slow"] = close.rolling(slow).mean()
        signal = (data["fast"] > data["slow"]).astype(int)
    elif strategy == "EMA crossover":
        data["fast"] = close.ewm(span=fast, adjust=False).mean()
        data["slow"] = close.ewm(span=slow, adjust=False).mean()
        signal = (data["fast"] > data["slow"]).astype(int)
    elif strategy == "RSI mean reversion":
        rsi = _rsi(close, fast)
        # Long while RSI has recovered above the lower threshold; exit above upper threshold.
        signal = pd.Series(index=data.index, dtype=float)
        state = 0
        for i, value in enumerate(rsi):
            if pd.isna(value):
                signal.iloc[i] = state
                continue
            if state == 0 and value < rsi_low:
                state = 1
            elif state == 1 and value > rsi_high:
                state = 0
            signal.iloc[i] = state
        data["rsi"] = rsi
    elif strategy == "Bollinger mean reversion":
        mid = close.rolling(slow).mean()
        sd = close.rolling(slow).std()
        lower, upper = mid - 2 * sd, mid + 2 * sd
        signal = pd.Series(index=data.index, dtype=float)
        state = 0
        for i, (price, lo, hi) in enumerate(zip(close, lower, upper)):
            if not pd.isna(lo) and state == 0 and price < lo:
                state = 1
            elif not pd.isna(hi) and state == 1 and price >= mid.iloc[i]:
                state = 0
            signal.iloc[i] = state
        data["bb_mid"], data["bb_lower"], data["bb_upper"] = mid, lower, upper
    else:  # Donchian breakout
        prior_high = data["high"].rolling(slow).max().shift(1)
        prior_low = data["low"].rolling(slow).min().shift(1)
        signal = pd.Series(index=data.index, dtype=float)
        state = 0
        for i, (price, hi, lo) in enumerate(zip(close, prior_high, prior_low)):
            if not pd.isna(hi) and state == 0 and price > hi:
                state = 1
            elif not pd.isna(lo) and state == 1 and price < lo:
                state = 0
            signal.iloc[i] = state

    data["signal"] = pd.Series(signal, index=data.index).fillna(0).astype(int)
    # Signal is acted on at the next bar to avoid using the current bar's close for its own return.
    data["position"] = data["signal"].shift(1).fillna(0)
    turnover = data["position"].diff().abs().fillna(data["position"].abs())
    cost = fee_bps / 10000.0
    data["market_return"] = close.pct_change().fillna(0)
    data["strategy_return"] = data["position"] * data["market_return"] - turnover * cost
    data["equity"] = (1 + data["strategy_return"]).cumprod()
    data["buy_hold"] = (1 + data["market_return"]).cumprod()
    data["drawdown"] = data["equity"] / data["equity"].cummax() - 1

    entries = (data["position"].diff().fillna(data["position"]) > 0)
    exits = (data["position"].diff().fillna(0) < 0)
    entry_prices = close[entries].tolist()
    exit_prices = close[exits].tolist()
    trade_returns = []
    entry_idx = 0
    for exit_price in exit_prices:
        if entry_idx < len(entry_prices):
            entry_price = entry_prices[entry_idx]
            if entry_price:
                trade_returns.append(exit_price / entry_price - 1 - 2 * cost)
            entry_idx += 1
    if len(entry_prices) > len(exit_prices) and entry_prices:
        trade_returns.append(close.iloc[-1] / entry_prices[-1] - 1 - 2 * cost)

    total_return = data["equity"].iloc[-1] - 1
    bh_return = data["buy_hold"].iloc[-1] - 1
    max_dd = data["drawdown"].min()
    daily_std = data["strategy_return"].std()
    sharpe = (data["strategy_return"].mean() / daily_std * math.sqrt(252)) if daily_std and not pd.isna(daily_std) else 0.0
    wins = sum(x > 0 for x in trade_returns)
    gross_profit = sum(x for x in trade_returns if x > 0)
    gross_loss = abs(sum(x for x in trade_returns if x < 0))
    metrics = {
        "Strategy return": total_return,
        "Buy & hold": bh_return,
        "Max drawdown": max_dd,
        "Win rate": wins / len(trade_returns) if trade_returns else 0,
        "Closed trades": len(trade_returns),
        "Profit factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0),
        "Sharpe (252-bar)": sharpe,
    }
    return data, metrics


def _extract_trade_levels(result):
    """Extract only verified buy and sell prices from TinyFish's final result."""
    if isinstance(result, dict):
        def find_value(obj, keys):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if str(key).lower().replace(" ", "_") in keys and value not in (None, ""):
                        return value
                for value in obj.values():
                    found = find_value(value, keys)
                    if found not in (None, ""):
                        return found
            elif isinstance(obj, list):
                for value in obj:
                    found = find_value(value, keys)
                    if found not in (None, ""):
                        return found
            return None

        buy = find_value(result, {"buy_price", "entry_price", "buy", "entry"})
        sell = find_value(result, {"sell_price", "target_price", "sell", "target", "exit_price"})
        status = find_value(result, {"signal", "recommendation", "status", "trade_status"})
        return buy, sell, status

    text_value = str(result or "")
    # Prefer JSON embedded in a text response.
    match = re.search(r"\{[\s\S]*\}", text_value)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return _extract_trade_levels(parsed)
        except Exception:
            pass

    buy_match = re.search(r"(?:buy(?:_price)?|entry(?:_price)?)\s*[:=]\s*(?:₹|INR\s*)?([0-9]+(?:\.[0-9]+)?)", text_value, re.I)
    sell_match = re.search(r"(?:sell(?:_price)?|target(?:_price)?|exit(?:_price)?)\s*[:=]\s*(?:₹|INR\s*)?([0-9]+(?:\.[0-9]+)?)", text_value, re.I)
    return (
        buy_match.group(1) if buy_match else None,
        sell_match.group(1) if sell_match else None,
        None,
    )


def render_stock_strategy_builder(api_key):
    st.divider()
    st.header("📈 Stock Buy / Sell Price Finder")
    st.caption("Enter an NSE stock. Get only the suggested buy-entry and sell-target prices.")

    stock = st.text_input(
        "Stock name or NSE symbol",
        placeholder="Example: RELIANCE, HDFCBANK, TCS",
        key="sb_stock_symbol",
    ).strip().upper()

    timeframe = st.selectbox(
        "Trading timeframe",
        ["3-minute", "5-minute", "15-minute", "1-hour", "Daily"],
        index=1,
        key="sb_quick_timeframe",
    )

    if st.button("Find buy and sell prices", type="primary", use_container_width=True, key="sb_quick_run"):
        if not api_key or not str(api_key).strip():
            st.error("Add your TinyFish API key in the sidebar.")
        elif not stock:
            st.error("Enter a stock name or NSE symbol.")
        else:
            try:
                query = f"{stock} NSE India latest share price {timeframe} technical entry target price"
                with st.spinner("Checking stock data and calculating levels…"):
                    sources = _search_stock_sources(api_key.strip(), query)
                    if not sources:
                        raise RuntimeError("No stock-data page was found. Check the symbol and try again.")

                    # Use only the highest-ranked search result to reduce browser navigation time.
                    source = sources[0]
                    goal = f"""You are a fast Indian stock-market price-level assistant.

Stock: {stock} (NSE India)
Trading timeframe: {timeframe}

Use ONLY this page and the minimum navigation needed to verify the latest available stock price and relevant technical data. Do not browse unrelated pages, write an essay, or provide general education.

Determine one technically justified BUY ENTRY PRICE and one SELL TARGET PRICE for this stock and timeframe. Use the page's actual current/latest data. Do not invent live prices, indicators, support/resistance, or calculations. If the page does not provide enough reliable data to calculate both prices, return null for the unavailable price.

Return ONLY valid JSON, with no markdown and no explanation:
{{
  "stock": "{stock}",
  "buy_price": number_or_null,
  "sell_price": number_or_null,
  "signal": "BUY" or "WAIT",
  "data_as_of": "date/time shown by source or unavailable"
}}

Rules:
- Prices must be numeric INR values, not percentages.
- buy_price is the proposed entry price, not just the current market price unless that is genuinely the entry.
- sell_price is the proposed exit/target price above the buy price for a long trade.
- If no reliable setup exists, use null for both prices and signal WAIT.
- Never guarantee profit. Never place an order.
- Finish as soon as these four fields are determined."""

                    progress = st.empty()
                    progress.caption("TinyFish is checking one source…")
                    result, events = _run_stock_research(api_key.strip(), source["url"], goal, progress)
                    buy, sell, signal = _extract_trade_levels(result)
                    st.session_state["stock_quick_result"] = {
                        "stock": stock,
                        "timeframe": timeframe,
                        "buy": buy,
                        "sell": sell,
                        "signal": signal,
                        "source": source["url"],
                        "raw": result,
                        "checked": datetime.now(timezone.utc).isoformat(),
                    }
            except Exception as exc:
                st.error(f"Could not calculate prices: {exc}")

    result = st.session_state.get("stock_quick_result")
    if result:
        st.divider()
        st.subheader(result["stock"])
        if result["buy"] is not None and result["sell"] is not None:
            buy_col, sell_col = st.columns(2)
            buy_col.metric("BUY PRICE", f"₹{result['buy']}")
            sell_col.metric("SELL PRICE", f"₹{result['sell']}")
        else:
            st.warning("No reliable buy/sell setup was returned. Try again later or use a different timeframe.")
        st.caption(f"Timeframe: {result['timeframe']} · Signal: {result['signal'] or 'Not confirmed'}")
        st.caption("Prices are research estimates, not guaranteed execution prices. Verify the live NSE quote before placing any trade.")
        with st.expander("Source"):
            st.write(result["source"])
