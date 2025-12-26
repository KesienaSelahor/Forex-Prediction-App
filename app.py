import streamlit as st
import pandas as pd
import numpy as np
import datetime
import pytz
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import google.generativeai as genai
import yfinance as yf
import time

st.set_page_config(
    page_title="Forex Quant Terminal",
    layout="wide",
    page_icon="🦅",
    initial_sidebar_state="collapsed"
)

st.set_option('client.showErrorDetails', False)

# ---------------- STATE ----------------
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
if "gemini_result" not in st.session_state:
    st.session_state.gemini_result = None
if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = "EURUSD"

# ---------------- CSS ----------------
st.markdown("""<style>
.stApp { background-color:#09090b;color:white;font-family:Inter }
</style>""", unsafe_allow_html=True)

# ---------------- CONSTANTS ----------------
PAIRS = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','XAUUSD']

# ---------------- UTILS ----------------
def get_lagos_time():
    return datetime.datetime.now(pytz.timezone("Africa/Lagos"))

@st.cache_data(ttl=600)
def fetch_live_data():
    try:
        data = yf.download(
            ["DX-Y.NYB","EURUSD=X","GBPUSD=X"],
            period="2d",
            interval="1d",
            progress=False,
            threads=False
        )
        dxy_open = data["Open"]["DX-Y.NYB"].iloc[-1]
        dxy_close = data["Close"]["DX-Y.NYB"].iloc[-1]
        usd = ((dxy_close - dxy_open) / dxy_open) * 100
        return {"USD": usd}, dxy_close
    except:
        return {"USD": 0.1}, 100.0

@st.cache_data(ttl=900)
def get_news():
    try:
        r = requests.get(
            "https://www.forexfactory.com/calendar?day=today",
            headers={"User-Agent":"Mozilla/5.0"},
            timeout=1.5
        )
        soup = BeautifulSoup(r.text,"html.parser")
        return ["High impact events today"] if soup else ["No major news"]
    except:
        return ["No major news"]

def call_gemini(pair, strength, dxy, key):
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        start = time.time()
        r = model.generate_content(
            f"Analyze {pair}. Strength:{strength}, DXY:{dxy}. "
            "Return JSON: score, action, reasoning(list), tp, sl"
        )
        if time.time() - start > 8:
            raise TimeoutError
        import json
        return json.loads(r.text.replace("```json","").replace("```",""))
    except:
        return None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    api_key = st.text_input("Gemini API Key", type="password")

# ---------------- HEADER ----------------
st.markdown("## 🦅 FX-CORE QUANT TERMINAL")
st.caption(f"Lagos Time: {get_lagos_time().strftime('%H:%M')}")

# ---------------- DATA LOAD ----------------
if not st.session_state.data_loaded:
    if st.button("🔌 CONNECT TO MARKETS"):
        with st.spinner("Connecting..."):
            st.session_state.strength, st.session_state.dxy = fetch_live_data()
            st.session_state.news = get_news()
            st.session_state.data_loaded = True
else:
    strength = st.session_state.strength
    dxy = st.session_state.dxy
    news = st.session_state.news

    col1, col2 = st.columns([1,2])
    with col1:
        st.selectbox("Asset", PAIRS, key="selected_pair")
        st.metric("DXY", f"{dxy:.2f}")

    with col2:
        if st.button("RUN QUANT ANALYSIS ⚡"):
            if api_key:
                with st.spinner("Analyzing..."):
                    st.session_state.gemini_result = call_gemini(
                        st.session_state.selected_pair,
                        strength,
                        dxy,
                        api_key
                    )

    if st.session_state.gemini_result:
        res = st.session_state.gemini_result
        st.success(f"{res.get('action')} | Confidence {res.get('score')}%")
        st.write(res.get("reasoning",[]))

    st.markdown("### 📰 News")
    for n in news:
        st.write("-", n)
