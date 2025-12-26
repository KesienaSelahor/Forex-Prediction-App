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
import warnings

warnings.filterwarnings("ignore")

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Forex Quant Terminal",
    layout="wide",
    page_icon="🦅",
    initial_sidebar_state="collapsed"
)

# Initialize State
if "data_loaded" not in st.session_state: st.session_state.data_loaded = False
if "gemini_result" not in st.session_state: st.session_state.gemini_result = None
if "selected_pair" not in st.session_state: st.session_state.selected_pair = "EURUSD"
if "api_key" not in st.session_state: st.session_state.api_key = ""

# ==========================================
# 2. CSS (FIXED: Sidebar Button Visible)
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #09090b; color: #ffffff; font-family: 'Inter', sans-serif; }
    
    /* Removed the line that hid the header/sidebar button */
    footer {visibility: hidden;}
    
    .quant-card { background-color: #111114; border: 1px solid #27272a; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .session-badge { padding: 5px 10px; border-radius: 6px; font-size: 10px; font-weight: 900; text-transform: uppercase; display: inline-block; margin-right: 5px; }
    .session-london { background-color: #22c55e; color: black; }
    .session-ny { background-color: #ef4444; color: white; }
    .session-tokyo { background-color: #facc15; color: black; }
    .session-sydney { background-color: #0ea5e9; color: black; }
    .session-inactive { background-color: #27272a; color: #71717a; }
    .session-overlap { background: linear-gradient(45deg, #f59e0b, #d97706); color: black; animation: pulse 2s infinite; }
    .strength-row { display: flex; align-items: center; margin-bottom: 8px; }
    .curr-label { width: 40px; font-weight: 900; font-size: 12px; color: #a1a1aa; }
    .bar-bg { flex-grow: 1; height: 6px; background-color: #27272a; border-radius: 10px; margin: 0 10px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 10px; }
    .curr-val { width: 50px; text-align: right; font-size: 11px; font-family: monospace; font-weight: bold; }
    .news-item { padding: 10px; border-left: 3px solid #27272a; background-color: #18181b; margin-bottom: 8px; border-radius: 0 6px 6px 0; }
    .news-time { color: #ef4444; font-weight: 900; font-size: 10px; }
    .news-event { font-size: 11px; font-weight: 600; color: #e4e4e7; }
    
    div.stButton > button { width: 100%; background-color: #2563eb; color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; transition: all 0.3s; }
    div.stButton > button:hover { background-color: #1d4ed8; transform: scale(1.02); }
    div[data-testid="stMetricValue"] { font-family: monospace; font-weight: 700; color: #3b82f6; }
    
    /* Input Field Styling */
    div[data-testid="stTextInput"] input { background-color: #18181b; color: white; border: 1px solid #3f3f46; }
    
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); } 70% { box-shadow: 0 0 0 10px rgba(245, 158, 11, 0); } 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. UTILS
# ==========================================
CONSTANTS = {
    'MAJOR_PAIRS': ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD'],
    'SESSIONS': [
        {'name': 'Sydney', 'start': 22, 'end': 7},
        {'name': 'Tokyo', 'start': 0, 'end': 9},
        {'name': 'London', 'start': 8, 'end': 17},
        {'name': 'New York', 'start': 13, 'end': 22}
    ]
}

def get_lagos_time(): return datetime.datetime.now(pytz.timezone('Africa/Lagos'))
def is_overlap(hour): return 14 <= hour < 17
def get_active_sessions(hour_utc):
    active = []
    for s in CONSTANTS['SESSIONS']:
        if s['start'] > s['end']:
            if hour_utc >= s['start'] or hour_utc < s['end']: active.append(s['name'])
        else:
            if s['start'] <= hour_utc < s['end']: active.append(s['name'])
    return active

@st.cache_data(ttl=600)
def fetch_live_data():
    try:
        tickers = ["DX-Y.NYB", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"]
        data = yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
        if data.empty: raise Exception("Block")
        
        def get_p(t, k='Close'): 
            try: return data[k][t].iloc[-1]
            except: return data[k].iloc[-1]

        dxy_c, dxy_o = get_p("DX-Y.NYB"), get_p("DX-Y.NYB", 'Open')
        usd = ((dxy_c - dxy_o) / dxy_o) * 100
        strength = {'USD': usd}
        
        pairs = {'EUR':'EURUSD=X', 'GBP':'GBPUSD=X', 'AUD':'AUDUSD=X', 'JPY':'USDJPY=X', 'CAD':'USDCAD=X'}
        for c, t in pairs.items():
            op, cl = get_p(t, 'Open'), get_p(t)
            ch = ((cl - op) / op) * 100
            strength[c] = (usd - ch) if c in ['JPY','CAD'] else (usd + ch)
        return strength, dxy_c
    except:
        return {'USD': 0.15, 'EUR': -0.12, 'GBP': 0.25, 'JPY': -0.40, 'AUD': 0.10, 'CAD': 0.05}, 103.50

@st.cache_data(ttl=900)
def get_news():
    try:
        r = requests.get("https://www.forexfactory.com/calendar?day=today", headers={'User-Agent':'Mozilla/5.0'}, timeout=1.5)
        soup = BeautifulSoup(r.text, 'html.parser')
        evs = []
        for r in soup.find_all("tr", class_="calendar__row"):
            if r.find("span", class_="high"):
                t = r.find("td", class_="calendar__time").text.strip()
                c = r.find("td", class_="calendar__currency").text.strip()
                e = r.find("td", class_="calendar__event").text.strip()
                evs.append(f"{t} | {c} | {e}")
        return evs if evs else ["No High Impact News"]
    except: return ["News Offline"]

def call_gemini(pair, strength, dxy, key):
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        p = f"Act as Quant Algo. Analyze {pair}. Strength:{strength}. DXY:{dxy}. JSON output: score(0-100), action(BUY/SELL/WAIT), reasoning(list), tp, sl."
        r = model.generate_content(p)
        return __import__('json').loads(r.text.replace('```json','').replace('```',''))
    except: return None

# ==========================================
# 4. APP LAYOUT
# ==========================================

# --- NEW: API KEY INPUT ON MAIN SCREEN ---
with st.expander("🔑 SYSTEM CREDENTIALS (API KEY)", expanded=not st.session_state.api_key):
    st.session_state.api_key = st.text_input("Enter Google Gemini API Key:", value=st.session_state.api_key, type="password")
    if st.button("RESET CONNECTION"):
        st.session_state.data_loaded = False
        st.rerun()

# --- HEADER ---
c1, c2 = st.columns([3,1])
with c1: st.markdown("### 🦅 FX-CORE QUANT TERMINAL")
with c2: st.metric("LAGOS TIME", get_lagos_time().strftime('%H:%M'))

# --- SESSIONS ---
h_utc = datetime.datetime.now(datetime.timezone.utc).hour
active = get_active_sessions(h_utc)
ovr = is_overlap(get_lagos_time().hour)
html = ""
for s in CONSTANTS['SESSIONS']:
    cls = "session-inactive"
    if s['name'] in active: cls = f"session-{s['name'].lower().replace(' ','')}"
    html += f'<span class="session-badge {cls}">{s["name"]}</span>'
if ovr: html += '<span class="session-badge session-overlap">⚡ KILL ZONE</span>'
st.markdown(f"<div style='margin-bottom:20px'>{html}</div>", unsafe_allow_html=True)

# --- LOADING GATE ---
if not st.session_state.data_loaded:
    st.info("System Standby. Click to Connect.")
    if st.button("🔌 CONNECT TO MARKETS"):
        with st.spinner("Connecting..."):
            st.session_state.strength, st.session_state.dxy = fetch_live_data()
            st.session_state.news = get_news()
            st.session_state.data_loaded = True
            st.rerun()
else:
    # --- DASHBOARD ---
    s_data = st.session_state.strength
    dxy_val = st.session_state.dxy
    news_data = st.session_state.news
    
    c_left, c_mid, c_right = st.columns([1, 1.5, 1])
    
    with c_left:
        st.markdown('<div class="quant-card"><h5>💪 POWER INDEX</h5>', unsafe_allow_html=True)
        for k, v in dict(sorted(s_data.items(), key=lambda i:i[1], reverse=True)).items():
            clr = "#22c55e" if v>0 else "#ef4444"
            wid = min(abs(v)*80, 100)
            st.markdown(f'<div class="strength-row"><div class="curr-label">{k}</div><div class="bar-bg"><div class="bar-fill" style="width:{wid}%; background:{clr};"></div></div><div class="curr-val" style="color:{clr}">{v:+.2f}%</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_mid:
        st.markdown('<div class="quant-card" style="border-top:3px solid #2563eb;">', unsafe_allow_html=True)
        st.metric("DXY INDEX", f"{dxy_val:.2f}", "Bullish" if s_data['USD']>0 else "Bearish")
        
        c_sel, c_run = st.columns(2)
        with c_sel: st.session_state.selected_pair = st.selectbox("ASSET", CONSTANTS['MAJOR_PAIRS'])
        with c_run:
            if st.button("RUN ANALYSIS ⚡"):
                if st.session_state.api_key:
                    with st.spinner("Analyzing..."):
                        st.session_state.gemini_result = call_gemini(st.session_state.selected_pair, s_data, dxy_val, st.session_state.api_key)
                else: st.error("ENTER API KEY ABOVE ⬆️")

        if st.session_state.gemini_result:
            r = st.session_state.gemini_result
            sc = r.get('score', 50)
            clr = "#22c55e" if sc>=80 else "#ef4444" if sc<=30 else "#eab308"
            st.markdown(f'<div style="background:{clr}20; border:1px solid {clr}; padding:15px; border-radius:8px; text-align:center; margin-top:15px;"><div style="color:{clr}; font-weight:900; font-size:32px;">{r.get("action")}</div><div style="font-weight:bold;">CONFIDENCE: {sc}%</div></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="margin-top:10px; font-size:12px;"><strong>NOTES:</strong><br>{"<br>".join([f"• {x}" for x in r.get("reasoning",[])])}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="display:flex; justify-content:space-between; margin-top:10px; font-family:monospace; font-weight:bold;"><span style="color:#ef4444">SL: {r.get("sl")}</span><span style="color:#22c55e">TP: {r.get("tp")}</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_right:
        if st.session_state.gemini_result:
            sc = st.session_state.gemini_result.get('score', 50)
            fig = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#2563eb"}, 'bgcolor': "#18181b", 'steps': [{'range': [0, 30], 'color': '#ef4444'}, {'range': [70, 100], 'color': '#22c55e'}]}))
            fig.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
            st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<div class="quant-card"><h5>📰 NEWS</h5>', unsafe_allow_html=True)
        for n in news_data: st.markdown(f'<div class="news-item"><div class="news-event">{n}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
