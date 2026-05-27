# ================================================
# FILE: strategies/sentiment_engine.py
# PURPOSE: Sentiment Analysis Engine
#          Analyses news headlines for each stock
#          and produces a sentiment score (0-100)
#
# MILESTONE 23 — Updated: 4 news sources added
#
# NEWS SOURCES (all free, legal, no API key needed):
#   1. Yahoo Finance news  — via yfinance (very reliable)
#   2. GNews               — Google News RSS wrapper
#   3. Economic Times RSS  — public feed, India-focused
#   4. Business Standard RSS — public feed, premium finance
#
# WHY NOT MONEYCONTROL / PULSE?
#   Those sites actively block bots. RSS feeds are the
#   legal, stable, machine-readable alternative they provide.
#   ET and BS are equally authoritative for Indian markets.
#
# HOW IT WORKS (3 layers):
#   Layer 1 — News Fetch (4 sources, merged + deduped)
#   Layer 2 — Scoring: Financial Lexicon (60%) + TextBlob (40%)
#   Layer 3 — Aggregation to 0-100 score with label
# ================================================

import re
from datetime import datetime


# ── Financial Sentiment Lexicon ───────────────────
# 250+ words tuned for Indian stock market news
BULLISH_WORDS = [
    'surge', 'surges', 'surging', 'rally', 'rallies', 'rallying',
    'gains', 'gain', 'gained', 'rises', 'rise', 'risen', 'rising',
    'jumps', 'jump', 'jumped', 'soars', 'soar', 'soared', 'soaring',
    'climbs', 'climb', 'climbed', 'climbing', 'spikes', 'spike', 'spiked',
    'rebounds', 'rebound', 'rebounded', 'recovers', 'recover', 'recovered',
    'breakout', 'upside', 'uptrend', 'uptick', 'lifts', 'lift',
    'beats', 'beat', 'outperforms', 'outperform', 'exceeds', 'exceed',
    'profit', 'profits', 'profitable', 'profitability', 'earnings',
    'revenue', 'growth', 'growing', 'grew', 'expands', 'expansion',
    'record', 'highest', 'best', 'strong', 'stronger', 'strength',
    'robust', 'stellar', 'impressive', 'healthy', 'solid', 'excellent',
    'accelerates', 'acceleration', 'momentum', 'boom', 'booming',
    'deal', 'deals', 'wins', 'win', 'won', 'contract', 'order', 'orders',
    'upgrade', 'upgraded', 'dividend', 'dividends', 'buyback', 'bonus',
    'acquisition', 'merger', 'partnership', 'collaboration', 'investment',
    'breakthrough', 'launch', 'launches', 'approved', 'approval',
    'positive', 'optimistic', 'bullish', 'upbeat', 'confident',
    'inflows', 'buying', 'demand', 'interest', 'attractive', 'opportunity',
    'accumulate', 'accumulation',
]

BEARISH_WORDS = [
    'falls', 'fall', 'fallen', 'falling', 'drops', 'drop', 'dropped',
    'declines', 'decline', 'declined', 'declining', 'slumps', 'slump',
    'slumped', 'plunges', 'plunge', 'plunged', 'tumbles', 'tumble',
    'tumbled', 'crashes', 'crash', 'crashed', 'crashing', 'sinks', 'sink',
    'sank', 'slides', 'slide', 'slid', 'retreats', 'retreat', 'retreated',
    'dips', 'dip', 'dipped', 'loses', 'lose', 'lost', 'loss', 'losses',
    'downside', 'downturn', 'downtrend', 'correction',
    'misses', 'miss', 'missed', 'disappoints', 'disappoint', 'disappointing',
    'below', 'weak', 'weakness', 'weaker', 'weakens',
    'shrinks', 'shrink', 'contraction', 'slowdown', 'slowing', 'slows',
    'stagnant', 'stagnation', 'flat', 'pressured', 'pressure',
    'concern', 'concerns', 'worried', 'worries', 'worry', 'risk', 'risks',
    'risky', 'uncertain', 'uncertainty', 'volatile', 'volatility',
    'headwinds', 'challenges', 'problems', 'issues',
    'regulatory', 'regulation', 'scrutiny', 'investigation', 'probe',
    'penalty', 'fine', 'fined', 'fraud', 'scandal', 'allegation',
    'warning', 'caution', 'cautious', 'bearish', 'pessimistic',
    'downgrade', 'downgraded', 'downgrading', 'exits', 'exit',
    'sell-off', 'selloff', 'debt', 'default', 'bankruptcy', 'restructuring',
    'cut', 'cuts', 'layoffs', 'retrenchment', 'shutdown', 'closure',
    'outflows', 'selling', 'recession', 'stagflation',
]

INTENSIFIERS = [
    'sharply', 'significantly', 'massively', 'hugely', 'dramatically',
    'strongly', 'substantially', 'considerably', 'record', 'historic',
    'unprecedented', 'major', 'heavy', 'deep', 'steep',
]


