#!/usr/bin/env python3
"""
India Equity Daily Intelligence Report Generator
-------------------------------------------------
Runs via GitHub Actions on a cron schedule (7:00 AM IST, Mon–Fri).
  1. Fetches live market data via yfinance (indices + key stocks)
  2. Tries to pull news headlines from RSS feeds
  3. Calls Claude API (claude-opus-4-6) to generate a full styled HTML report
  4. Saves the HTML to output/ and emails it via Gmail SMTP

Required environment variables (set as GitHub Secrets):
  ANTHROPIC_API_KEY   — your Anthropic API key
  GMAIL_USER          — your Gmail address (e.g. goutam.bang@gmail.com)
  GMAIL_APP_PASSWORD  — Gmail App Password (not your regular password)
  RECIPIENT_EMAIL     — destination email (defaults to GMAIL_USER if not set)
"""

import os
import re
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
import pytz
import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

IST = pytz.timezone("Asia/Kolkata")
NOW = datetime.now(IST)
DATE_STR = NOW.strftime("%B %d, %Y")
DATE_FILE = NOW.strftime("%Y-%m-%d")
WEEKDAY = NOW.strftime("%A")

MODEL = "claude-opus-4-6"
MAX_TOKENS = 8000

# ---------------------------------------------------------------------------
# 1. Market Data — Indices
# ---------------------------------------------------------------------------

INDICES = {
    "Nifty 50":    "^NSEI",
    "Sensex":      "^BSESN",
    "Nifty Bank":  "^NSEBANK",
    "Dow Jones":   "^DJI",
    "S&P 500":     "^GSPC",
    "Nasdaq":      "^IXIC",
    "Nikkei 225":  "^N225",
    "Hang Seng":   "^HSI",
}

# Key NSE stocks (symbol.NS format for yfinance)
STOCKS = {
    "TCS":           "TCS.NS",
    "Infosys":       "INFY.NS",
    "HDFC Bank":     "HDFCBANK.NS",
    "Reliance":      "RELIANCE.NS",
    "ICICI Bank":    "ICICIBANK.NS",
    "Bharti Airtel": "BHARTIARTL.NS",
    "HUL":           "HINDUNILVR.NS",
    "Bajaj Finance": "BAJFINANCE.NS",
    "L&T":           "LT.NS",
    "BEL":           "BEL.NS",
    "HAL":           "HAL.NS",
    "Tata Steel":    "TATASTEEL.NS",
    "NTPC":          "NTPC.NS",
    "Tata Consumer": "TATACONSUM.NS",
    "Adani Ports":   "ADANIPORTS.NS",
    "Dixon Tech":    "DIXON.NS",
    "M&M":           "M&M.NS",
    "Cummins India": "CUMMINSIND.NS",
    "Siemens India": "SIEMENS.NS",
    "IEX":           "IEX.NS",
    "Indus Towers":  "INDUSTOWER.NS",
    "Canara Bank":   "CANBK.NS",
    "BPCL":          "BPCL.NS",
    "KNR Constructions": "KNRCON.NS",
    "Mazagon Dock":  "MAZDOCK.NS",
}


def fetch_index_data() -> dict:
    results = {}
    for name, symbol in INDICES.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if len(hist) >= 2:
                close   = hist["Close"].iloc[-1]
                prev    = hist["Close"].iloc[-2]
                change  = close - prev
                pct     = change / prev * 100
                results[name] = {
                    "symbol": symbol,
                    "close":  round(close, 2),
                    "change": round(change, 2),
                    "pct":    round(pct, 2),
                }
        except Exception as e:
            results[name] = {"symbol": symbol, "error": str(e)[:80]}
    return results


def fetch_stock_data() -> dict:
    results = {}
    for name, symbol in STOCKS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period="3d")
            hist1y = ticker.history(period="1y")

            if len(hist) >= 2:
                close  = hist["Close"].iloc[-1]
                prev   = hist["Close"].iloc[-2]
                vol    = int(hist["Volume"].iloc[-1])
                change = close - prev
                pct    = change / prev * 100

                high52 = round(hist1y["High"].max(), 2) if not hist1y.empty else None
                low52  = round(hist1y["Low"].min(),  2) if not hist1y.empty else None
                near_high = bool(high52 and close >= high52 * 0.95)

                results[name] = {
                    "symbol":    symbol,
                    "close":     round(close, 2),
                    "change":    round(change, 2),
                    "pct":       round(pct, 2),
                    "volume":    vol,
                    "high52":    high52,
                    "low52":     low52,
                    "near_high": near_high,
                }
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# 2. News — RSS feeds
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    ("https://feeds.feedburner.com/ndtvprofit-latest",         "NDTV Profit"),
    ("https://economictimes.indiatimes.com/markets/rss.cms",   "ET Markets"),
    ("https://www.moneycontrol.com/rss/marketreports.xml",     "Moneycontrol"),
]


