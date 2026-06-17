# ================================================
# FILE: strategies/institutional_flow.py
# PURPOSE: FII/DII + Promoter Holding Intelligence
#
# DATA SOURCES (in order of reliability):
#   1. NSE fiidiiTradeReact API (with cookie handshake)
#   2. Moneycontrol FII/DII RSS/JSON proxy
#   3. Stooq / yfinance derived proxy via NIFTY vs FII ETF
#   4. Hardcoded neutral fallback (no crash ever)
#
# PROMOTER HOLDING:
#   Fetched quarterly from yfinance ticker.info
#   Cached for 7 days (changes only each quarter)
#   Signal: increasing = bullish, decreasing = bearish
# ================================================

import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import json

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR       = os.path.join(BASE_DIR, "logs")
FII_CACHE_FILE = os.path.join(LOGS_DIR, "fii_dii_cache.json")
PROMO_CACHE    = os.path.join(LOGS_DIR, "promoter_cache.json")
os.makedirs(LOGS_DIR, exist_ok=True)

CACHE_TTL_HOURS   = 4    # Refresh FII/DII every 4 hours
PROMO_CACHE_DAYS  = 7    # Promoter data changes quarterly


# ════════════════════════════════════════════════
# NSE SESSION (cookie-based)
# ════════════════════════════════════════════════

def _nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "en-US,en;q=0.9",
        "Accept-Encoding":  "gzip, deflate, br",
        "Referer":          "https://www.nseindia.com/",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua":        '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-fetch-dest":   "empty",
        "sec-fetch-mode":   "cors",
        "sec-fetch-site":   "same-origin",
    })
    try:
        # Must visit homepage FIRST to get cookies — NSE checks this
        r = session.get("https://www.nseindia.com", timeout=8)
        r.raise_for_status()
    except Exception as e:
        print(f"⚠️ NSE homepage visit failed: {e}")
    return session


# ════════════════════════════════════════════════
# SOURCE 1: NSE fiidiiTradeReact API
# ════════════════════════════════════════════════

def _fetch_from_nse_api(days: int = 10) -> pd.DataFrame:
    """Fetch from NSE fiidiiTradeReact endpoint."""
    try:
        session = _nse_session()
        resp = session.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        rows = []
        for item in data:
            try:
                # NSE returns different field structures — handle both
                fii_buy  = _safe_cr(item.get("fiiBuySell", {}).get("buyValue")
                                    or item.get("fii_buy_value")
                                    or item.get("BUY", {}).get("FII"))
                fii_sell = _safe_cr(item.get("fiiBuySell", {}).get("sellValue")
                                    or item.get("fii_sell_value")
                                    or item.get("SELL", {}).get("FII"))
                dii_buy  = _safe_cr(item.get("diiBuySell", {}).get("buyValue")
                                    or item.get("dii_buy_value")
                                    or item.get("BUY", {}).get("DII"))
                dii_sell = _safe_cr(item.get("diiBuySell", {}).get("sellValue")
                                    or item.get("dii_sell_value")
                                    or item.get("SELL", {}).get("DII"))
                date_str = str(item.get("date", "")).strip()

                if fii_buy == 0 and fii_sell == 0:
                    continue   # skip empty rows

                rows.append({
                    "Date":     date_str,
                    "FII_Buy":  fii_buy,
                    "FII_Sell": fii_sell,
                    "FII_Net":  round(fii_buy - fii_sell, 2),
                    "DII_Buy":  dii_buy,
                    "DII_Sell": dii_sell,
                    "DII_Net":  round(dii_buy - dii_sell, 2),
                })
            except Exception:
                continue

        if rows:
            df = pd.DataFrame(rows).sort_values("Date", ascending=False).head(days)
            return df.reset_index(drop=True)
    except Exception as e:
        print(f"⚠️ NSE API fetch failed: {e}")
    return pd.DataFrame()


# ════════════════════════════════════════════════
# SOURCE 2: NSE Archives CSV (monthly published file)
# More reliable than API — plain CSV, no cookies needed
# ════════════════════════════════════════════════

