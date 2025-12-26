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

# ==========================================
# 1. CONFIGURATION & STATE
# ==========================================
st.set_page_config(
    page_title="Forex Quant Terminal",
    layout="wide",
    page_icon="🦅",
    initial_sidebar_state="collapsed"
)

# Initialize Session State
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
if "gemini_result" not in st.session_state:
    st.session_state.gemini_result = None
if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = "EURUSD"

# ==========================================
# 2. PRO-LEVEL CSS (The "React" Look)
# ==========================================
st.markdown("""
<style>
    /* Main Background */
    .stApp { background-color: #09090b; color: #ffffff; font-family: 'Inter', sans-serif; }
    
    /* Hide Default Header/Footer */
    header {visibility: hidden;}
    footer {visibility: hidden;}

    /* Cards */
    .quant-card {
        background-color: #111114;
        border: 1px solid #27272a;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    /* Strength Bars */
    .strength-row { display: flex; align-items: center; margin-bottom: 8px; }
    .curr-label { width: 40px; font-weight: 900; font-size: 12px; color: #a1a1aa; }
    .bar-bg { flex-grow: 1; height: 6px; background-color: #27272a; border-radius: 10px; margin: 0 10px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 10px; }
    .curr-val { width: 50px; text-align: right; font-size: 11px; font-family: monospace; font-weight: bold; }

    /* News Items */
    .news-item {
        padding: 10px;
        border-left: 3px solid #27272a;
        background-color: #18181b;
        margin-bottom: 8px;
        border-radius: 0 6px 6px 0;
    }
    .news-time { color: #ef4444; font-weight: 900; font-size: 10px; }
    .news-event { font-size: 11px; font-weight: 600; color: #e4e4e7; }

    /* Action Buttons */
    div.stButton > button {
        width: 100%;
        background-color: #2563eb;
        color: white;
        border: none;
        padding: 12px;
        border-radius: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s;
    }
    div.stButton > button:hover { background-color: #1d4ed8; transform: scale(1.02); }
    
    /* Metrics */
    div[data-testid="stMetricValue"] { font-family: monospace; font-weight: 700; color: #3b82f6; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. ROBUST DATA LOGIC
# ==========================================

CONSTANTS = {
    'MAJOR_PAIRS': ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD']
}

def get_lagos_time():
    return datetime.datetime.now(pytz.timezone('Africa/Lagos'))

@st.cache_data(ttl=600)
def fetch_live_data():
    """Fetches real market data safely"""
    try:
        # Fetch minimal data to prevent timeout
        tickers = ["DX-Y.NYB", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"]
        data = yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
        
        if data.empty: raise Exception("Empty Data")

        # Helper to get price safely
        def get_price(ticker, type='Close'):
            try:
                return data[type][ticker].iloc[-1]
            except:
                return data[type].iloc[-1]

        # Calculate DXY
        dxy_close = get_price("DX-Y.NYB")
        dxy_open = get_price("DX-Y.NYB", 'Open')
        usd_str = ((dxy_close - dxy_open) / dxy_open) * 100
        
        strength = {'USD': usd_str}
        
        # Calculate Others
        pairs = {'EUR': 'EURUSD=X', 'GBP': 'GBPUSD=X', 'AUD': 'AUDUSD=X', 'JPY': 'USDJPY=X', 'CAD': 'USDCAD=X'}
        for curr, tick in pairs.items():
            op = get_price(tick, 'Open')
            cl = get_price(tick, 'Close')
            change = ((cl - op) / op) * 100
            if curr in ['JPY', 'CAD']: strength[curr] = usd_str - change
            else: strength[curr] = usd_str + change
            
        return strength, dxy_close
    except:
        # Safe Fallback
        return {'USD': 0.1, 'EUR': -0.1, 'GBP': 0.2, 'JPY': -0.3, 'AUD': 0.1, 'CAD': 0.0}, 104.50

@st.cache_data(ttl=900)
def get_news():
    """Fast scrape with timeout"""
    try:
        r = requests.get("https://www.forexfactory.com/calendar?day=today", headers={'User-Agent': 'Mozilla/5.0'}, timeout=1.5)
        soup = BeautifulSoup(r.text, 'html.parser')
        events = []
        rows = soup.find_all("tr", class_="calendar__row")
        for row in rows:
            if row.find("span", class_="high"): # Red folder
                time = row.find("td", class_="calendar__time").text.strip()
                curr = row.find("td", class_="calendar__currency").text.strip()
                evt = row.find("td", class_="calendar__event").text.strip()
                events.append(f"{time} | {curr} | {evt}")
        return events if events else ["No High Impact News Today"]
    except:
        return ["News Feed Unavailable (Connection Timeout)"]

def call_gemini(pair, strength, dxy, key):
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = f"""
        Act as a Hedge Fund Algo. Analyze {pair}.
        Context:
        - Currency Strength: {strength}
        - DXY Index: {dxy}
        
        Task: Return a JSON object with:
        - score (0-100)
        - action (STRONG BUY, BUY, WAIT, SELL, STRONG SELL)
        - reasoning (array of 3 short bullet points)
        - tp (price)
        - sl (price)
        """
        
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '')
        import json
        return json.loads(text)
    except:
        return None

# ==========================================
# 4. APP LAYOUT
# ==========================================

# Sidebar
with st.sidebar:
    st.header("⚙️ CORE SETTINGS")
    api_key = st.text_input("Gemini API Key", type="password")
    if st.button("RESET SYSTEM"):
        st.session_state.data_loaded = False
        st.rerun()

# Header
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    <div style="display:flex; align-items:center; gap:10px;">
        <span style="background:#2563eb; padding:4px 8px; border-radius:4px; font-weight:900; font-size:12px;">FX-CORE v4</span>
        <h1 style="margin:0; font-size:28px;">QUANT TERMINAL</h1>
    </div>
    <p style="color:#71717a; font-size:12px; letter-spacing:1px;">INSTITUTIONAL DATA ENGINE</p>
    """, unsafe_allow_html=True)
