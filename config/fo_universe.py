# ================================================
# FILE: config/fo_universe.py
# PURPOSE: F&O (Futures & Options) eligible stock universe
#          Used by the Intraday Engine (M38B) to restrict
#          trades to F&O stocks only — required for:
#            - Better liquidity
#            - No circuit-breaker-only stocks
#            - Ability to eventually trade via F&O margin products
#
# PRIORITY ORDER (same pattern as watchlist_manager.py):
#   1. Google Sheet (if URL set)      — best option, easy to update
#   2. fo_universe.csv at repo root   — local fallback
#   3. Built-in default list          — last resort, may go stale
#
# NSE REVIEWS THE F&O LIST QUARTERLY.
# Update via Google Sheet or fo_universe.csv — no code changes needed.
# ================================================

import pandas as pd
import os

# ── Google Sheet URL (optional) ───────────────────
# Leave empty "" to use fo_universe.csv or the built-in defaults.
# Format: single column named "Symbol" with NSE stock names
# (no .NS suffix, e.g. RELIANCE not RELIANCE.NS)
FO_UNIVERSE_SHEET_URL = ""

# ── Local CSV fallback ────────────────────────────
FO_UNIVERSE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fo_universe.csv"
)

# ── Built-in default F&O universe ─────────────────
# NOTE: This list changes every quarter as SEBI/NSE reviews
# F&O eligibility. This snapshot may go stale — always prefer
# updating via Google Sheet or fo_universe.csv instead of
# editing this list directly.
DEFAULT_FO_STOCKS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN",
    "BHARTIARTL","ITC","KOTAKBANK","LT","AXISBANK","BAJFINANCE","MARUTI",
    "ASIANPAINT","TITAN","SUNPHARMA","ULTRACEMCO","NESTLEIND","WIPRO",
    "HCLTECH","TECHM","ADANIENT","ADANIPORTS","POWERGRID","NTPC",
    "TATASTEEL","JSWSTEEL","M&M","BAJAJFINSV","INDUSINDBK","GRASIM",
    "HINDALCO","CIPLA","DRREDDY","DIVISLAB","EICHERMOT","HEROMOTOCO",
    "BAJAJ-AUTO","BRITANNIA","TATACONSUM","APOLLOHOSP","SBILIFE",
    "HDFCLIFE","ICICIPRULI","COALINDIA","ONGC","BPCL","IOC","GAIL",
    "VEDL","HINDCOPPER","NATIONALUM","SAIL","NMDC","JINDALSTEL",
    "TATAPOWER","ADANIGREEN","TATAMOTORS","ASHOKLEY","BHARATFORG",
    "MOTHERSON","BOSCHLTD","MRF","BALKRISIND","APOLLOTYRE","TVSMOTOR",
    "ESCORTS","CUMMINSIND","SIEMENS","ABB","HAVELLS","POLYCAB",
    "VOLTAS","BLUESTARCO","CROMPTON","DIXON","AMBER","WHIRLPOOL",
    "PIDILITIND","BERGEPAINT","AKZOINDIA","GODREJCP","MARICO","DABUR",
    "COLPAL","EMAMILTD","VBL","UBL","RADICO","JUBLFOOD","TRENT","DMART",
    "PAGEIND","ABFRL","GODREJPROP","DLF","OBEROIRLTY","PRESTIGE",
    "BRIGADE","PHOENIXLTD","LODHA","INDHOTEL","IRCTC","CONCOR",
    "DELHIVERY","BLUEDART","GMRAIRPORT","ADANIPOWER","TORNTPOWER",
    "NHPC","SJVN","JSWENERGY","CESC","RECLTD","PFC","IRFC","IREDA",
    "PNB","BANKBARODA","CANBK","UNIONBANK","INDIANB","IDFCFIRSTB",
    "FEDERALBNK","BANDHANBNK","AUBANK","RBLBANK","IDBI","YESBANK",
    "IOB","CENTRALBK","MAHABANK","UCOBANK","BANKINDIA",
    "SHRIRAMFIN","CHOLAFIN","MUTHOOTFIN","MANAPPURAM","M&MFIN",
    "BAJAJHFL","LICHSGFIN","PNBHOUSING","CANFINHOME","AAVAS",
    "SBICARD","POONAWALLA","IIFL","ANGELONE","CDSL","BSE",
    "MCX","CAMS","NAM-INDIA","HDFCAMC","UTIAMC","ICICIGI","GICRE",
    "NIACL","STARHEALTH","LICI","AUROPHARMA","LUPIN","ALKEM",
    "TORNTPHARM","GLENMARK","BIOCON","LAURUSLABS",
    "GRANULES","IPCALAB","SYNGENE","NATCOPHARM","ABBOTINDIA",
    "PIIND","UPL","SRF","DEEPAKNTR","AARTIIND","NAVINFLUOR",
    "TATACHEM","GNFC","CHAMBLFERT","COROMANDEL","GSFC",
    "ASTRAL","SUPREMEIND","FINEORG","ATUL","GALAXYSURF",
    "CLEAN","VINATIORGA","AMBUJACEM","ACC","SHREECEM","RAMCOCEM",
    "DALBHARAT","JKCEMENT","STARCEMENT","IEX","PVRINOX",
    "SUNTV","NAZARA","NETWORK18","TATACOMM",
    "INDIGO","NAUKRI","JUSTDIAL","POLICYBZR","PAYTM",
    "NYKAA","IRCON","RVNL","RITES","IRB","GMRINFRA",
    "HAL","BEL","BDL","MAZDOCK","GRSE","COCHINSHIP",
    "BHEL","BEML","ENGINERSIN","NBCC","NCC","HCC","KEC",
    "GPPL","GESHIP","CONCOR","ALLCARGO",
    "EXIDEIND","JKTYRE","CEATLTD","BALRAMCHIN",
    "TRIVENI","EIDPARRY","DALMIASUG","KRBL",
    "PERSISTENT","COFORGE","MPHASIS","LTTS","TATAELXSI",
    "BSOFT","KPITTECH","INTELLECT","NEWGEN","ROUTE","TANLA",
]