# ════════════════════════════════════════════════
# NEWS FETCHERS — 4 independent sources
# ════════════════════════════════════════════════

def fetch_via_yfinance(symbol, max_results=8):
    """
    Fetch news from Yahoo Finance using yfinance.
    Most reliable source — works on Streamlit Cloud.
    No API key needed. Financial news focused.
    """
    headlines = []
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        news   = ticker.news or []
        for item in news[:max_results]:
            title = item.get('title', '').strip()
            if title:
                headlines.append(title)
    except Exception:
        pass
    return headlines


def fetch_via_gnews(query, max_results=8):
    """
    Fetch from GNews library (Google News RSS wrapper).
    Requires: pip install gnews
    """
    headlines = []
    try:
        from gnews import GNews
        gn      = GNews(language='en', country='IN', period='7d', max_results=max_results)
        results = gn.get_news(query)
        for item in results:
            title = item.get('title', '').strip()
            if title:
                headlines.append(title)
    except Exception:
        pass
    return headlines


def fetch_via_rss(url, max_results=8):
    """
    Fetch headlines from any public RSS feed.
    Used for ET Markets and Business Standard.
    Requires: pip install feedparser
    Both ET and BS publish public RSS — completely legal.
    """
    headlines = []
    try:
        import feedparser
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_results]:
            title = getattr(entry, 'title', '').strip()
            if title:
                headlines.append(title)
    except Exception:
        pass
    return headlines


def fetch_news_headlines(stock_name, symbol, max_results=10):
    """
    Master news fetcher — combines 4 sources.

    Source priority:
      1. Yahoo Finance (yfinance) — most reliable, stock-specific
      2. GNews — Google News, broad coverage
      3. Economic Times RSS — India-focused financial news
      4. Business Standard RSS — premium Indian financial journalism

    All results merged and deduplicated by headline text.
    Returns list of headline strings (up to max_results).

    WHY NOT MONEYCONTROL/PULSE?
      They block automated access (bot detection).
      RSS feeds are the legal machine-readable alternative.
    """
    all_headlines = []
    seen          = set()

    def add_unique(new_list):
        """Add headlines, skipping near-duplicates."""
        for h in new_list:
            h_clean = h.strip()
            key     = h_clean[:50].lower()   # First 50 chars as dedup key
            if key not in seen and h_clean:
                seen.add(key)
                all_headlines.append(h_clean)

    clean_symbol = symbol.replace('.NS', '').replace('.BO', '')

    # ── Source 1: Yahoo Finance ───────────────────
    # Stock-specific news — very relevant
    add_unique(fetch_via_yfinance(symbol, max_results=8))

    # ── Source 2: GNews ───────────────────────────
    if len(all_headlines) < max_results:
        add_unique(fetch_via_gnews(f"{stock_name} NSE stock India", max_results=6))

    # ── Source 3: Economic Times RSS ─────────────
    # Public RSS: ET Markets stocks news
    # URL: economictimes.indiatimes.com markets stocks news
    if len(all_headlines) < max_results:
        et_headlines = fetch_via_rss(
            "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms",
            max_results=10
        )
        # Prefer headlines that mention this stock
        et_relevant = [h for h in et_headlines
                       if stock_name.lower() in h.lower()
                       or clean_symbol.lower() in h.lower()]
        # If no stock-specific match, add 3 general market headlines for context
        if et_relevant:
            add_unique(et_relevant)
        else:
            add_unique(et_headlines[:3])

    # ── Source 4: Business Standard RSS ──────────
    # Public RSS: BS Markets section
    if len(all_headlines) < max_results:
        bs_headlines = fetch_via_rss(
            "https://www.business-standard.com/rss/markets-106.rss",
            max_results=10
        )
        bs_relevant = [h for h in bs_headlines
                       if stock_name.lower() in h.lower()
                       or clean_symbol.lower() in h.lower()]
        if bs_relevant:
            add_unique(bs_relevant)
        else:
            add_unique(bs_headlines[:3])

    return all_headlines[:max_results]


def fetch_market_headlines(max_results=15):
    """
    Fetch general Indian market sentiment headlines.
    Used for the market-wide sentiment banner.
    Combines all 4 sources with no stock filter.
    """
    all_headlines = []
    seen          = set()

    def add_unique(new_list):
        for h in new_list:
            h_clean = h.strip()
            key     = h_clean[:50].lower()
            if key not in seen and h_clean:
                seen.add(key)
                all_headlines.append(h_clean)

    # GNews market query
    add_unique(fetch_via_gnews("Nifty 50 NSE BSE Indian stock market", max_results=8))

    # ET Markets general feed
    add_unique(fetch_via_rss(
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        max_results=8
    ))

    # Business Standard markets
    add_unique(fetch_via_rss(
        "https://www.business-standard.com/rss/markets-106.rss",
        max_results=8
    ))

    return all_headlines[:max_results]


# ════════════════════════════════════════════════
# SENTIMENT SCORER
# ════════════════════════════════════════════════

