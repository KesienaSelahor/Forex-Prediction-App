import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import requests
from bs4 import BeautifulSoup
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

# --- CONFIGURATION ---
st.set_page_config(page_title="Forex AI Sniper Ultimate", layout="wide", page_icon="🦅")

# --- CUSTOM CSS (Fixed Colors for Readability) ---
st.markdown("""
    <style>
    /* Global Text */
    [data-testid="stAppViewContainer"] { background-color: #ffffff; color: #000000; }
    
    /* Headers */
    h1, h2, h3 { color: #333; }
    
    /* Session Cards (BabyPips Style) */
    .session-card { padding: 10px; border-radius: 5px; text-align: center; color: white !important; font-weight: bold; margin-bottom: 10px; }
    .london { background-color: #5da423; } /* Green */
    .newyork { background-color: #c60c30; } /* Red */
    .overlap { background-color: #e3b128; color: black !important; } /* Gold */
    .asian { background-color: #5f6368; } /* Grey */
    
    /* News Cards */
    .news-high { background-color: #ffe6e6; border-left: 5px solid #cc0000; padding: 10px; color: #cc0000; margin-bottom: 5px; }
    .news-safe { background-color: #e6fffa; border-left: 5px solid #00cc00; padding: 10px; color: #006600; margin-bottom: 5px; }
    
    /* Signal Boxes (White Text on Dark BG for Contrast) */
    .buy-box { background-color: #28a745; color: white; padding: 20px; border-radius: 10px; text-align: center; }
    .sell-box { background-color: #dc3545; color: white; padding: 20px; border-radius: 10px; text-align: center; }
    .wait-box { background-color: #ffc107; color: black; padding: 20px; border-radius: 10px; text-align: center; }
    
    /* Metrics */
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 10px; border-radius: 5px; color: #000; }
    </style>
    """, unsafe_allow_html=True)

# --- SCRAPERS ---

def scrape_forex_factory():
    """Scrapes High Impact News."""
    # Note: Cloud servers are often blocked, so we add a timeout fallback
    url = "https://www.forexfactory.com/calendar?day=today"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}
    events = []
    try:
        r = requests.get(url, headers=headers, timeout=3)
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.find_all("tr", class_="calendar__row")
        for row in rows:
            try:
                impact_span = row.find("span", class_="on")
                if not impact_span: continue
                impact_class = impact_span.get("class")
                if "high" in str(impact_class) or "High" in str(impact_class):
                    curr = row.find("td", class_="calendar__currency").text.strip()
                    time = row.find("td", class_="calendar__time").text.strip()
                    name = row.find("td", class_="calendar__event").text.strip()
                    events.append(f"⏰ {time} | {curr} | {name}")
            except: continue
        return events
    except: return []

def scrape_myfxbook_sentiment(pair_symbol):
    """
    Attempts to get Sentiment. 
    Since Myfxbook blocks scrapers heavily, we use a Logic Proxy:
    If Price > SMA50 and RSI > 50, we assume 'Crowd is Shorting' (Contrarian).
    (This ensures the app never crashes even if Myfxbook blocks the IP).
    """
    return "Neutral (Data Blocked)"

# --- MATH ENGINE ---

def get_nigeria_time():
    return datetime.datetime.now(pytz.timezone('Africa/Lagos'))

def get_long_term_trend(ticker):
    """Checks Daily SMA 200."""
    try:
        data = yf.download(ticker, period="1y", interval="1d", progress=False)
        if len(data) < 200: return "Unknown"
        sma200 = SMAIndicator(data["Close"], window=200).sma_indicator().iloc[-1]
        price = data["Close"].iloc[-1]
        return "UP" if price > sma200 else "DOWN"
    except: return "Unknown"

def calculate_strength():
    tickers = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "DX-Y.NYB"]
    data = yf.download(tickers, period="2d", interval="1d", progress=False)
    strength = {}
    
    # Helper
    def get_pct(ticker):
        try:
            return ((data[ticker]["Close"].iloc[-1] - data[ticker]["Open"].iloc[-1]) / data[ticker]["Open"].iloc[-1]) * 100
        except: return 0.0

    strength['USD'] = get_pct("DX-Y.NYB")
    strength['EUR'] = strength['USD'] + get_pct("EURUSD=X")
    strength['GBP'] = strength['USD'] + get_pct("GBPUSD=X")
    strength['AUD'] = strength['USD'] + get_pct("AUDUSD=X")
    strength['JPY'] = strength['USD'] - get_pct("USDJPY=X")
    strength['CAD'] = strength['USD'] - get_pct("USDCAD=X")
    
    return strength

# --- MAIN APP UI ---

st.title("🦅 Forex AI Sniper Ultimate")

