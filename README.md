# Servejit AI Agent

An independent Python AI agent project designed for GitHub Codespaces and Android browser use.

## Included
- Python agent loop using Ollama's local-model API
- Playwright browser automation
- Website navigation, extraction, click and form-field fill
- SQLite task memory
- CSV, Excel, PDF, TXT and Markdown file reading
- Streamlit dashboard
- Safety checks for consequential actions
- No paid AI API is required

## Start in Codespaces

Open this repository in GitHub Codespaces, then run:

```bash
pip install -r requirements.txt
playwright install chromium
```

Install Ollama in the Codespace environment:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start Ollama in one terminal:

```bash
ollama serve
```

In another terminal:

```bash
ollama pull qwen2.5:3b
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Open forwarded port 8501.

## Android
Use Chrome on Android to open GitHub Codespaces and the Streamlit forwarded port. Browser automation runs in the Codespace, not directly inside the phone's Chrome browser.

## Important model note
A local Ollama model must run somewhere reachable by the Codespace. A model installed on a separate Windows PC or phone is not automatically reachable. Codespaces resources and free usage are limited; a 3B model may be slow or exceed available memory.

## Safety
Sign in manually for OTP, CAPTCHA and authentication. Never provide passwords, banking credentials or private tokens to the agent. Consequential actions must be reviewed and approved. This starter agent does not bypass site restrictions and cannot guarantee success on every website.