def lexicon_score(text):
    """
    Score using financial word lexicon.
    Returns -1.0 (very bearish) to +1.0 (very bullish).
    Financial-specific words = more accurate than general NLP.
    """
    if not text:
        return 0.0

    text_lower = text.lower()
    words      = re.findall(r'\b\w+\b', text_lower)

    bull_count = sum(1 for w in words if w in BULLISH_WORDS)
    bear_count = sum(1 for w in words if w in BEARISH_WORDS)
    intensity  = sum(1 for w in words if w in INTENSIFIERS) * 0.1

    total = bull_count + bear_count
    if total == 0:
        return 0.0

    base  = (bull_count - bear_count) / total
    # Apply intensity in same direction as base sentiment
    score = base + (intensity if base > 0 else -intensity if base < 0 else 0)
    return round(max(-1.0, min(1.0, score)), 4)


def textblob_score(text):
    """
    Score using TextBlob NLP library.
    Returns -1.0 to +1.0.
    Catches sentiment from unusual phrasing.
    """
    if not text:
        return 0.0
    try:
        from textblob import TextBlob
        return round(TextBlob(text).sentiment.polarity, 4)
    except Exception:
        return 0.0


def score_headline(text):
    """
    Combined score: Financial Lexicon (60%) + TextBlob (40%).
    Lexicon gets more weight — tuned for market news.
    Returns (combined, lex_score, tb_score).
    """
    lex      = lexicon_score(text)
    tb       = textblob_score(text)
    combined = round(max(-1.0, min(1.0, (lex * 0.60) + (tb * 0.40))), 4)
    return combined, round(lex, 4), round(tb, 4)


def score_to_label(score):
    """Convert numeric score to human-readable label."""
    if   score >= 0.40:  return "VERY BULLISH 🟢🟢"
    elif score >= 0.15:  return "BULLISH 🟢"
    elif score <= -0.40: return "VERY BEARISH 🔴🔴"
    elif score <= -0.15: return "BEARISH 🔴"
    else:                return "NEUTRAL ⚪"


def score_to_0_100(score):
    """Convert -1..+1 to 0..100. Neutral = 50."""
    return round((score + 1) / 2 * 100)


# ════════════════════════════════════════════════
# AGGREGATION
# ════════════════════════════════════════════════

def analyse_headlines(headlines):
    """Score a list of headlines and aggregate results."""
    if not headlines:
        return {
            "avg_score": 0.0, "label": "NEUTRAL ⚪",
            "score_0_100": 50, "total_headlines": 0,
            "bullish_count": 0, "bearish_count": 0,
            "neutral_count": 0, "scored_headlines": [],
        }

    scored = []
    for headline in headlines:
        combined, lex, tb = score_headline(headline)
        scored.append({
            "Headline":  headline,
            "Score":     combined,
            "Lex Score": lex,
            "TB Score":  tb,
            "Sentiment": score_to_label(combined),
        })

    all_scores    = [s["Score"] for s in scored]
    avg_score     = round(sum(all_scores) / len(all_scores), 4)
    bullish_count = sum(1 for s in all_scores if s >= 0.15)
    bearish_count = sum(1 for s in all_scores if s <= -0.15)
    neutral_count = len(all_scores) - bullish_count - bearish_count

    return {
        "avg_score":        avg_score,
        "label":            score_to_label(avg_score),
        "score_0_100":      score_to_0_100(avg_score),
        "total_headlines":  len(scored),
        "bullish_count":    bullish_count,
        "bearish_count":    bearish_count,
        "neutral_count":    neutral_count,
        "scored_headlines": scored,
    }


# ════════════════════════════════════════════════
# MASTER FUNCTIONS — called from app.py
# ════════════════════════════════════════════════

def get_stock_sentiment(stock_name, symbol, max_results=10):
    """
    Full sentiment analysis for one stock.
    Fetches from 4 sources, scores, aggregates.
    Call this from app.py Tab 4.
    """
    headlines = fetch_news_headlines(stock_name, symbol, max_results)
    analysis  = analyse_headlines(headlines)
    analysis["stock_name"]     = stock_name
    analysis["symbol"]         = symbol
    analysis["fetched_at"]     = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0
    return analysis


def get_market_sentiment():
    """
    Overall Indian market sentiment from broad news.
    Shows in Dashboard market regime banner.
    """
    headlines = fetch_market_headlines(max_results=15)
    analysis  = analyse_headlines(headlines)
    analysis["fetched_at"]     = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0
    return analysis


def get_sentiment_score_only(stock_name, symbol):
    """
    Lightweight — returns just the 0-100 score.
    Used by scoring_engine.py. Returns 50 (neutral) on failure.
    """
    try:
        result = get_stock_sentiment(stock_name, symbol, max_results=8)
        return result["score_0_100"]
    except Exception:
        return 50


def demo_sentiment(text_list):
    """Analyse a user-supplied list of headlines (manual tester)."""
    return analyse_headlines(text_list)
