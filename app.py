import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import streamlit as st

API_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
TERMINAL_TYPES = {"COMPLETE", "ERROR", "FAILED"}

st.set_page_config(
    page_title="TinyFish Web Agent",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .main .block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem;}
      div[data-testid="stMetric"] {background: rgba(120,120,120,.07); padding: 14px; border-radius: 12px;}
      .small-muted {color: #888; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "task_history" not in st.session_state:
    st.session_state.task_history = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_events" not in st.session_state:
    st.session_state.last_events = []

st.title("🐟 TinyFish Web Agent")
st.caption("Give an AI browser agent a website and a goal. Watch its progress and inspect the result.")

with st.sidebar:
    st.header("Connection")
    saved_key = ""
    try:
        saved_key = st.secrets.get("TINYFISH_API_KEY", "")
    except Exception:
        pass
    api_key = st.text_input(
        "TinyFish API key",
        value=saved_key,
        type="password",
        help="You can paste your key here, or store it as TINYFISH_API_KEY in Streamlit Secrets.",
        placeholder="Paste your TinyFish API key",
    )
    st.markdown(
        '<p class="small-muted">Your key is sent directly from this app to TinyFish over HTTPS. '
        'Do not paste it into code or commit it to GitHub.</p>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.subheader("How it works")
    st.write("1. Enter a public website URL.")
    st.write("2. Describe the task clearly.")
    st.write("3. Run the agent and follow its progress.")
    st.write("4. Review or download the returned data.")

def valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

def parse_json_maybe(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value

def extract_event_payload(line: str):
    line = line.strip()
    if not line or line.startswith(":") or not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"type": "MESSAGE", "message": raw}

def run_tinyfish(api_key: str, url: str, goal: str):
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {"url": url, "goal": goal}
    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        stream=True,
        timeout=(25, 600),
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:2000]
        raise RuntimeError(f"TinyFish returned HTTP {response.status_code}: {detail}")

    events = []
    final_event = None
    progress_box = st.empty()
    event_area = st.container()
    latest_status = "Connecting"
    progress_lines = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="replace")
        event = extract_event_payload(raw_line)
        if event is None:
            continue

        events.append(event)
        event_type = str(event.get("type") or event.get("event") or "UPDATE").upper()
        latest_status = event_type

        purpose = event.get("purpose") or event.get("message") or event.get("status")
        if purpose:
            progress_lines.append(f"**{event_type}:** {purpose}")
        elif event_type:
            progress_lines.append(f"**{event_type}**")

        live_url = event.get("streaming_url") or event.get("streamingUrl")
        if live_url:
            progress_lines.append(f"[Open live browser preview]({live_url})")

        progress_box.markdown("\n\n".join(progress_lines[-12:]))

        if event_type in TERMINAL_TYPES or (
            event_type == "COMPLETE" and event.get("status") == "COMPLETED"
        ):
            final_event = event
            # Some servers may send additional terminal metadata after COMPLETE.
            if event_type in {"ERROR", "FAILED"}:
                break

    response.close()
    return events, final_event

st.subheader("Create a task")
col1, col2 = st.columns([1, 1])
with col1:
    website_url = st.text_input(
        "Website URL",
        value="https://www.example.com",
        placeholder="https://example.com",
    )
with col2:
    task_label = st.text_input("Task name (optional)", placeholder="Example: Compare product prices")

goal = st.text_area(
    "What should the agent do?",
    height=160,
    placeholder=(
        "Example: Find the first 5 products on this page. Return their names, "
        "prices, ratings and product URLs as a JSON array. Do not purchase anything."
    ),
)

with st.expander("Tips for better results"):
    st.markdown(
        """
        - Be specific about what information to collect and the format you want.
        - For tables, ask for JSON with clear field names.
        - Tell the agent whether it should scroll or open detail pages.
        - Start with public pages. Login-protected websites may require separate credential/vault setup.
        - Do not ask it to make purchases, transfer money, submit sensitive information, or perform other irreversible actions.
        """
    )

run_col, clear_col = st.columns([1, 5])
with run_col:
    run_clicked = st.button("▶ Run agent", type="primary", use_container_width=True)
