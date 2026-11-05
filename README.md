# TinyFish Autonomous Agent

A Streamlit app that accepts a natural-language task, discovers a suitable website with TinyFish Search, then runs TinyFish Agent on the selected website.

## What changed

- No website URL is required for normal tasks.
- Describe the desired outcome in plain English.
- The app searches for candidate websites automatically.
- It selects a candidate and starts TinyFish browser automation.
- Optional manual website override remains available under Advanced options.
- Includes a text-to-video workflow: describe the video you want and the agent searches for a suitable generator, then attempts the browser workflow.
- Shows browser progress, preview URL when supplied, final result, candidate websites and event log.

## How the routing works

TinyFish Search is used to discover possible websites. The app ranks the returned candidates using task-intent keywords and selects the top candidate. TinyFish Agent then receives that URL and a detailed natural-language goal.

This is search-assisted autonomous routing. It is not a separate general-purpose LLM planner: TinyFish Agent performs the reasoning and actions on the selected website. Search and Fetch are documented as free; Agent/browser automation is metered by TinyFish.

## Deploy on Streamlit Community Cloud

The existing deployment can be updated by pushing these files to the same GitHub repository. Your existing Streamlit app and Secrets should remain in place.

Required Streamlit Secret:

~~~toml
TINYFISH_API_KEY = "your_tinyfish_api_key"
~~~

Never commit the API key to GitHub.

## Run locally

~~~bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
~~~

## TinyFish APIs used

Search:
https://api.search.tinyfish.ai?query=...

Agent SSE:
https://agent.tinyfish.ai/v1/automation/run-sse

Both use the X-API-Key header. The Agent endpoint requires a starting URL, which is why the app searches first.

## Safety

- The agent is instructed not to purchase, subscribe, start paid trials, spend credits, publish publicly, send messages, delete data, or submit sensitive information.
- If a site requires one of those actions, the agent should stop and ask the user to complete/confirm it manually.
- The agent must not bypass CAPTCHA, access controls, paywalls, or website security.
- Generated video availability, download links, free usage and watermarks depend on the selected third-party website.
- Search-assisted routing is heuristic. If the wrong site is selected, use the optional website override.
- Recent task history is stored only in Streamlit session state and is not a permanent database.


## NSE Stock Strategy Builder (added)

The Streamlit app now includes a dedicated **NSE Stock Strategy Builder** section while retaining the original general-purpose TinyFish agent.

### Strategy Research
- Describe a trading idea in plain English.
- Choose market, timeframe and trading style.
- TinyFish Search discovers relevant source pages, then TinyFish Agent researches the selected page.
- The report asks for exact entry/exit rules, indicators, risk management, execution timing, validation steps, failure modes and source URLs.
- Download the resulting strategy report.

### CSV Backtest Lab
- Upload historical OHLC CSV data with Open, High, Low and Close columns.
- Test SMA crossover, EMA crossover, RSI mean reversion, Bollinger mean reversion or Donchian breakout templates.
- Configure periods, RSI thresholds and estimated transaction costs.
- Review strategy return, buy-and-hold return, drawdown, win rate, trade count, profit factor, Sharpe estimate and equity curve.
- Download the backtest results as CSV.

The backtest is a simplified long-only historical simulation. Signals are acted on at the next bar to reduce look-ahead bias. It is not broker-connected and does not model all real-world costs or execution constraints. TinyFish Agent/browser runs may be metered; check your TinyFish plan before running repeated research.