def load_fo_from_google_sheet():
    """Load F&O universe from Google Sheets CSV URL, if configured."""
    if not FO_UNIVERSE_SHEET_URL or not FO_UNIVERSE_SHEET_URL.strip():
        return None
    try:
        df = pd.read_csv(FO_UNIVERSE_SHEET_URL)
        if "Symbol" not in df.columns:
            return None
        print("✅ F&O universe loaded from Google Sheet")
        return df
    except Exception as e:
        print(f"⚠️ Could not load F&O universe from Google Sheet: {e}")
        return None


def load_fo_from_csv():
    """Load F&O universe from local fo_universe.csv, if it exists."""
    if not os.path.exists(FO_UNIVERSE_FILE):
        return None
    try:
        df = pd.read_csv(FO_UNIVERSE_FILE)
        if "Symbol" not in df.columns:
            return None
        print("✅ F&O universe loaded from fo_universe.csv")
        return df
    except Exception as e:
        print(f"⚠️ Could not load fo_universe.csv: {e}")
        return None


def get_fo_universe() -> set:
    """
    Return the set of F&O-eligible stock names (no .NS suffix).
    Tries Google Sheet → local CSV → built-in defaults.
    """
    df = load_fo_from_google_sheet()
    if df is None:
        df = load_fo_from_csv()

    if df is not None and "Symbol" in df.columns:
        symbols = df["Symbol"].astype(str).str.strip().str.upper().tolist()
        return set(symbols)

    print("⚠️ Using built-in default F&O universe (may be stale — update via Google Sheet or fo_universe.csv)")
    return set(DEFAULT_FO_STOCKS)


def is_fo_eligible(stock_name: str) -> bool:
    """Check if a single stock (name, no .NS) is in the F&O universe."""
    universe = get_fo_universe()
    return str(stock_name).strip().upper() in universe