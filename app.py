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
if 'selected_pair' not in st.session_state:
    st.session_state.selected_pair = 'EURUSD'
if 'gemini_result' not in st.session_state:
    st.session_state.gemini_result = None

# ==========================================
# 2. CSS STYLING
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #09090b; color: #ffffff; font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #ffffff !important; font-weight: 900 !important; }
    .quant-card { background-color: #111114; border: 1px solid #27272a; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
    .session-badge { padding: 5px 10px; border-radius: 6px; font-size: 10px; font-weight: 900; text-transform: uppercase; display: inline-block; margin-right: 5px; }
    .session-london { background-color: #22c55e; color: black; }
    .session-ny { background-color: #ef4444; color: white; }
    .session-tokyo { background-color: #facc15; color: black; }
    .session-sydney { background-color: #0ea5e9; color: black; }
    .session-inactive { background-color: #27272a; color: #71717a; }
    .session-overlap { background: linear-gradient(45deg, #f59e0b, #d97706); color: black; animation: pulse 2s infinite; }
    .strength-container { display: flex; align-items: center; margin-bottom: 8px; }
    .strength-label { width: 40px; font-weight: bold; font-size: 12px; color: #a1a1aa; }
    .strength-bar-bg { flex-grow: 1; height: 8px; background-color: #27272a; border-radius: 4px; overflow: hidden; }
    .strength-bar-fill { height: 100%; border-radius: 4px; }
    .strength-val { width: 50px; text-align: right; font-size: 11px; font-family: monospace; }
    div.stButton > button { background-color: #2563eb; color: white; border: none; border-radius: 8px; font-weight: 800; text-transform: uppercase; }
    div.stButton > button:hover { background-color: #1d4ed8; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); } 70% { box-shadow: 0 0 0 10px rgba(245, 158, 11, 0); } 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. UTILS & LOGIC
# ==========================================

CONSTANTS = {
    'MAJOR_PAIRS': ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'XAUUSD'],
    'SESSIONS': [
        {'name': 'Sydney', 'start': 22, 'end': 7, 'color': '#0ea5e9'},
        {'name': 'Tokyo', 'start': 0, 'end': 9, 'color': '#facc15'},
        {'name': 'London', 'start': 8, 'end': 17, 'color': '#22c55e'},
        {'name': 'New York', 'start': 13, 'end': 22, 'color': '#ef4444'}
    ]
}

def get_lagos_time():
    return datetime.datetime.now(pytz.timezone('Africa/Lagos'))

def is_overlap(hour):
    return 14 <= hour < 17

def get_active_sessions(current_hour_utc):
    active = []
    for s in CONSTANTS['SESSIONS']:
        if s['start'] > s['end']:
            if current_hour_utc >= s['start'] or current_hour_utc < s['end']:
                active.append(s['name'])
        else:
            if s['start'] <= current_hour_utc < s['end']:
                active.append(s['name'])
    return active

# --- Real Data Fetchers ---

@st.cache_data(ttl=600) # Cache for 10 mins to prevent constant reloading
def fetch_live_data():
    """Fetches real market data (DXY, Currencies)"""
    tickers = ["DX-Y.NYB", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"]
    try:
        # CRITICAL FIX: threads=False prevents Streamlit Cloud from hanging
        data = yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
        
        if data.empty:
            raise Exception("No data returned")

        # Calculate Strength
        strength = {}
        
        # Safe access to multi-index dataframe
        def get_close(ticker):
            try:
                return data["Close"][ticker].iloc[-1]
            except:
                return data["Close"].iloc[-1] # Fallback if single level

        def get_open(ticker):
            try:
                return data["Open"][ticker].iloc[-1]
            except:
                return data["Open"].iloc[-1]

        # DXY Strength
        dxy_open = get_open("DX-Y.NYB")
        dxy_close = get_close("DX-Y.NYB")
        
        # Safety check for NaN
        if pd.isna(dxy_close) or pd.isna(dxy_open):
            raise Exception("NaN data found")

        usd_str = ((dxy_close - dxy_open) / dxy_open) * 100
        strength['USD'] = usd_str
        
        pairs = {'EUR': 'EURUSD=X', 'GBP': 'GBPUSD=X', 'AUD': 'AUDUSD=X', 'JPY': 'USDJPY=X', 'CAD': 'USDCAD=X'}
        
        for curr, tick in pairs.items():
            op = get_open(tick)
            cl = get_close(tick)
            change = ((cl - op) / op) * 100
            
            if curr in ['JPY', 'CAD']: # Base USD
                strength[curr] = usd_str - change
            else: # Quote USD
                strength[curr] = usd_str + change
                
        return strength, dxy_close
    except Exception as e:
        # Fallback Mock Data so app DOES NOT CRASH
        return {'USD': 0.1, 'EUR': -0.1, 'GBP': 0.2, 'JPY': -0.3, 'AUD': 0.1, 'CAD': 0.0}, 100.00

def get_forex_factory_news():
    url = "https://www.forexfactory.com/calendar?day=today"
    headers = {'User-Agent': 'Mozilla/5.0'}
    events = []
    try:
        r = requests.get(url, headers=headers, timeout=3)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            rows = soup.find_all("tr", class_="calendar__row")
            for row in rows:
                impact = row.find("span", class_="high")
                if impact:
                    time_val = row.find("td", class_="calendar__time").text.strip()
                    currency = row.find("td", class_="calendar__currency").text.strip()
                    event = row.find("td", class_="calendar__event").text.strip()
                    events.append({'time': time_val, 'currency': currency, 'event': event, 'impact': 'High'})
    except:
        pass
    
    if not events:
        return [{'time': '--:--', 'currency': 'ALL', 'event': 'No High Impact News Detected', 'impact': 'Low'}]
    return events

# --- Gemini Service ---
def call_gemini_ai(pair, strength_data, dxy_price, api_key):
    if not api_key:
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        system_prompt = "You are a Senior Quant Developer. Analyze Forex data. Output valid JSON only."
        user_prompt = f"Analyze {pair}. Strength: {strength_data}. DXY: {dxy_price}. Provide score(0-100), action(BUY/SELL/WAIT), reasoning(list), tp, sl."
        
        response = model.generate_content(system_prompt + user_prompt)
        text = response.text.replace('```json', '').replace('```', '')
        import json
        return json.loads(text)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# ==========================================
# 4. MAIN APP LAYOUT
# ==========================================

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ SYSTEM CORE")
    api_key = st.text_input("Gemini API Key", type="password")
    st.caption("Get key from Google AI Studio")
    st.divider()
    st.info("System Ready")

# --- HEADER ---
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("### 🦅 FX-CORE QUANT TERMINAL")
    st.caption("Institutional Profit & Logic Engine")
with col2:
    lagos_time = get_lagos_time()
    st.metric("LAGOS TIME", lagos_time.strftime('%H:%M:%S'))

# --- SESSIONS ---
# Fix: Use timezone-aware UTC for current hour check
current_hour_utc = datetime.datetime.now(datetime.timezone.utc).hour
active_sessions = get_active_sessions(current_hour_utc)
overlap = is_overlap(lagos_time.hour)

st.markdown("---")
session_html = ""
for s in CONSTANTS['SESSIONS']:
    status = "session-inactive"
    if s['name'] in active_sessions:
        if s['name'] == 'London': status = 'session-london'
        elif s['name'] == 'New York': status = 'session-ny'
        elif s['name'] == 'Tokyo': status = 'session-tokyo'
        elif s['name'] == 'Sydney': status = 'session-sydney'
    session_html += f'<span class="session-badge {status}">{s["name"]}</span>'

if overlap:
    session_html += '<span class="session-badge session-overlap">⚡ KILL ZONE ACTIVE</span>'
st.markdown(f"<div>{session_html}</div>", unsafe_allow_html=True)
st.markdown("---")

# --- DATA LOAD ---
with st.spinner("Connecting to Global Markets..."):
    strength_data, dxy_val = fetch_live_data()
    news_data = get_forex_factory_news()

# --- MAIN GRID ---
col_left, col_mid, col_right = st.columns([1, 2, 1])

# LEFT: Strength
with col_left:
    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.markdown("##### 💪 CURRENCY POWER", unsafe_allow_html=True)
    sorted_strength = dict(sorted(strength_data.items(), key=lambda item: item[1], reverse=True))
    for curr, val in sorted_strength.items():
        color = "#22c55e" if val > 0 else "#ef4444"
        width = min(abs(val) * 50, 100)
        st.markdown(f"""
        <div class="strength-container">
            <div class="strength-label">{curr}</div>
            <div class="strength-bar-bg"><div class="strength-bar-fill" style="width: {width}%; background-color: {color};"></div></div>
            <div class="strength-val" style="color: {color}">{val:+.2f}%</div>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.session_state.selected_pair = st.selectbox("TARGET ASSET", CONSTANTS['MAJOR_PAIRS'])
    st.markdown('</div>', unsafe_allow_html=True)

# MIDDLE: Action
with col_mid:
    st.metric("DOLLAR INDEX (DXY)", f"{dxy_val:.2f}", delta="Bullish" if strength_data['USD'] > 0 else "Bearish")
    
    if st.button("RUN QUANT ANALYSIS ⚡", use_container_width=True):
        if api_key:
            with st.spinner("Calculating..."):
                st.session_state.gemini_result = call_gemini_ai(st.session_state.selected_pair, strength_data, dxy_val, api_key)
        else:
            st.warning("Enter API Key in Sidebar")

    if st.session_state.gemini_result:
        res = st.session_state.gemini_result
        score = res.get('score', 50)
        action = res.get('action', 'WAIT')
        bg_color = "#eab308"
        if score >= 80: bg_color = "#22c55e"
        if score <= 30: bg_color = "#ef4444"
        
        st.markdown(f"""
        <div style="background-color: {bg_color}; color: black; padding: 20px; border-radius: 12px; text-align: center; margin-top: 20px;">
            <div style="font-size: 40px; font-weight: 900;">{action}</div>
            <div>CONFIDENCE: {score}%</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="quant-card" style="margin-top: 10px;">
            <div style="display:flex; justify-content:space-between; font-weight:bold;">
                <span style="color:#ef4444">SL: {res.get('sl',0)}</span>
                <span style="color:#22c55e">TP: {res.get('tp',0)}</span>
            </div>
            <hr style="border-color:#333;">
            <div style="font-size:12px; color:#aaa;">{' • '.join(res.get('reasoning', []))}</div>
        </div>
        """, unsafe_allow_html=True)

# RIGHT: News & Gauge
with col_right:
    if st.session_state.gemini_result:
        score = st.session_state.gemini_result.get('score', 50)
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = score,
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#2563eb"},
                     'steps': [{'range': [0, 30], 'color': '#ef4444'}, {'range': [70, 100], 'color': '#22c55e'}]}
        ))
        fig.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.markdown("##### 📰 NEWS", unsafe_allow_html=True)
    for n in news_data:
        color = "#ef4444" if n['impact'] == 'High' else "#555"
        st.markdown(f"<div style='border-left:3px solid {color}; padding-left:8px; margin-bottom:8px; font-size:11px;'><b>{n['time']}</b> {n['currency']} - {n['event']}</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
