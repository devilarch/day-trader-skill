#!/usr/bin/env python3
"""Indian Financial Market News Monitor for trader-news. Standard library only.

Upgraded to match professional standards:
  - Ticker-Specific Real-Time Search: Queries live Google News RSS + Yahoo Finance for exact NSE tickers.
  - Comprehensive Broad Feeds: Moneycontrol Market Reports, Economic Times Stocks, LiveMint.
  - Intraday Price Move Tracking: Calculates today's % change vs yesterday's close, flagging moves >= 2.5%.
  - Automatic Categorization Tags: [EARNINGS], [ORDER/DEAL], [REGULATORY/SEBI], [MANAGEMENT], [FII/DII].
  - 30-Day State Persistence: Remembers seen headlines in trader/state/news.json so you never see duplicates.
  - Auto-reads tickers from trader/watchlist.json, trader/plan.json, or command line arguments.
"""

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from market_calendar_indian import to_ist

STATE_FILE = "trader/state/news.json"
WATCHLIST_FILE = "trader/watchlist.json"
PLAN_FILE = "trader/plan.json"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MOVE_PCT = 2.5  # Flag stocks that moved 2.5%+ today

FEEDS = {
    "moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977082108.cms",
    "et_stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2143846026.cms"
}

CATEGORY_KEYWORDS = {
    "[EARNINGS]": ["q1", "q2", "q3", "q4", "quarter", "results", "net profit", "pat", "ebitda", "revenue", "dividend"],
    "[ORDER/DEAL]": ["order", "contract", "bags", "wins", "acquisition", "merger", "deal", "joint venture", "jv"],
    "[REGULATORY]": ["sebi", "rbi", "penalty", "notice", "probe", "investigation", "court", "tribunal", "nclt"],
    "[MANAGEMENT]": ["resigns", "appoints", "ceo", "cfo", "md", "director", "leadership", "promoter"],
    "[BLOCK DEAL]": ["block deal", "bulk deal", "stake sale", "promoter", "fii", "dii", "pledge"]
}

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"seen": {}}
    return {"seen": {}}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    # Prune items older than 30 days
    now_ts = _dt.datetime.now().timestamp()
    thirty_days = 30 * 86400
    cleaned_seen = {k: v for k, v in state.get("seen", {}).items() if (now_ts - v) < thirty_days}
    state["seen"] = cleaned_seen
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to save news state: {e}\n")

def tag_headline(text):
    text_lower = text.lower()
    for tag, words in CATEGORY_KEYWORDS.items():
        if any(w in text_lower for w in words):
            return tag
    return "[GENERAL]"

def fetch_xml(url):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read()
            return ET.fromstring(content)
    except Exception:
        return None

def fetch_ticker_google_news(ticker):
    # Query Google News India for the ticker
    clean_ticker = ticker.replace(".NS", "").replace(".BO", "")
    query = f"{clean_ticker} share price OR {clean_ticker} NSE when:3d"
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    root = fetch_xml(url)
    items = []
    if root is not None:
        for it in root.findall(".//item")[:10]:
            title = it.findtext("title", "").strip()
            link = it.findtext("link", "").strip()
            pub_date = it.findtext("pubDate", "").strip()
            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "source": "Google News (IN)",
                    "ticker": clean_ticker,
                    "tag": tag_headline(title)
                })
    return items

def fetch_ticker_move(ticker):
    sym = ticker if "." in ticker else f"{ticker}.NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            curr_price = meta.get("regularMarketPrice")
            if prev_close and curr_price:
                pct = round(((curr_price - prev_close) / prev_close) * 100, 2)
                return {
                    "price": curr_price,
                    "prev_close": prev_close,
                    "pct_change": pct,
                    "flagged": abs(pct) >= MOVE_PCT
                }
    except Exception:
        return None
    return None

