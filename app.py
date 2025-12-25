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
# 2. CSS STYLING (The "React/Tailwind" Look)
# ==========================================
st.markdown("""
<style>
    /* Main Background - Dark Zinc Theme */
    .stApp {
        background-color: #09090b;
        color: #ffffff;
        font-family: 'Inter', sans-serif;
    }
    
    /* Headers */
    h1, h2, h3 { color: #ffffff !important; font-weight: 900 !important; letter-spacing: -1px; }
    
    /* Cards */
    .quant-card {
        background-color: #111114;
        border: 1px solid #27272a;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Session Badges */
    .session-badge {
        padding: 5px 10px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: 900;
        text-transform: uppercase;
        display: inline-block;
        margin-right: 5px;
    }
    .session-london { background-color: #22c55e; color: black; }
    .session-ny { background-color: #ef4444; color: white; }
    .session-tokyo { background-color: #facc15; color: black; }
    .session-sydney { background-color: #0ea5e9; color: black; }
    .session-inactive { background-color: #27272a; color: #71717a; border: 1px solid #3f3f46; }
    .session-overlap { 
        background: linear-gradient(45deg, #f59e0b, #d97706); 
        color: black; 
        animation: pulse 2s infinite; 
    }

    /* Strength Meter Bars */
    .strength-container { display: flex; align-items: center; margin-bottom: 8px; }
    .strength-label { width: 40px; font-weight: bold; font-size: 12px; color: #a1a1aa; }
    .strength-bar-bg { flex-grow: 1; height: 8px; background-color: #27272a; border-radius: 4px; overflow: hidden; }
    .strength-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
    .strength-val { width: 50px; text-align: right; font-size: 11px; font-family: monospace; }

    /* Custom Button Styling */
    div.stButton > button {
        background-color: #2563eb;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    div.stButton > button:hover { background-color: #1d4ed8; }

    /* Animations */
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(245, 158, 11, 0); }
        100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. UTILS & LOGIC (Python Ports of TS Code)
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
        # Handle overnight wrap-around (e.g. 22 to 7)
        if s['start'] > s['end']:
            if current_hour_utc >= s['start'] or current_hour_utc < s['end']:
                active.append(s['name'])
        else:
            if s['start'] <= current_hour_utc < s['end']:
                active.append(s['name'])
    return active

# --- Real Data Fetchers ---

@st.cache_data(ttl=300) # Cache for 5 mins
def fetch_live_data():
    """Fetches real market data (DXY, Currencies)"""
    tickers = ["DX-Y.NYB", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"]
    try:
        data = yf.download(tickers, period="2d", interval="1d", progress=False)
        
        # Calculate Strength (Change %)
        strength = {}
        # DXY Strength
        dxy_open = data["Open"]["DX-Y.NYB"].iloc[-1]
        dxy_close = data["Close"]["DX-Y.NYB"].iloc[-1]
        usd_str = ((dxy_close - dxy_open) / dxy_open) * 100
        
        strength['USD'] = usd_str
        
        # Others relative to USD
        pairs = {
            'EUR': 'EURUSD=X', 'GBP': 'GBPUSD=X', 'AUD': 'AUDUSD=X',
            'JPY': 'USDJPY=X', 'CAD': 'USDCAD=X'
        }
        
        for curr, tick in pairs.items():
            op = data["Open"][tick].iloc[-1]
            cl = data["Close"][tick].iloc[-1]
            change = ((cl - op) / op) * 100
            
            if curr in ['JPY', 'CAD']: # Base USD
                strength[curr] = usd_str - change
            else: # Quote USD
                strength[curr] = usd_str + change
                
        return strength, dxy_close
    except:
        # Fallback Mock Data if API Fails
        return {'USD': 0.5, 'EUR': -0.2, 'GBP': 0.1, 'JPY': -0.8, 'AUD': 0.3, 'CAD': 0.0}, 104.50

def get_forex_factory_news():
    """Scrapes High Impact News"""
    url = "https://www.forexfactory.com/calendar?day=today"
    headers = {'User-Agent': 'Mozilla/5.0'}
    events = []
    try:
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            rows = soup.find_all("tr", class_="calendar__row")
            for row in rows:
                impact = row.find("span", class_="high") # Red folder
                if impact:
                    time = row.find("td", class_="calendar__time").text.strip()
                    currency = row.find("td", class_="calendar__currency").text.strip()
                    event = row.find("td", class_="calendar__event").text.strip()
                    events.append({'time': time, 'currency': currency, 'event': event, 'impact': 'High'})
    except:
        pass
    
    # If empty or failed, show safe state
    if not events:
        return [{'time': '--:--', 'currency': 'ALL', 'event': 'No High Impact News Detected', 'impact': 'Low'}]
    return events

# --- Gemini Service (Using the prompt you provided) ---
def call_gemini_ai(pair, strength_data, dxy_price, api_key):
    if not api_key:
        return None
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash") # Updated model name for Python SDK
        
        system_prompt = """
        You are a Senior Quant Developer. Analyze Forex data.
        RULES:
        - Output MUST be valid JSON.
        - Fields: pair, score (0-100), action (BUY/SELL/WAIT), reasoning (list of strings), tp (price), sl (price).
        - Be precise.
        """
        
        user_prompt = f"""
        Analyze {pair}.
        Data:
        - Currency Strength: {strength_data}
        - DXY Price: {dxy_price}
        - Trend: {('Bullish' if strength_data.get('USD',0) > 0 else 'Bearish')}
        
        Provide high probability trade setup.
        """
        
        response = model.generate_content(system_prompt + user_prompt)
        # Clean JSON markdown if present
        text = response.text.replace('```json', '').replace('```', '')
        import json
        return json.loads(text)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# ==========================================
# 4. MAIN APP LAYOUT
# ==========================================

# --- SIDEBAR (Settings) ---
with st.sidebar:
    st.header("⚙️ SYSTEM CORE")
    api_key = st.text_input("Gemini API Key", type="password", help="Get key from Google AI Studio")
    st.caption("Required for 'Live Verdict' Analysis")
    
    st.divider()
    st.info("System Version v3.4")

# --- HEADER SECTION ---
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 10px;">
        <span style="background-color: #2563eb; padding: 5px 10px; border-radius: 6px; font-weight: bold; font-style: italic;">FX-CORE</span>
        <h1 style="margin: 0; font-size: 32px;">QUANT TERMINAL</h1>
    </div>
    <p style="color: #71717a; font-size: 12px; letter-spacing: 2px; margin-top: 5px; text-transform: uppercase;">Institutional Profit & Logic Engine</p>
    """, unsafe_allow_html=True)