with clear_col:
    st.caption("Agent runs can take a little time. Keep this page open while the live stream is being read.")

if run_clicked:
    if not api_key.strip():
        st.error("Add your TinyFish API key in the sidebar first.")
    elif not valid_http_url(website_url):
        st.error("Enter a complete URL beginning with https:// or http://.")
    elif not goal.strip():
        st.error("Describe what you want the agent to do.")
    else:
        started_at = datetime.now(timezone.utc).isoformat()
        st.session_state.last_result = None
        st.session_state.last_events = []
        try:
            with st.status("Connecting to TinyFish…", expanded=True) as status:
                events, final_event = run_tinyfish(api_key.strip(), website_url.strip(), goal.strip())
                st.session_state.last_events = events
                if final_event:
                    status.update(label="Agent finished", state="complete", expanded=False)
                else:
                    status.update(label="Stream ended without a final COMPLETE event", state="error", expanded=True)

            result = None
            if final_event:
                result = (
                    final_event.get("resultJson")
                    if "resultJson" in final_event
                    else final_event.get("result")
                )
                if result is None:
                    result = final_event
                result = parse_json_maybe(result)

            record = {
                "task_name": task_label.strip() or goal.strip()[:60],
                "url": website_url.strip(),
                "goal": goal.strip(),
                "started_at": started_at,
                "events": events,
                "final_event": final_event,
                "result": result,
            }
            st.session_state.last_result = record
            st.session_state.task_history.insert(0, record)
            st.session_state.task_history = st.session_state.task_history[:20]

            if final_event:
                st.success("TinyFish returned a final event. Review the result below.")
            else:
                st.warning("The connection ended before a final event arrived. Check the event log below.")
        except requests.exceptions.Timeout:
            st.error("The request timed out. The browser task may still have run; try a shorter task or check TinyFish run history.")
        except requests.exceptions.RequestException as exc:
            st.error(f"Network error: {exc}")
        except Exception as exc:
            st.error(str(exc))

record = st.session_state.last_result
if record:
    st.divider()
    st.subheader("Latest result")
    a, b = st.columns(2)
    with a:
        st.metric("Events received", len(record.get("events", [])))
    with b:
        final = record.get("final_event") or {}
        st.metric("Final status", str(final.get("status") or final.get("type") or "No final event"))

    final = record.get("final_event") or {}
    live_url = final.get("streaming_url") or final.get("streamingUrl")
    if live_url:
        st.link_button("Open browser preview", live_url)

    result = record.get("result")
    if result is not None:
        st.markdown("#### Extracted data")
        if isinstance(result, (dict, list)):
            st.json(result, expanded=True)
            download_data = json.dumps(result, ensure_ascii=False, indent=2)
            st.download_button(
                "⬇ Download result as JSON",
                data=download_data,
                file_name="tinyfish_result.json",
                mime="application/json",
            )
            if isinstance(result, list) and result and all(isinstance(x, dict) for x in result):
                try:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(result), use_container_width=True)
                    st.download_button(
                        "⬇ Download result as CSV",
                        data=pd.DataFrame(result).to_csv(index=False).encode("utf-8"),
                        file_name="tinyfish_result.csv",
                        mime="text/csv",
                    )
                except Exception:
                    pass
        else:
            st.text_area("Result text", str(result), height=220)
            st.download_button(
                "⬇ Download result as TXT",
                data=str(result),
                file_name="tinyfish_result.txt",
                mime="text/plain",
            )

    with st.expander("Raw event log"):
        st.json(record.get("events", []), expanded=False)

if st.session_state.task_history:
    st.divider()
    st.subheader("Recent task history")
    for index, item in enumerate(st.session_state.task_history):
        final = item.get("final_event") or {}
        label = item.get("task_name", f"Task {index + 1}")
        state = final.get("status") or final.get("type") or "No final event"
        with st.expander(f"{label} — {state}"):
            st.write("**Website:**", item.get("url"))
            st.write("**Goal:**", item.get("goal"))
            if item.get("result") is not None:
                st.json(item["result"], expanded=False)

st.divider()
st.caption("TinyFish Web Agent • Streamlit interface • API key is not stored in the repository.")
