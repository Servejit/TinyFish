import os
import streamlit as st
from agent import Agent
from memory import Memory
from files_tool import inspect_file

st.set_page_config(page_title="Servejit AI Agent", page_icon="🤖", layout="wide")
st.title("🤖 Servejit AI Agent")
st.caption("Your own Python agent • Browser automation • File analysis • Memory")

if "agent" not in st.session_state:
    st.session_state.agent = Agent()
if "memory" not in st.session_state:
    st.session_state.memory = Memory()
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Settings")
    ollama_url = st.text_input("Ollama URL", "http://127.0.0.1:11434")
    model = st.text_input("Model", "qwen2.5:3b")
    steps = st.slider("Maximum steps", 2, 12, 6)
    headless = st.checkbox("Run browser in background", True)
    allow_actions = st.checkbox("Allow consequential actions", False)
    st.caption("Keep consequential actions disabled unless you have checked the page and intend to proceed.")
    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()
    if st.button("Close browser"):
        st.session_state.agent.close()
        st.success("Browser closed.")

chat_tab, file_tab, memory_tab, setup_tab = st.tabs(["Agent", "Files", "Memory", "Setup"])

with chat_tab:
    task = st.text_area("What should the agent do?", height=120, placeholder="Example: Open https://example.com and summarize the page.")
    start_url = st.text_input("Starting URL (optional)", placeholder="https://example.com")
    if st.button("Run agent", type="primary"):
        if not task.strip():
            st.warning("Enter a task first.")
        else:
            prompt = task.strip()
            if start_url.strip():
                prompt += "\nStart by opening " + start_url.strip()
            with st.spinner("Agent is working..."):
                try:
                    result = st.session_state.agent.run(prompt, ollama_url, model, steps, headless, allow_actions, st.session_state.memory)
                    st.session_state.history.append({"task": task, "answer": result["answer"], "log": result["log"]})
                    st.markdown("### Result")
                    st.write(result["answer"])
                    with st.expander("Execution log", expanded=True):
                        for item in result["log"]:
                            st.markdown("**Step " + str(item["step"]) + ": " + item["action"] + "**")
                            st.write(item["detail"])
                except Exception as exc:
                    st.error(str(exc))
    for item in reversed(st.session_state.history[-10:]):
        with st.expander(item["task"][:100]):
            st.write(item["answer"])

with file_tab:
    upload = st.file_uploader("Upload CSV, Excel, PDF, TXT or Markdown", type=["csv", "xlsx", "xls", "pdf", "txt", "md"])
    if upload:
        try:
            data = inspect_file(upload)
            st.subheader(upload.name)
            st.text_area("Extracted content", data["text"], height=280)
            if data["table"] is not None:
                st.dataframe(data["table"], use_container_width=True)
            st.download_button("Download extracted text", data["text"], file_name=upload.name + ".txt")
        except Exception as exc:
            st.error("File error: " + str(exc))

with memory_tab:
    st.subheader("Saved task memory")
    records = st.session_state.memory.list_recent()
    if not records:
        st.info("No saved tasks yet.")
    for record in records:
        with st.expander(record["created"] + " — " + record["task"][:80]):
            st.write(record["result"])
    if st.button("Delete agent memory"):
        st.session_state.memory.clear()
        st.rerun()

with setup_tab:
    st.subheader("Run in GitHub Codespaces")
    st.code("pip install -r requirements.txt\nplaywright install chromium\nollama serve\nollama pull qwen2.5:3b\nstreamlit run app.py --server.address 0.0.0.0 --server.port 8501", language="bash")
    st.info("Ollama must be reachable from the Codespace. A model running only on your personal phone is not automatically accessible to the Codespace.")
    st.warning("Sign in manually for OTP/CAPTCHA. Never give the agent passwords, banking credentials or private tokens. Payments, purchases, sending, deleting and final submissions require explicit approval.")