with col2:
    t = get_lagos_time()
    st.markdown(f"""
    <div style="text-align:right; border-right:3px solid #2563eb; padding-right:10px;">
        <div style="font-size:10px; font-weight:900; color:#52525b;">LAGOS TIME</div>
        <div style="font-size:24px; font-weight:700; font-family:monospace;">{t.strftime('%H:%M')}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# DATA LOADING GATE (The Safety Switch)
if not st.session_state.data_loaded:
    st.markdown("""
    <div style="text-align:center; padding:50px;">
        <h3 style="color:#52525b;">SYSTEM STANDBY</h3>
        <p style="font-size:12px; color:#3f3f46;">Connect to global data feeds to begin analysis.</p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("🔌 CONNECT TO MARKETS (INITIATE FEED)"):
            with st.spinner("Establishing Secure Connection..."):
                st.session_state.strength, st.session_state.dxy = fetch_live_data()
                st.session_state.news = get_news()
                st.session_state.data_loaded = True
                st.rerun()

else:
    # === MAIN DASHBOARD ===
    strength = st.session_state.strength
    dxy = st.session_state.dxy
    news = st.session_state.news

    c_left, c_mid, c_right = st.columns([1, 1.5, 1])

    # LEFT: STRENGTH METER
    with c_left:
        st.markdown('<div class="quant-card">', unsafe_allow_html=True)
        st.markdown("##### 💪 POWER INDEX", unsafe_allow_html=True)
        
        sorted_strength = dict(sorted(strength.items(), key=lambda item: item[1], reverse=True))
        for curr, val in sorted_strength.items():
            color = "#22c55e" if val > 0 else "#ef4444"
            width = min(abs(val) * 80, 100)
            st.markdown(f"""
            <div class="strength-row">
                <div class="curr-label">{curr}</div>
                <div class="bar-bg"><div class="bar-fill" style="width:{width}%; background:{color};"></div></div>
                <div class="curr-val" style="color:{color}">{val:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # MID: AI ENGINE
    with c_mid:
        st.markdown('<div class="quant-card" style="border-top:3px solid #2563eb;">', unsafe_allow_html=True)
        
        # DXY Display
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <div>
                <div style="font-size:10px; font-weight:900; color:#71717a;">DOLLAR INDEX</div>
                <div style="font-size:28px; font-weight:900; font-family:monospace;">{dxy:.2f}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:10px; font-weight:900; color:#71717a;">TREND BIAS</div>
                <div style="color:{'#22c55e' if strength['USD']>0 else '#ef4444'}; font-weight:900;">
                    {'BULLISH' if strength['USD']>0 else 'BEARISH'}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Controls
        col_sel, col_btn = st.columns([1, 1])
        with col_sel:
            st.session_state.selected_pair = st.selectbox("ASSET", CONSTANTS['MAJOR_PAIRS'], label_visibility="collapsed")
        with col_btn:
            if st.button("RUN ANALYSIS ⚡"):
                if api_key:
                    with st.spinner("Processing..."):
                        st.session_state.gemini_result = call_gemini(st.session_state.selected_pair, strength, dxy, api_key)
                else:
                    st.warning("⚠️ API Key Needed")

        # Result Display
        if st.session_state.gemini_result:
            res = st.session_state.gemini_result
            score = res.get('score', 50)
            action = res.get('action', 'WAIT')
            color = "#22c55e" if score >= 80 else "#ef4444" if score <= 30 else "#eab308"
            
            st.markdown(f"""
            <div style="background:{color}20; border:1px solid {color}; padding:20px; border-radius:8px; margin-top:20px; text-align:center;">
                <div style="color:{color}; font-size:12px; font-weight:900; letter-spacing:2px;">SIGNAL VERDICT</div>
                <div style="color:{color}; font-size:36px; font-weight:900;">{action}</div>
                <div style="font-size:12px; font-weight:bold; color:#fff;">CONFIDENCE: {score}%</div>
            </div>
            <div style="margin-top:15px; font-size:12px; color:#a1a1aa; line-height:1.6;">
                <strong style="color:#fff;">STRATEGY NOTES:</strong><br>
                {'<br>'.join([f"• {r}" for r in res.get('reasoning', [])])}
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px; font-family:monospace; font-weight:bold;">
                <span style="color:#ef4444">SL: {res.get('sl', '---')}</span>
                <span style="color:#22c55e">TP: {res.get('tp', '---')}</span>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)

    # RIGHT: NEWS & GAUGE
    with c_right:
        if st.session_state.gemini_result:
            score = st.session_state.gemini_result.get('score', 50)
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = score,
                gauge = {
                    'axis': {'range': [0, 100]}, 
                    'bar': {'color': "#2563eb"},
                    'bgcolor': "#18181b",
                    'steps': [{'range': [0, 30], 'color': '#ef4444'}, {'range': [70, 100], 'color': '#22c55e'}]
                }
            ))
            fig.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="quant-card">', unsafe_allow_html=True)
        st.markdown("##### 📰 NEWS FEED", unsafe_allow_html=True)
        for n in news:
            st.markdown(f'<div class="news-item"><div class="news-event">{n}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