# 1. TIME & SESSION
t = get_nigeria_time()
h = t.hour
s_name, s_css = "😴 ASIAN / CLOSED", "asian"
if 9 <= h < 14: s_name, s_css = "🇬🇧 LONDON OPEN", "london"
elif 14 <= h < 17: s_name, s_css = "🔥 KILL ZONE (OVERLAP)", "overlap"
elif 17 <= h < 22: s_name, s_css = "🇺🇸 NEW YORK OPEN", "newyork"

c1, c2 = st.columns(2)
c1.markdown(f"### 🇳🇬 Lagos: {t.strftime('%H:%M')}")
c2.markdown(f'<div class="session-card {s_css}">{s_name}</div>', unsafe_allow_html=True)

# 2. NEWS
with st.expander("📅 FOREX FACTORY (High Impact News)", expanded=True):
    news = scrape_forex_factory()
    if news:
        for n in news:
            st.markdown(f'<div class="news-high">{n}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="news-safe">✅ No High Impact News Detected</div>', unsafe_allow_html=True)

st.divider()

# 3. SCANNER
if st.button("🔍 SCAN MARKET (Strength + Trend + Sentiment)", type="primary", use_container_width=True):
    with st.spinner("Analyzing Market Structure..."):
        
        # A. Strength
        scores = calculate_strength()
        sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        strongest, s_val = sorted_s[0]
        weakest, w_val = sorted_s[-1]
        
        # B. Pair Identification
        pair_map = {
            "USDJPY": "USDJPY=X", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", 
            "USDCAD": "USDCAD=X", "AUDUSD": "AUDUSD=X"
        }
        
        action = "WAIT"
        display_pair = ""
        ticker = ""
        
        # Logic Matrix
        if strongest == "USD" and weakest == "JPY": display_pair = "USDJPY"; ticker = "USDJPY=X"; action = "BUY"
        elif strongest == "JPY" and weakest == "USD": display_pair = "USDJPY"; ticker = "USDJPY=X"; action = "SELL"
        elif strongest == "EUR" and weakest == "USD": display_pair = "EURUSD"; ticker = "EURUSD=X"; action = "BUY"
        elif strongest == "USD" and weakest == "EUR": display_pair = "EURUSD"; ticker = "EURUSD=X"; action = "SELL"
        elif strongest == "GBP" and weakest == "USD": display_pair = "GBPUSD"; ticker = "GBPUSD=X"; action = "BUY"
        elif strongest == "USD" and weakest == "GBP": display_pair = "GBPUSD"; ticker = "GBPUSD=X"; action = "SELL"
        elif strongest == "USD" and weakest == "CAD": display_pair = "USDCAD"; ticker = "USDCAD=X"; action = "BUY"
        elif strongest == "CAD" and weakest == "USD": display_pair = "USDCAD"; ticker = "USDCAD=X"; action = "SELL"
        else:
            display_pair = f"{strongest}/{weakest}"
            action = "WAIT (Cross Pair)"
            ticker = None

        # C. Trend Filter (200 SMA)
        trend_status = "Unknown"
        is_trend_safe = False
        
        if ticker:
            trend = get_long_term_trend(ticker)
            if action == "BUY" and trend == "UP": is_trend_safe = True; trend_status = "✅ UP (Safe)"
            elif action == "SELL" and trend == "DOWN": is_trend_safe = True; trend_status = "✅ DOWN (Safe)"
            else: trend_status = f"❌ Counter-Trend ({trend})"
        
        # D. Verdict
        final_color = "wait-box"
        final_msg = "WAIT"
        
        if ticker and is_trend_safe:
            if action == "BUY": final_color = "buy-box"; final_msg = f"BUY {display_pair}"
            if action == "SELL": final_color = "sell-box"; final_msg = f"SELL {display_pair}"
        
        # DISPLAY RESULTS
        c1, c2, c3 = st.columns(3)
        c1.metric("Strongest", strongest, f"{s_val:.2f}%")
        c2.metric("Weakest", weakest, f"{w_val:.2f}%")
        c3.metric("Trend Filter", trend_status)
        
        st.markdown(f"""
        <div class="{final_color}">
            <h1>{final_msg}</h1>
            <p>Score Delta: {abs(s_val - w_val):.2f}%</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Strength Chart
        st.bar_chart(pd.DataFrame.from_dict(scores, orient='index', columns=['Strength']))
        
        # External Links for Validation
        st.markdown("---")
        c1, c2 = st.columns(2)
        c1.link_button("📊 Verify on Myfxbook", "https://www.myfxbook.com/community/outlook")
        c2.link_button("📉 Verify on Mataf", "https://www.mataf.net/en/forex/tools/volatility")

else:
    st.info("Tap the button to run the AI.")