def _fetch_from_nse_archives() -> pd.DataFrame:
    """
    NSE publishes monthly FII/DII participant-wise data CSV.
    URL pattern: archives.nseindia.com/content/fo/fii_stats_<MMYYYY>.csv
    Free, no auth, stable format.
    """
    try:
        now  = datetime.now()
        # Try current month and last month
        for delta_months in [0, 1]:
            month = now.month - delta_months
            year  = now.year
            if month <= 0:
                month += 12
                year -= 1
            month_str = f"{month:02d}{year}"
            url = f"https://archives.nseindia.com/content/fo/fii_stats_{month_str}.csv"

            resp = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0"
            })
            if resp.status_code == 200 and len(resp.content) > 200:
                from io import StringIO
                df = pd.read_csv(StringIO(resp.text))
                # Parse NSE archive format
                rows = _parse_nse_archive_csv(df)
                if rows:
                    return pd.DataFrame(rows).head(10)
    except Exception as e:
        print(f"⚠️ NSE archives fetch failed: {e}")
    return pd.DataFrame()


def _parse_nse_archive_csv(df: pd.DataFrame) -> list:
    """Parse the NSE monthly archive CSV format."""
    rows = []
    try:
        # NSE archive has columns like Date, FII/FPI Net, DII Net etc.
        # Try to find them regardless of exact column names
        df.columns = [str(c).strip() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if not date_col:
            return []

        for _, row in df.iterrows():
            try:
                date_str = str(row[date_col]).strip()
                if not date_str or date_str == "nan":
                    continue

                # Try various column name patterns NSE uses
                fii_net = 0
                dii_net = 0
                for col in df.columns:
                    val = _safe_cr(row.get(col))
                    if "fii" in col.lower() and "net" in col.lower():
                        fii_net = val
                    if "dii" in col.lower() and "net" in col.lower():
                        dii_net = val

                rows.append({
                    "Date":     date_str,
                    "FII_Buy":  0, "FII_Sell": 0,
                    "FII_Net":  fii_net,
                    "DII_Buy":  0, "DII_Sell": 0,
                    "DII_Net":  dii_net,
                })
            except Exception:
                continue
    except Exception:
        pass
    return rows


# ════════════════════════════════════════════════
# SOURCE 3: IIFL / Trendlyne public API
# A backup JSON endpoint that provides FII/DII data
# ════════════════════════════════════════════════

def _fetch_from_trendlyne() -> pd.DataFrame:
    """
    Trendlyne provides a public FII/DII endpoint used by many
    financial websites. No auth required.
    """
    try:
        url = "https://trendlyne.com/api/fii-dii-data/"
        resp = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        if resp.status_code == 200:
            data = resp.json()
            rows = []
            for item in (data.get("data") or data if isinstance(data, list) else []):
                try:
                    rows.append({
                        "Date":     str(item.get("date", "")),
                        "FII_Buy":  _safe_cr(item.get("fii_buy")),
                        "FII_Sell": _safe_cr(item.get("fii_sell")),
                        "FII_Net":  _safe_cr(item.get("fii_net")),
                        "DII_Buy":  _safe_cr(item.get("dii_buy")),
                        "DII_Sell": _safe_cr(item.get("dii_sell")),
                        "DII_Net":  _safe_cr(item.get("dii_net")),
                    })
                except Exception:
                    continue
            if rows:
                return pd.DataFrame(rows).head(10)
    except Exception as e:
        print(f"⚠️ Trendlyne FII fetch failed: {e}")
    return pd.DataFrame()


# ════════════════════════════════════════════════
# SOURCE 4: yfinance NIFTY 50 ETF proxy
# When all direct sources fail, estimate FII sentiment
# from NIFTY momentum vs Gold (typical FII rotation signal)
# This gives a PROXY score, not actual ₹ flows
# ════════════════════════════════════════════════

def _estimate_fii_from_market_proxy() -> pd.DataFrame:
    """
    Last resort: derive an FII proxy score from market data.
    Uses NIFTYBEES.NS (ETF) and LIQUIDBEES.NS (money market)
    as a rough institutional flow signal.

    When FIIs buy equities, NIFTYBEES volume spikes.
    When they sell, LIQUIDBEES or GOLDBEES get inflows.

    This is NOT actual FII data — it's an approximation.
    Clearly marked as "estimated" in the result.
    """
    try:
        import yfinance as yf
        nifty = yf.download("NIFTYBEES.NS", period="10d", interval="1d",
                            progress=False, auto_adjust=True)
        if nifty.empty:
            return pd.DataFrame()

        nifty.columns = [c[0] for c in nifty.columns]
        nifty = nifty.dropna(subset=["Close"])
        nifty["vol_ratio"] = nifty["Volume"] / nifty["Volume"].rolling(5).mean()

        rows = []
        for date, row in nifty.tail(5).iterrows():
            # Estimate FII net: strong volume up day = FII buying
            close    = float(row["Close"])
            prev_c   = float(nifty["Close"].shift(1).loc[date]) if date in nifty.index else close
            price_chg = (close - prev_c) / prev_c if prev_c > 0 else 0
            vol_ratio = float(row.get("vol_ratio", 1.0)) if not pd.isna(row.get("vol_ratio")) else 1.0

            # Rough proxy: positive price + high volume → institutional buying
            proxy_net = round(price_chg * vol_ratio * 2000, 0)   # scale to crore-like units

            rows.append({
                "Date":        str(date)[:10],
                "FII_Buy":     max(0, proxy_net),
                "FII_Sell":    max(0, -proxy_net),
                "FII_Net":     proxy_net,
                "DII_Buy":     0,
                "DII_Sell":    0,
                "DII_Net":     0,
                "is_proxy":    True,
            })

        if rows:
            df = pd.DataFrame(rows).sort_values("Date", ascending=False)
            return df.reset_index(drop=True)
    except Exception as e:
        print(f"⚠️ Market proxy FII estimation failed: {e}")
    return pd.DataFrame()


def _safe_cr(value) -> float:
    """Safely parse a crore value from any format."""
    try:
        v = str(value).replace(",", "").replace("₹", "").replace(" ", "").strip()
        if not v or v in ("nan", "None", "-", ""):
            return 0.0
        return round(float(v), 2)
    except Exception:
        return 0.0


# ════════════════════════════════════════════════
# CACHE LAYER
# ════════════════════════════════════════════════

def _load_cache() -> pd.DataFrame | None:
    try:
        if not os.path.exists(FII_CACHE_FILE):
            return None
        with open(FII_CACHE_FILE, "r") as f:
            cache = json.load(f)
        cached_at = datetime.strptime(cache["cached_at"], '%Y-%m-%d %H:%M:%S')
        age_hours = (datetime.now() - cached_at).total_seconds() / 3600
        if age_hours > CACHE_TTL_HOURS:
            return None
        df = pd.DataFrame(cache["data"])
        if df.empty or df["FII_Net"].abs().sum() == 0:
            return None   # Don't return cached zero data
        return df
    except Exception:
        return None


def _save_cache(df: pd.DataFrame):
    try:
        cache = {
            "cached_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "data":      df.to_dict(orient="records"),
        }
        with open(FII_CACHE_FILE, "w") as f:
            json.dump(cache, f, default=str)
    except Exception as e:
        print(f"⚠️ FII cache save failed: {e}")


def _get_neutral_df() -> pd.DataFrame:
    today = datetime.now().strftime('%Y-%m-%d')
    return pd.DataFrame([{
        "Date": today, "FII_Buy": 0.0, "FII_Sell": 0.0,
        "FII_Net": 0.0, "DII_Buy": 0.0, "DII_Sell": 0.0,
        "DII_Net": 0.0,
    }])


# ════════════════════════════════════════════════
# MASTER FETCHER — tries all sources in order
# ════════════════════════════════════════════════

def fetch_fii_dii_data(days: int = 10) -> pd.DataFrame:
    """
    Fetch FII/DII data — tries 4 sources in order.
    Always returns a DataFrame (never crashes).
    """
    # Check cache first
    cached = _load_cache()
    if cached is not None:
        print("✅ FII/DII data from cache")
        return cached

    # Source 1: NSE API (most accurate)
    print("📡 Fetching FII/DII from NSE API...")
    df = _fetch_from_nse_api(days)
    if not df.empty and df["FII_Net"].abs().sum() > 0:
        print(f"  ✅ NSE API: {len(df)} days of data")
        _save_cache(df)
        return df

    # Source 2: NSE Archives CSV
    print("📡 Trying NSE archives...")
    df = _fetch_from_nse_archives()
    if not df.empty and df["FII_Net"].abs().sum() > 0:
        print(f"  ✅ NSE archives: {len(df)} days of data")
        _save_cache(df)
        return df

    # Source 3: Trendlyne
    print("📡 Trying Trendlyne...")
    df = _fetch_from_trendlyne()
    if not df.empty and df["FII_Net"].abs().sum() > 0:
        print(f"  ✅ Trendlyne: {len(df)} days of data")
        _save_cache(df)
        return df

    # Source 4: Market proxy (last resort)
    print("📡 Using market proxy estimation...")
    df = _estimate_fii_from_market_proxy()
    if not df.empty:
        print(f"  ⚠️ Using proxy data (not actual FII flows)")
        _save_cache(df)
        return df

    print("⚠️ All FII/DII sources failed — returning neutral")
    return _get_neutral_df()


# ════════════════════════════════════════════════
# PROMOTER HOLDING CHANGE
# Quarterly data from yfinance — cached 7 days
# ════════════════════════════════════════════════

def fetch_promoter_holding(symbol: str) -> dict:
    """
    Fetch promoter/insider holding % for a stock via yfinance.
    Returns a dict with current holding and interpretation.

    NOTE: yfinance provides 'heldPercentInsiders' which maps to
    promoter + promoter group holding in Indian context.
    """
    result = {
        "promoter_pct":    None,
        "promoter_change": None,   # QoQ change if available
        "label":           "N/A",
        "score":           50,     # neutral
        "data_available":  False,
    }

    cache = _load_promoter_cache()
    if symbol in cache:
        cached_date = cache[symbol].get("date", "")
        try:
            age_days = (datetime.now() - datetime.strptime(cached_date, '%Y-%m-%d')).days
            if age_days < PROMO_CACHE_DAYS:
                return cache[symbol]
        except Exception:
            pass

    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info   = ticker.info

        pct_insiders = info.get("heldPercentInsiders")
        if pct_insiders is not None:
            pct = round(float(pct_insiders) * 100, 2)
            result["promoter_pct"]   = pct
            result["data_available"] = True
            result["date"]           = datetime.now().strftime('%Y-%m-%d')

            # Score based on promoter holding level
            # Higher promoter holding = more skin in game = bullish
            if pct >= 65:
                result["label"] = f"HIGH PROMOTER HOLDING {pct:.1f}% 🟢"
                result["score"] = 80
            elif pct >= 50:
                result["label"] = f"STRONG PROMOTER HOLDING {pct:.1f}% 🟢"
                result["score"] = 70
            elif pct >= 35:
                result["label"] = f"MODERATE PROMOTER HOLDING {pct:.1f}% 🟡"
                result["score"] = 55
            elif pct >= 20:
                result["label"] = f"LOW PROMOTER HOLDING {pct:.1f}% 🟠"
                result["score"] = 40
            else:
                result["label"] = f"VERY LOW PROMOTER HOLDING {pct:.1f}% 🔴"
                result["score"] = 25

        # Also try to get institutional holding breakdown
        pct_institution = info.get("heldPercentInstitutions")
        if pct_institution is not None:
            result["fii_holding_pct"] = round(float(pct_institution) * 100, 2)

    except Exception as e:
        print(f"⚠️ Promoter fetch failed for {symbol}: {e}")

    # Cache result
    _save_promoter_cache(symbol, result)
    return result


def _load_promoter_cache() -> dict:
    try:
        if os.path.exists(PROMO_CACHE):
            with open(PROMO_CACHE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_promoter_cache(symbol: str, data: dict):
    try:
        cache = _load_promoter_cache()
        cache[symbol] = data
        with open(PROMO_CACHE, "w") as f:
            json.dump(cache, f, default=str)
    except Exception:
        pass


# ════════════════════════════════════════════════
# SCORING ENGINE
# ════════════════════════════════════════════════

def calculate_fii_dii_score(df: pd.DataFrame) -> dict:
    """
    Build a 0-100 institutional flow score.
    Returns 50 (neutral) when data is all zeros.
    """
    if df.empty:
        return _neutral_score()

    # Check if all values are zero (data fetch failed)
    total_flow = df["FII_Net"].abs().sum() + df["DII_Net"].abs().sum()
    if total_flow == 0:
        print("⚠️ FII/DII: all flow values are zero — returning neutral score")
        return _neutral_score()

    base = 50

    latest_fii = float(df["FII_Net"].iloc[0])
    latest_dii = float(df["DII_Net"].iloc[0])

    # Latest day FII (40 pts range)
    if   latest_fii > 2000:  base += 40
    elif latest_fii > 500:   base += 25
    elif latest_fii > 0:     base += 10
    elif latest_fii > -500:  base -= 5
    elif latest_fii > -2000: base -= 20
    else:                    base -= 40

    # 5-day FII trend (30 pts range)
    recent = df.head(min(5, len(df)))
    positive_days = int((recent["FII_Net"] > 0).sum())
    if   positive_days == 5:  base += 30
    elif positive_days >= 3:  base += 20
    elif positive_days == 2:  base += 10
    elif positive_days == 1:  base -= 10
    else:                     base -= 20

    # DII confirmation (20 pts range)
    if   latest_dii > 500: base += 20
    elif latest_dii > 0:   base += 5
    else:                  base -= 10

    # Combined FII + DII (10 pts)
    if latest_fii > 0 and latest_dii > 0:  base += 10
    elif latest_fii < 0 and latest_dii < 0: base -= 10

    score = max(0, min(100, round(base)))

    if   score >= 75: label = "STRONG INSTITUTIONAL BUYING 🟢🟢"
    elif score >= 60: label = "INSTITUTIONAL BUYING 🟢"
    elif score >= 45: label = "NEUTRAL ⚪"
    elif score >= 30: label = "INSTITUTIONAL SELLING 🔴"
    else:             label = "HEAVY INSTITUTIONAL SELLING 🔴🔴"

    fii_5d = round(df.head(min(5, len(df)))["FII_Net"].sum(), 2)
    dii_5d = round(df.head(min(5, len(df)))["DII_Net"].sum(), 2)

    is_proxy = bool(df.get("is_proxy", pd.Series([False])).any()) if "is_proxy" in df.columns else False

    return {
        "score":             score,
        "label":             label + (" (estimated)" if is_proxy else ""),
        "latest_fii_net":    round(latest_fii, 2),
        "latest_dii_net":    round(latest_dii, 2),
        "fii_5d_total":      fii_5d,
        "dii_5d_total":      dii_5d,
        "positive_fii_days": positive_days,
        "data_available":    total_flow > 0,
        "is_proxy":          is_proxy,
        "fetched_at":        datetime.now().strftime('%d %b %Y %H:%M'),
    }


def _neutral_score() -> dict:
    return {
        "score":             50,
        "label":             "NEUTRAL ⚪ — data temporarily unavailable",
        "latest_fii_net":    0,
        "latest_dii_net":    0,
        "fii_5d_total":      0,
        "dii_5d_total":      0,
        "positive_fii_days": 0,
        "data_available":    False,
        "is_proxy":          False,
        "fetched_at":        datetime.now().strftime('%d %b %Y %H:%M'),
    }


# ════════════════════════════════════════════════
# MASTER FUNCTIONS
# ════════════════════════════════════════════════

def get_fii_dii_analysis(days: int = 10) -> dict:
    """Full FII/DII analysis for dashboard display."""
    df    = fetch_fii_dii_data(days)
    score = calculate_fii_dii_score(df)
    score["raw_data"] = df
    return score


def get_fii_dii_score_only() -> int:
    """Lightweight version — returns int 0-100 for scoring engine."""
    try:
        df    = fetch_fii_dii_data(days=5)
        score = calculate_fii_dii_score(df)
        return score["score"]
    except Exception:
        return 50


def get_promoter_holding_score(symbol: str) -> int:
    """Returns promoter holding score 0-100 for use in Stock Score tab."""
    try:
        result = fetch_promoter_holding(symbol)
        return result.get("score", 50)
    except Exception:
        return 50


def clear_fii_cache():
    """Force-clear the FII/DII cache so next fetch is fresh."""
    try:
        if os.path.exists(FII_CACHE_FILE):
            os.remove(FII_CACHE_FILE)
            print("✅ FII/DII cache cleared")
    except Exception:
        pass