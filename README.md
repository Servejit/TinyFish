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


### Simplified stock output (latest update)
The Stock Buy / Sell Price Finder is now placed at the top of the app. Enter an NSE symbol and timeframe. It uses one TinyFish Search result and one focused browser run, then displays only **BUY PRICE** and **SELL PRICE** (or a no-reliable-setup message). The verbose strategy report and event log are no longer shown in this stock workflow. The original general-purpose TinyFish task runner remains below it.


## Comic E-book Studio (added)

The Streamlit app now includes a dedicated **Comic E-book Studio** while preserving the existing NSE stock tools and general-purpose TinyFish task runner.

### What it does
- Accepts any new e-book topic.
- Lets you choose the chapter count, target audience, language, illustration style and author name.
- Uses TinyFish Search to discover a suitable comic/storybook creation website.
- Sends a detailed comic publishing goal to the TinyFish Agent API.
- Requests original stories, illustrated comic pages, a professional cover and a complete PDF export.
- Displays the browser preview, run events, agent report and any PDF/cover URLs returned by the website.

### Important setup and limitations
- Uses the existing `TINYFISH_API_KEY` Streamlit Secret; no API key is hardcoded.
- TinyFish's Agent API starts a new run from a website URL and a natural-language goal. The Playground run URL is a run record, not a reusable agent identifier accepted by this API. The app therefore sends the reusable comic-book instructions with each new run.
- The website selected by TinyFish must actually support illustrated book creation and PDF export. Some sites require a user login, paid plan or credits. The app instructs the agent not to purchase, subscribe, spend credits or bypass access controls.
- A completed browser run does not guarantee that a PDF was created. Check the returned file links and the browser session. The app reports when no PDF link is returned.
- Generated content and artwork must be checked for quality and commercial-use licensing before selling.

### Use it
1. Deploy the updated `main` branch on Streamlit Community Cloud.
2. Keep your existing `TINYFISH_API_KEY` secret.
3. Open **Comic E-book Studio**.
4. Enter a topic, choose the settings and click **Create my comic e-book**.
5. Review the result and open the PDF link returned by the creation website.

## Optional Open-source Browser Agent (Browser Use + Groq)

The app includes a separate experimental browser workflow. It does not replace the existing TinyFish stock tools, Comic E-book Studio, or TinyFish general-purpose task runner.

### Setup

Add this secret in Streamlit Community Cloud → your app → Settings → Secrets:

    GROQ_API_KEY = "your_groq_api_key"

Never commit the key to GitHub or paste it into chat. The optional agent uses Browser Use with the Groq model `openai/gpt-oss-20b` and Playwright Chromium. It attempts to install Chromium on first use if the hosting environment permits it.

### Limitations

- This is an experimental open-source browser workflow, not a TinyFish run.
- It uses a headless browser on the Streamlit server; it does not open a controllable browser window on the phone.
- Login sessions and browser cookies are not saved between runs.
- Streamlit Community Cloud has resource and execution limits. Chromium may fail to install or launch if the free server lacks required system dependencies or memory.
- Groq free-tier access and rate limits can change. Rate-limit errors require waiting; the app does not fall back to a paid provider.
- The browser agent is instructed not to purchase, spend credits, publish, send messages, delete data, submit sensitive information, or bypass CAPTCHA, paywalls, or access controls.
- A completed browser run is not proof that a requested external action succeeded. Verify the reported result yourself.