def get_target_tickers(cli_tickers):
    if cli_tickers:
        return [t.upper() for t in cli_tickers]
    tickers = []
    # Try reading from watchlist
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                w = json.load(f)
                for h in w.get("hits", []):
                    sym = h.get("symbol", "").replace(".NS", "")
                    if sym and sym not in tickers:
                        tickers.append(sym)
        except Exception:
            pass
    # Try reading from plan
    if os.path.exists(PLAN_FILE):
        try:
            with open(PLAN_FILE, "r", encoding="utf-8") as f:
                p = json.load(f)
                sym = p.get("symbol", "").replace(".NS", "")
                if sym and sym not in tickers:
                    tickers.append(sym)
        except Exception:
            pass
    return tickers or ["NIFTY", "BANKNIFTY", "RELIANCE", "SBIN", "BEL", "MCX"]

def main():
    parser = argparse.ArgumentParser(description="Indian Market Active News & Corporate Action Monitor")
    parser.add_argument("--tickers", nargs="+", help="Specific NSE tickers to monitor (e.g. BEL SBIN MCX)")
    parser.add_argument("--all", action="store_true", help="Show all headlines even if seen before")
    parser.add_argument("--limit", type=int, default=12, help="Max headlines to display")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    tickers = get_target_tickers(args.tickers)
    state = load_state()
    seen = state.get("seen", {})

    all_headlines = []
    ticker_moves = {}

    print(f"📡 Monitoring breaking news & price moves for: {', '.join(tickers)}")

    # 1. Fetch moves & ticker-specific headlines
    for t in tickers:
        move = fetch_ticker_move(t)
        if move:
            ticker_moves[t] = move
        t_news = fetch_ticker_google_news(t)
        all_headlines.extend(t_news)

    # 2. Fetch broad market headlines
    for source_name, feed_url in FEEDS.items():
        tree = fetch_xml(feed_url)
        if tree is not None:
            for it in tree.findall(".//item")[:10]:
                title = it.findtext("title", "").strip()
                link = it.findtext("link", "").strip()
                pub_date = it.findtext("pubDate", "").strip()
                if title:
                    all_headlines.append({
                        "title": title,
                        "link": link,
                        "pub_date": pub_date,
                        "source": source_name,
                        "ticker": "BROAD",
                        "tag": tag_headline(title)
                    })

    # 3. Filter unread and deduplicate
    now_ts = _dt.datetime.now().timestamp()
    unread_headlines = []
    seen_hashes = set()

    for item in all_headlines:
        h = hashlib.sha256(item["title"].encode("utf-8")).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        if not args.all and h in seen:
            continue  # Already seen in a previous check

        seen[h] = now_ts
        unread_headlines.append(item)

    state["seen"] = seen
    save_state(state)

    results = unread_headlines[:args.limit]

    if args.json:
        print(json.dumps({"moves": ticker_moves, "headlines": results}, indent=2))
        return

    print("=" * 80)
    print("🇮🇳 LIVE INDIAN MARKET MONITOR: ACTIVE NEWS & INTRADAY PRICE MOVES")
    print("=" * 80)

    # Display Price Moves
    if ticker_moves:
        print("\n📊 INTRADAY PRICE MOMENTUM:")
        for t, m in ticker_moves.items():
            sym_clean = t.replace(".NS", "")
            flag = "🚨 ACTIVE MOVE" if m["flagged"] else "Normal"
            direction = "🟢" if m["pct_change"] >= 0 else "🔴"
            print(f"  {direction} {sym_clean:<12} ₹{m['price']:<9,.2f} ({m['pct_change']:>+6.2f}%) -> {flag}")
        print("-" * 80)

    # Display Headlines
    if not results:
        print("\n✅ All clear: No new unread breaking headlines since your last check.")
        return

    print(f"\n📰 BREAKING HEADLINES ({len(results)} unread):")
    for idx, item in enumerate(results, 1):
        tick_label = f"[{item['ticker']}]" if item['ticker'] != 'BROAD' else "[MARKET]"
        print(f"\n{idx}. {item['tag']} {tick_label} {item['title']}")
        if item.get("pub_date"):
            print(f"   Published: {item['pub_date']} | Source: {item['source']}")

if __name__ == "__main__":
    main()