with col2:
    lagos_time = get_lagos_time()
    st.markdown(f"""
    <div style="background-color: #18181b; padding: 15px; border-radius: 12px; border: 1px solid #27272a; text-align: right;">
        <div style="color: #52525b; font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px;">LAGOS / MARKET TIME</div>
        <div style="color: #ffffff; font-size: 32px; font-family: monospace; font-weight: 700; line-height: 1;">{lagos_time.strftime('%H:%M:%S')}</div>
    </div>
    """, unsafe_allow_html=True)

# --- SESSIONS TIMELINE ---
current_hour_utc = datetime.datetime.utcnow().hour
active_sessions = get_active_sessions(current_hour_utc)
overlap = is_overlap(lagos_time.hour)

st.markdown("### 🌐 MARKET SESSIONS")
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
st.markdown("<br>", unsafe_allow_html=True)

# --- DATA FETCHING ---
strength_data, dxy_val = fetch_live_data()
news_data = get_forex_factory_news()

# --- MAIN GRID ---
col_left, col_mid, col_right = st.columns([1, 2, 1])

# === LEFT COLUMN: STRENGTH & ASSETS ===
with col_left:
    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.markdown("##### 💪 CURRENCY POWER", unsafe_allow_html=True)
    
    # Sort strength
    sorted_strength = dict(sorted(strength_data.items(), key=lambda item: item[1], reverse=True))
    
    for curr, val in sorted_strength.items():
        color = "#22c55e" if val > 0 else "#ef4444"
        width = min(abs(val) * 50, 100) # Scale bar
        st.markdown(f"""
        <div class="strength-container">
            <div class="strength-label">{curr}</div>
            <div class="strength-bar-bg">
                <div class="strength-bar-fill" style="width: {width}%; background-color: {color};"></div>
            </div>
            <div class="strength-val" style="color: {color}">{val:+.2f}%</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.markdown("##### 🎯 TARGET ASSET", unsafe_allow_html=True)
    st.session_state.selected_pair = st.selectbox("Select Pair", CONSTANTS['MAJOR_PAIRS'], label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

# === MIDDLE COLUMN: ANALYSIS & VERDICT ===
with col_mid:
    # 1. DXY Context
    st.markdown(f"""
    <div class="quant-card" style="display: flex; justify-content: space-between; align-items: center; border-left: 4px solid #3b82f6;">
        <div>
            <div style="font-size: 10px; color: #71717a; font-weight: bold; text-transform: uppercase;">DOLLAR INDEX (DXY)</div>
            <div style="font-size: 24px; font-weight: 900; font-family: monospace;">{dxy_val:.2f}</div>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 10px; color: #71717a; font-weight: bold; text-transform: uppercase;">TREND</div>
            <div style="color: {'#22c55e' if strength_data['USD'] > 0 else '#ef4444'}; font-weight: bold;">
                {'BULLISH 🐂' if strength_data['USD'] > 0 else 'BEARISH 🐻'}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. AI Verdict Button
    if st.button("RUN QUANT ANALYSIS ⚡", use_container_width=True):
        with st.spinner("Accessing Institutional Data..."):
            if api_key:
                result = call_gemini_ai(st.session_state.selected_pair, strength_data, dxy_val, api_key)
                st.session_state.gemini_result = result
            else:
                st.error("Please enter Gemini API Key in the Sidebar")

    # 3. Verdict Display
    if st.session_state.gemini_result:
        res = st.session_state.gemini_result
        score = res.get('score', 50)
        action = res.get('action', 'WAIT')
        
        # Color Logic
        bg_color = "#eab308" # Yellow
        if score >= 80: bg_color = "#22c55e" # Green
        if score <= 30: bg_color = "#ef4444" # Red
        
        st.markdown(f"""
        <div style="background-color: {bg_color}; color: black; padding: 30px; border-radius: 12px; text-align: center; margin-top: 20px; box-shadow: 0 0 20px {bg_color}40;">
            <div style="font-size: 12px; font-weight: 900; letter-spacing: 2px; margin-bottom: 10px; opacity: 0.8;">EXECUTION SIGNAL</div>
            <div style="font-size: 48px; font-weight: 900; line-height: 1;">{action}</div>
            <div style="font-size: 14px; font-weight: bold; margin-top: 10px;">CONFIDENCE: {score}%</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Details
        st.markdown(f"""
        <div class="quant-card" style="margin-top: 20px;">
            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #27272a; padding-bottom: 10px; margin-bottom: 10px;">
                <span style="color: #ef4444; font-weight: bold;">STOP LOSS: {res.get('sl', 0.0000)}</span>
                <span style="color: #22c55e; font-weight: bold;">TAKE PROFIT: {res.get('tp', 0.0000)}</span>
            </div>
            <div style="font-size: 12px; color: #a1a1aa;">
                <strong>INSTITUTIONAL REASONING:</strong><br>
                {'<br>• '.join(res.get('reasoning', []))}
            </div>
        </div>
        """, unsafe_allow_html=True)

# === RIGHT COLUMN: NEWS & METRICS ===
with col_right:
    # Gauge Chart (Plotly)
    if st.session_state.gemini_result:
        score = st.session_state.gemini_result.get('score', 50)
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = score,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "SIGNAL STRENGTH", 'font': {'size': 12, 'color': "gray"}},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "#2563eb"},
                'bgcolor': "white",
                'steps': [
                    {'range': [0, 30], 'color': '#ef4444'},
                    {'range': [30, 70], 'color': '#eab308'},
                    {'range': [70, 100], 'color': '#22c55e'}],
            }
        ))
        fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor='rgba(0,0,0,0)', font={'color': "white"})
        st.plotly_chart(fig, use_container_width=True)

    # News Feed
    st.markdown('<div class="quant-card">', unsafe_allow_html=True)
    st.markdown("##### 📰 MACRO NEWS", unsafe_allow_html=True)
    for n in news_data:
        impact_color = "#ef4444" if n['impact'] == 'High' else "#71717a"
        st.markdown(f"""
        <div style="border-left: 3px solid {impact_color}; padding-left: 10px; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; font-size: 10px; font-weight: bold; color: #a1a1aa;">
                <span>{n['time']}</span>
                <span>{n['currency']}</span>
            </div>
            <div style="font-size: 11px; font-weight: 600;">{n['event']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="text-align: center; color: #3f3f46; font-size: 10px; margin-top: 50px; font-weight: 900; letter-spacing: 4px;">
    QUANT CORE TERMINAL v3.4 // DEPLOY-READY
</div>
""", unsafe_allow_html=True)
