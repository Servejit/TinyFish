"""Servejit Browser Agent — Browser Use + Groq only. No TinyFish dependency."""
import streamlit as st
from browser_agent import render_browser_use_agent

st.set_page_config(
    page_title="Servejit Browser Agent",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .main .block-container {max-width: 1100px; padding-top: 2rem; padding-bottom: 3rem;}
      div[data-testid="stMetric"] {background: rgba(120,120,120,.07); padding: 14px; border-radius: 12px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🌐 Servejit Browser Agent")
st.caption("Open-source browser automation powered by Browser Use and Groq. TinyFish is not required.")

with st.sidebar:
    st.header("Agent")
    st.success("Browser Use mode")
    st.write("AI reasoning: Groq")
    st.write("Browser automation: Playwright / Chromium")
    st.caption("Free-tier limits apply. No paid fallback is configured.")
    st.divider()
    st.markdown("**Privacy and safety**")
    st.write("Your Groq key is read from Streamlit Secrets. Never put it in GitHub or share it in chat.")
    st.write("The agent must stop before purchases, payments, public posts, messages, deletions, or sensitive-data submission.")

render_browser_use_agent()

st.divider()
st.caption("Servejit Browser Agent • Browser Use + Groq • No TinyFish API key or TinyFish account required.")
