# TinyFish Streamlit Web Agent

A standalone Streamlit interface for running TinyFish browser-agent tasks.

## Features

- Enter a website URL and natural-language goal.
- Stream TinyFish Server-Sent Events (SSE) while the agent runs.
- Show progress messages and a browser preview URL when provided.
- Display returned JSON/text and download JSON, CSV, or TXT.
- Keep the latest 20 tasks in the current Streamlit session.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Paste your TinyFish API key into the sidebar.

## Deploy on Streamlit Community Cloud

1. Create a new public or private GitHub repository.
2. Upload `app.py`, `requirements.txt`, and this `README.md` to the repository root.
3. Open https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app**, select the repository, branch, and `app.py`.
5. In **Advanced settings → Secrets**, add:

```toml
TINYFISH_API_KEY = "your_tinyfish_api_key"
```

6. Deploy the app. Never commit your API key to GitHub.

You can also leave the secret unset and paste the key into the app sidebar at runtime.

## TinyFish API

The app uses the TinyFish Agent SSE endpoint:

`POST https://agent.tinyfish.ai/v1/automation/run-sse`

Authentication header: `X-API-Key`

Request body:

```json
{
  "url": "https://www.example.com",
  "goal": "Describe the website task here"
}
```

## Notes

- Agent tasks can take time; keep the Streamlit page open while the SSE response is being read.
- Task history is stored in Streamlit session state and is not a permanent database.
- Start with public websites. Login-protected workflows may require TinyFish Vault/credential configuration.
- Do not use browser automation to bypass access controls, CAPTCHAs, or website terms, or to make purchases or other irreversible actions without appropriate human review.