def fetch_news(max_items: int = 12) -> list[str]:
    headlines = []
    for url, source in RSS_FEEDS:
        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                # Pull titles from RSS — CDATA or plain
                titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
                if not titles:
                    titles = re.findall(r"<title>(.*?)</title>", resp.text)
                # Skip the first entry (feed title itself)
                for title in titles[1:8]:
                    clean = re.sub(r"<[^>]+>", "", title).strip()
                    if clean:
                        headlines.append(f"[{source}] {clean}")
        except Exception:
            pass

    if not headlines:
        headlines = ["[Note] News RSS feeds unavailable — Claude will use latest trained knowledge for news context."]

    return headlines[:max_items]


# ---------------------------------------------------------------------------
# 3. Format data for the Claude prompt
# ---------------------------------------------------------------------------

def build_market_summary(indices: dict, stocks: dict, news: list[str]) -> str:
    lines = [f"=== LIVE MARKET DATA — {DATE_STR} ({WEEKDAY}) IST ===\n"]

    # Indices
    lines.append("--- MAJOR INDICES ---")
    for name, d in indices.items():
        if "error" in d:
            lines.append(f"  {name}: unavailable ({d['error']})")
        else:
            sign = "+" if d["change"] >= 0 else ""
            lines.append(f"  {name} ({d['symbol']}): {d['close']:>10,.2f}  {sign}{d['change']:+,.2f}  ({sign}{d['pct']:+.2f}%)")

    # Stocks — sorted best→worst
    lines.append("\n--- NSE STOCKS (sorted by % change) ---")
    sorted_stocks = sorted(
        [(n, d) for n, d in stocks.items() if "pct" in d],
        key=lambda x: x[1]["pct"],
        reverse=True,
    )
    for name, d in sorted_stocks:
        hi_flag = "  ⭐ NEAR 52W HIGH" if d.get("near_high") else ""
        range_str = f"  | 52W: {d['low52']:.0f}–{d['high52']:.0f}" if d.get("high52") else ""
        lines.append(
            f"  {name:<20} ₹{d['close']:>8,.2f}  ({d['pct']:+.2f}%)"
            f"  vol {d['volume']:,}{hi_flag}{range_str}"
        )

    # News
    lines.append("\n--- LATEST NEWS HEADLINES ---")
    for h in news:
        lines.append(f"  • {h}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Claude API — generate full HTML report
# ---------------------------------------------------------------------------

REPORT_PROMPT = """\
You are a senior Indian equity research analyst. Today is {date_str} IST.

Below is real-time market data collected moments ago via yfinance and news RSS feeds:

{market_summary}

Generate a complete, self-contained HTML report with the following title:
"🇮🇳 India Equity Daily Intelligence Report — {date_str}"

━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN RULES (strictly follow)
━━━━━━━━━━━━━━━━━━━━━━━━
• Fully self-contained HTML — all CSS inside a <style> block, no external stylesheets.
• Dark theme: body bg #0f1117, card bg #1a202c, borders #2d3748, body text #e2e8f0, accent #90cdf4.
• Layout: table-based (NOT flexbox/grid) so it renders identically in browsers and email clients.
• Color coding:
    - gains / positive / buy  → #48bb78 (green)
    - losses / negative / avoid → #fc8181 (red)
    - alerts / watch / neutral → #f6e05e (yellow)
• Badges (.buy, .watch, .avoid) with colored pill backgrounds.
• Every <table> must have a dark header row (bg #2d3748, text #90cdf4).
• Alert boxes: left-border only (3px solid), matching bg tint, compact padding.

━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED SECTIONS (use the live data above, supplement with your analysis)
━━━━━━━━━━━━━━━━━━━━━━━━
1. Market Overview
   - Table: each index → Level, Change (pts), % Change, YTD est., Key Levels.
   - Use EXACT numbers from the live data above.
   - Nifty key levels: resistance, support 1, support 2.
   - Global cues sub-table (US + Asia from live data).
   - Alert box summarising the overnight cue implication for India.

2. Top Movers
   - Top 5 gainers and top 5 losers from the live stock data (by % change).
   - State catalyst/reason for each move.
   - Separate sub-tables for large-cap and mid/small-cap.

3. Fundamental Picks (5–7 stocks)
   - Criteria: ROE >15%, D/E <0.5, Revenue/Profit growth >15% YoY, PEG <1.5.
   - Columns: Stock, Symbol, Cap badge, ROE, D/E, Growth, Key Thesis.

4. Technical Signals
   - Stocks near 52W high (flagged with ⭐ in live data above).
   - RSI oversold/overbought candidates.
   - Golden cross (50 DMA > 200 DMA) candidates.
   - Volume spike alerts.

5. News & Sentiment
   - Analyse the news headlines from the live data above — group by theme.
   - FII/DII context (use latest available intelligence).
   - RBI, SEBI, government policy mentions.

6. Annual Report / Concall Hotspots
   - Q4 FY26 earnings season highlights for BEL, Tata Consumer, SBI, IEX, and IT sector.
   - Flag: guidance changes, capex plans, margin trends, any red flags.

7. Sector Spotlight
   - Pick the ONE sector most relevant today (use news + index moves to decide).
   - Give 2–3 specific stock picks within it with rationale.

8. Decision Framework — Buy / Watch / Avoid
   - Table of exactly 10 stocks.
   - Columns: #, Stock (Symbol), Cap badge, Signal badge, One-line reasoning.

End with a disclaimer paragraph in a grey muted box.

━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY the raw HTML document. No markdown, no code fences, no explanation.
Start with exactly: <!DOCTYPE html>
"""


def generate_html_report(market_summary: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = REPORT_PROMPT.format(date_str=DATE_STR, market_summary=market_summary)

    print("  → Calling Claude API…")
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    html = message.content[0].text.strip()

    # Safety: strip any accidental markdown code fences
    if html.startswith("```"):
        html = re.sub(r"^```[a-z]*\n?", "", html)
        html = re.sub(r"\n?```$", "", html)

    return html


# ---------------------------------------------------------------------------
# 5. Save report
# ---------------------------------------------------------------------------

def save_report(html: str) -> Path:
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"india_equity_scan_{DATE_FILE}.html"
    path.write_text(html, encoding="utf-8")
    print(f"  → Saved: {path}")
    return path


# ---------------------------------------------------------------------------
# 6. Email via Gmail SMTP
# ---------------------------------------------------------------------------

def send_email(html: str, nifty_level: str) -> None:
    sender    = os.environ["GMAIL_USER"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)
    subject   = f"🇮🇳 India Equity Scan — {DATE_STR} | Nifty {nifty_level}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"  → Sending email to {recipient}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    print("  → Email sent ✅")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n🇮🇳 India Equity Scan — {DATE_STR} ({WEEKDAY})")
    print("=" * 55)

    print("\n[1/5] Fetching index data…")
    indices = fetch_index_data()
    for name, d in indices.items():
        if "error" not in d:
            sign = "+" if d["pct"] >= 0 else ""
            print(f"       {name}: {d['close']:,.2f} ({sign}{d['pct']:.2f}%)")
        else:
            print(f"       {name}: ERROR — {d['error']}")

    print("\n[2/5] Fetching stock data…")
    stocks = fetch_stock_data()
    print(f"       {len(stocks)} stocks fetched.")

    print("\n[3/5] Fetching news headlines…")
    news = fetch_news()
    for h in news[:3]:
        print(f"       {h[:90]}")
    if len(news) > 3:
        print(f"       … and {len(news) - 3} more")

    market_summary = build_market_summary(indices, stocks, news)

    print("\n[4/5] Generating HTML report via Claude API…")
    html_report = generate_html_report(market_summary)
    print(f"       Report length: {len(html_report):,} chars")

    save_report(html_report)

    # Get Nifty level for email subject
    nifty_str = "—"
    if "Nifty 50" in indices and "close" in indices["Nifty 50"]:
        nifty_str = f"{indices['Nifty 50']['close']:,.0f}"

    print("\n[5/5] Sending email…")
    send_email(html_report, nifty_str)

    print("\n✅ All done!\n")


if __name__ == "__main__":
    # Validate required env vars before running
    missing = [v for v in ("ANTHROPIC_API_KEY", "GMAIL_USER", "GMAIL_APP_PASSWORD") if not os.environ.get(v)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    main()
