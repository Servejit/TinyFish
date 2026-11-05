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


def render_stock_strategy_builder(api_key):
    st.divider()
    st.header("📈 NSE Stock Strategy Builder")
    st.caption("Research trading ideas with TinyFish, turn them into explicit rules, then test rule-based templates on your own OHLC CSV.")
    research_tab, backtest_tab, guide_tab = st.tabs(["Strategy Research", "CSV Backtest Lab", "How to use"])

    with research_tab:
        st.subheader("Build a strategy from your idea")
        idea = st.text_area(
            "Describe your trading idea",
            height=120,
            placeholder="Example: Find a 5-minute intraday bullish strategy using Ichimoku Kijun, Alligator and price action. I want clear entry, exit and risk rules.",
            key="stock_strategy_idea",
        )
        c1, c2, c3 = st.columns(3)
        market = c1.selectbox("Market", ["NSE India", "BSE India", "US stocks", "Crypto"], key="sb_market")
        timeframe = c2.selectbox("Timeframe", ["1-minute", "3-minute", "5-minute", "15-minute", "30-minute", "1-hour", "Daily", "Swing / multi-day"], index=2, key="sb_tf")
        style = c3.selectbox("Trading style", ["Intraday", "Scalping", "Swing", "Positional"], key="sb_style")
        with st.expander("Optional strategy constraints"):
            indicators = st.text_input("Preferred indicators / concepts", "Price action, volume, Ichimoku, Alligator, Bollinger Bands", key="sb_indicators")
            risk = st.selectbox("Risk preference", ["Conservative", "Balanced", "Aggressive"], index=1, key="sb_risk")
            avoid = st.text_input("Conditions to avoid", "Look-ahead bias, repainting signals, unsupported claims", key="sb_avoid")
        if st.button("🔎 Research and build strategy", type="primary", use_container_width=True, key="sb_research"):
            if not api_key or not str(api_key).strip():
                st.error("Add your TinyFish API key in the Connection section of the sidebar.")
            elif not idea.strip():
                st.error("Describe the trading idea first.")
            else:
                try:
                    query = f"{market} {timeframe} {style} stock trading strategy {indicators} backtesting rules risk management"
                    with st.status("Researching strategy sources…", expanded=True) as status:
                        sources = _search_stock_sources(api_key.strip(), query)
                        if not sources:
                            raise RuntimeError("TinyFish Search returned no usable source URLs. Try a broader strategy description.")
                        st.write(f"Found {len(sources)} source pages. Starting TinyFish research on {sources[0]['url']}")
                        goal = f"""Act as a rigorous quantitative trading strategy researcher. Develop a testable strategy, not a trading recommendation.

USER IDEA: {idea}
MARKET: {market}
TIMEFRAME: {timeframe}
STYLE: {style}
PREFERRED CONCEPTS: {indicators}
RISK PREFERENCE: {risk}
AVOID: {avoid}

Research the current page and follow relevant credible references where possible. Prefer exchange/regulator/official documentation and established educational sources. Distinguish verified facts from hypotheses. Do not invent backtest statistics or claim profitability.

Return a well-structured strategy report with:
1. Strategy name and concise thesis.
2. Exact instruments/universe assumptions and market-session constraints.
3. Indicators with exact parameters and formulas.
4. Entry conditions as numbered AND/OR rules that can be coded without interpretation.
5. Exit conditions, stop-loss, position sizing and maximum risk per trade.
6. Filters and no-trade conditions.
7. Execution timing: signal candle vs next candle, avoiding look-ahead/repainting.
8. Suggested validation: out-of-sample, walk-forward, transaction costs, slippage, sample size.
9. Failure modes, market regimes where it may underperform, and risks.
10. A pseudocode block.
11. Sources with page title and exact URL; label any claim that could not be independently verified.

Do not place trades, give guaranteed-return language, or present this as personalized financial advice."""
                        progress = st.empty()
                        result, events = _run_stock_research(api_key.strip(), sources[0]["url"], goal, progress)
                        status.update(label="Strategy research finished", state="complete", expanded=False)
                    st.session_state["stock_strategy_result"] = {
                        "idea": idea, "market": market, "timeframe": timeframe, "style": style,
                        "sources": sources, "result": result, "events": events,
                        "created": datetime.now(timezone.utc).isoformat(),
                    }
                except Exception as exc:
                    st.error(f"Strategy research failed: {exc}")

        report = st.session_state.get("stock_strategy_result")
        if report:
            st.markdown("### Strategy research report")
            st.caption(f"{report['market']} · {report['timeframe']} · {report['style']} · {report['created']}")
            result = report["result"]
            if isinstance(result, (dict, list)):
                st.json(result, expanded=True)
                download_text = json.dumps(result, ensure_ascii=False, indent=2)
            else:
                st.markdown(str(result))
                download_text = str(result)
            st.download_button("Download strategy report", download_text, file_name="stock_strategy_report.md", mime="text/markdown", key="sb_download")
            with st.expander("Research pages found"):
                for source in report["sources"]:
                    label = source["title"] or source["url"]
                    st.markdown(f"- [{label}]({source['url']}) — {source['snippet']}")
            with st.expander("TinyFish event log"):
                st.json(report["events"], expanded=False)

    with backtest_tab:
        st.subheader("Test a strategy on historical OHLC data")
        st.info("Upload a CSV exported from your data provider. This lab tests the selected built-in rule set; it does not automatically translate a TinyFish research report into executable code.")
        uploaded = st.file_uploader("Upload OHLC CSV", type=["csv"], key="sb_csv")
        a, b, c = st.columns(3)
        strategy = a.selectbox("Strategy template", ["SMA crossover", "EMA crossover", "RSI mean reversion", "Bollinger mean reversion", "Donchian breakout"], key="sb_template")
        fast = b.number_input("Fast / RSI period", min_value=2, max_value=100, value=14, key="sb_fast")
        slow = c.number_input("Slow / band / breakout period", min_value=5, max_value=250, value=50, key="sb_slow")
        d, e = st.columns(2)
        rsi_low = d.slider("RSI entry threshold", 5, 45, 30, key="sb_rsi_low")
        rsi_high = e.slider("RSI exit threshold", 50, 95, 60, key="sb_rsi_high")
        fee_bps = st.number_input("Estimated transaction cost per side (basis points)", min_value=0.0, max_value=200.0, value=5.0, step=0.5, key="sb_fee")
        if uploaded is not None and st.button("▶ Run backtest", type="primary", use_container_width=True, key="sb_run_bt"):
            try:
                raw = pd.read_csv(uploaded)
                clean = _clean_ohlcv(raw)
                if strategy in ("SMA crossover", "EMA crossover") and fast >= slow:
                    raise ValueError("For crossover strategies, Fast period must be smaller than Slow period.")
                if strategy == "RSI mean reversion" and rsi_low >= rsi_high:
                    raise ValueError("RSI entry threshold must be below exit threshold.")
                results, metrics = _backtest(clean, strategy, int(fast), int(slow), int(rsi_low), int(rsi_high), float(fee_bps))
                st.session_state["stock_backtest_result"] = (results, metrics, strategy)
            except Exception as exc:
                st.error(f"Backtest could not run: {exc}")
        bt = st.session_state.get("stock_backtest_result")
        if bt:
            results, metrics, used_strategy = bt
            st.markdown(f"### Results — {used_strategy}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Strategy return", f"{metrics['Strategy return']:.2%}")
            m2.metric("Buy & hold", f"{metrics['Buy & hold']:.2%}")
            m3.metric("Max drawdown", f"{metrics['Max drawdown']:.2%}")
            m4.metric("Win rate", f"{metrics['Win rate']:.1%}")
            m5, m6, m7 = st.columns(3)
            m5.metric("Closed trades", str(metrics["Closed trades"]))
            pf = metrics["Profit factor"]
            m6.metric("Profit factor", "∞" if math.isinf(pf) else f"{pf:.2f}")
            m7.metric("Sharpe (252-bar)", f"{metrics['Sharpe (252-bar)']:.2f}")
            chart = results[["equity", "buy_hold"]].rename(columns={"equity": "Strategy equity", "buy_hold": "Buy & hold"})
            st.line_chart(chart)
            st.caption("Signals execute on the next bar. Costs are deducted on position changes. Results are historical simulations, not predictions; actual fills, taxes, slippage and corporate actions may differ.")
            export = results.reset_index().to_csv(index=False)
            st.download_button("Download backtest results CSV", export, file_name="stock_strategy_backtest.csv", mime="text/csv", key="sb_bt_download")

    with guide_tab:
        st.markdown("""
### CSV format
Your file should contain at least these columns: `Open`, `High`, `Low`, `Close`. A `Date` or `Datetime` column is recommended. `Volume` is optional.

### Included templates
- **SMA / EMA crossover:** long when fast average is above slow average.
- **RSI mean reversion:** enter after RSI falls below the entry threshold; exit after it rises above the exit threshold.
- **Bollinger mean reversion:** enter below the lower 2-standard-deviation band; exit at the middle band.
- **Donchian breakout:** enter above the prior rolling high; exit below the prior rolling low.

### Important limitations
This is a research and paper-testing tool, not an order execution system. It does not connect to a broker. The included backtest is long-only and simplified; it does not model intrabar stop fills, market impact, taxes, circuit limits, survivorship bias or corporate actions. Test with out-of-sample data and realistic slippage before considering live use.
""")
