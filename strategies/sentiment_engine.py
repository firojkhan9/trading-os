# ================================================
# FILE: strategies/sentiment_engine.py
# PURPOSE: Sentiment Analysis Engine
#          Analyses news headlines for each stock
#          and produces a sentiment score (0-100)
#
# UPDATED: All 5 news sources kept + diagnostic reporting
#
# NEWS SOURCES (tried in order, all results merged):
#   1. Yahoo Finance (yfinance)      — most reliable
#   2. GNews                         — Google News wrapper
#   3. ET Markets RSS (requests)     — India-focused, no extra lib
#   4. ET Markets RSS (feedparser)   — backup if requests fails
#   5. Business Standard RSS         — premium Indian finance
#
# NEW: sources_status dict returned with every result.
#   Shows exactly which sources worked and which failed,
#   so the dashboard can display a helpful diagnostic.
#   e.g. "ET RSS: blocked", "gnews: not installed"
# ================================================

import re
from datetime import datetime


# ── Financial Sentiment Lexicon ───────────────────
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
# INDIVIDUAL SOURCE FETCHERS
# Each returns (headlines_list, status_string)
# status_string explains what happened — success or failure reason
# ════════════════════════════════════════════════

def fetch_via_yfinance(symbol, max_results=10):
    """
    Source 1: Yahoo Finance via yfinance.
    Handles both old dict format (item['title'])
    and new nested format (item['content'][0]['value']).
    Returns (headlines, status_message).
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        news   = ticker.news or []

        if not news:
            return [], "✅ Connected — but no news returned for this symbol"

        headlines = []
        for item in news[:max_results]:
            title = None

            # Old format: direct 'title' key
            title = item.get('title', '').strip()

            # New format: nested under 'content'
            if not title:
                content = item.get('content', {})
                if isinstance(content, dict):
                    title = content.get('title', '').strip()
                elif isinstance(content, list) and len(content) > 0:
                    first = content[0]
                    if isinstance(first, dict):
                        title = first.get('value', first.get('title', '')).strip()

            if title:
                headlines.append(title)

        if headlines:
            return headlines, f"✅ {len(headlines)} headlines fetched"
        else:
            return [], "✅ Connected — headlines found but title field was empty (yfinance format may have changed)"

    except ImportError:
        return [], "❌ yfinance not installed"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:80]}"


def fetch_via_gnews(query, max_results=8):
    """
    Source 2: GNews — Google News RSS wrapper.
    Requires: pip install gnews
    Returns (headlines, status_message).
    """
    try:
        from gnews import GNews
        gn      = GNews(language='en', country='IN', period='7d', max_results=max_results)
        results = gn.get_news(query)

        if results is None:
            return [], "⚠️ gnews returned None — may be blocked by network"

        headlines = []
        for item in results:
            title = item.get('title', '').strip()
            if title:
                headlines.append(title)

        if headlines:
            return headlines, f"✅ {len(headlines)} headlines fetched"
        else:
            return [], "⚠️ gnews connected but returned no results for this query"

    except ImportError:
        return [], "❌ gnews not installed — run: pip install gnews"
    except Exception as e:
        err = str(e)
        if "timeout" in err.lower() or "timed out" in err.lower():
            return [], "⚠️ gnews timed out — network too slow or blocked on cloud"
        elif "connection" in err.lower() or "refused" in err.lower():
            return [], "⚠️ gnews blocked — network restriction on Streamlit Cloud"
        else:
            return [], f"❌ gnews error: {err[:80]}"


def fetch_via_requests_rss(url, source_name, max_results=10):
    """
    Source 3/5: RSS via requests (no extra library needed).
    Parses <title> tags directly from XML response.
    More reliable than feedparser on restricted networks.
    Returns (headlines, status_message).
    """
    try:
        import requests
        resp = requests.get(url, timeout=8, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; TradingOS/1.0; +https://github.com)'
        })

        if resp.status_code == 403:
            return [], f"⚠️ {source_name} RSS blocked this request (403 Forbidden)"
        elif resp.status_code == 404:
            return [], f"❌ {source_name} RSS URL not found (404) — feed may have moved"
        elif resp.status_code != 200:
            return [], f"⚠️ {source_name} RSS returned HTTP {resp.status_code}"

        # Try CDATA-wrapped titles first (most RSS feeds use this)
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', resp.text)

        # Fall back to plain titles
        if not titles:
            titles = re.findall(r'<title>(.*?)</title>', resp.text)

        # First entry is always the channel/feed title — skip it
        article_titles = titles[1:] if len(titles) > 1 else titles

        # Clean HTML entities
        clean = []
        for t in article_titles[:max_results]:
            t = re.sub(r'&amp;', '&', t)
            t = re.sub(r'&lt;', '<', t)
            t = re.sub(r'&gt;', '>', t)
            t = re.sub(r'&quot;', '"', t)
            t = re.sub(r'&#\d+;', '', t)
            t = re.sub(r'<[^>]+>', '', t)
            t = t.strip()
            if t and len(t) > 10:
                clean.append(t)

        if clean:
            return clean, f"✅ {len(clean)} headlines fetched"
        else:
            return [], f"⚠️ {source_name} RSS connected but no parseable titles found"

    except ImportError:
        return [], "❌ requests not installed"
    except Exception as e:
        err = str(e)
        if "timeout" in err.lower() or "timed out" in err.lower():
            return [], f"⚠️ {source_name} RSS timed out (8s limit exceeded)"
        elif "connection" in err.lower():
            return [], f"⚠️ {source_name} RSS connection refused — likely blocked"
        else:
            return [], f"❌ {source_name} RSS error: {err[:80]}"


def fetch_via_feedparser(url, source_name, max_results=10):
    """
    Source 4: feedparser RSS parsing.
    Backup to requests-based fetcher.
    Returns (headlines, status_message).
    """
    try:
        import feedparser
        feed = feedparser.parse(url)

        # feedparser returns a bozo flag if the feed is malformed
        if feed.get('bozo') and not feed.entries:
            exc = feed.get('bozo_exception', '')
            return [], f"⚠️ {source_name} feedparser: malformed feed ({str(exc)[:60]})"

        headlines = []
        for entry in feed.entries[:max_results]:
            title = getattr(entry, 'title', '').strip()
            if title and len(title) > 10:
                headlines.append(title)

        if headlines:
            return headlines, f"✅ {len(headlines)} headlines fetched via feedparser"
        elif feed.entries:
            return [], f"⚠️ {source_name} feedparser: entries found but no titles extracted"
        else:
            return [], f"⚠️ {source_name} feedparser: feed empty or blocked"

    except ImportError:
        return [], "❌ feedparser not installed — run: pip install feedparser"
    except Exception as e:
        return [], f"❌ {source_name} feedparser error: {str(e)[:80]}"


# ════════════════════════════════════════════════
# MASTER NEWS FETCHER
# Tries all sources, merges results, reports status
# ════════════════════════════════════════════════

# RSS feed URLs
ET_STOCKS_RSS  = "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms"
ET_MARKETS_RSS = "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
BS_MARKETS_RSS = "https://www.business-standard.com/rss/markets-106.rss"


def _clean_and_deduplicate(raw_lists):
    """
    Merge multiple headline lists, removing near-duplicates.
    Returns a single deduplicated list.
    """
    seen = set()
    result = []
    for h in raw_lists:
        h = h.strip()
        key = h[:50].lower()
        if key not in seen and len(h) > 10:
            seen.add(key)
            result.append(h)
    return result


def fetch_news_headlines(stock_name, symbol, max_results=10):
    """
    Master fetcher — tries ALL 5 sources.
    Returns (headlines_list, sources_status_dict).

    sources_status_dict looks like:
    {
        "Yahoo Finance":          "✅ 8 headlines fetched",
        "GNews":                  "⚠️ gnews timed out",
        "ET RSS (requests)":      "✅ 3 headlines fetched",
        "ET RSS (feedparser)":    "❌ feedparser not installed",
        "Business Standard RSS":  "✅ 2 headlines fetched",
    }
    """
    sources_status = {}
    clean_symbol   = symbol.replace('.NS', '').replace('.BO', '')
    all_raw        = []

    # ── Source 1: Yahoo Finance ───────────────────
    yf_headlines, yf_status = fetch_via_yfinance(symbol, max_results=10)
    sources_status["Yahoo Finance"] = yf_status
    all_raw.extend(yf_headlines)

    # ── Source 2: GNews ───────────────────────────
    gnews_query    = f"{stock_name} {clean_symbol} NSE India stock"
    gn_headlines, gn_status = fetch_via_gnews(gnews_query, max_results=8)
    sources_status["GNews"] = gn_status
    # For GNews, prefer stock-specific results
    gn_relevant = [h for h in gn_headlines
                   if stock_name.lower() in h.lower()
                   or clean_symbol.lower() in h.lower()]
    all_raw.extend(gn_relevant if gn_relevant else gn_headlines[:3])

    # ── Source 3: ET Markets RSS (requests) ───────
    et_req_headlines, et_req_status = fetch_via_requests_rss(
        ET_STOCKS_RSS, "ET Markets (requests)", max_results=12
    )
    sources_status["ET RSS (requests)"] = et_req_status
    et_req_relevant = [h for h in et_req_headlines
                       if stock_name.lower() in h.lower()
                       or clean_symbol.lower() in h.lower()]
    all_raw.extend(et_req_relevant if et_req_relevant else et_req_headlines[:2])

    # ── Source 4: ET Markets RSS (feedparser) ─────
    # Only try if requests version got nothing
    if not et_req_relevant:
        et_fp_headlines, et_fp_status = fetch_via_feedparser(
            ET_STOCKS_RSS, "ET Markets (feedparser)", max_results=12
        )
        sources_status["ET RSS (feedparser)"] = et_fp_status
        et_fp_relevant = [h for h in et_fp_headlines
                          if stock_name.lower() in h.lower()
                          or clean_symbol.lower() in h.lower()]
        all_raw.extend(et_fp_relevant if et_fp_relevant else et_fp_headlines[:2])
    else:
        sources_status["ET RSS (feedparser)"] = "⏭️ Skipped — requests version succeeded"

    # ── Source 5: Business Standard RSS ──────────
    bs_headlines, bs_status = fetch_via_requests_rss(
        BS_MARKETS_RSS, "Business Standard", max_results=12
    )
    sources_status["Business Standard RSS"] = bs_status
    bs_relevant = [h for h in bs_headlines
                   if stock_name.lower() in h.lower()
                   or clean_symbol.lower() in h.lower()]
    all_raw.extend(bs_relevant if bs_relevant else bs_headlines[:2])

    # ── Merge and deduplicate ─────────────────────
    final_headlines = _clean_and_deduplicate(all_raw)[:max_results]

    return final_headlines, sources_status


def fetch_market_headlines(max_results=15):
    """
    Fetch general Indian market sentiment headlines.
    Returns (headlines, sources_status).
    """
    sources_status = {}
    all_raw        = []

    # GNews for broad market
    gn_hl, gn_st = fetch_via_gnews(
        "Nifty 50 NSE BSE Indian stock market today", max_results=8
    )
    sources_status["GNews (market)"] = gn_st
    all_raw.extend(gn_hl)

    # ET general markets feed
    et_hl, et_st = fetch_via_requests_rss(
        ET_MARKETS_RSS, "ET Markets General", max_results=10
    )
    sources_status["ET Markets RSS"] = et_st
    all_raw.extend(et_hl)

    # Business Standard
    bs_hl, bs_st = fetch_via_requests_rss(
        BS_MARKETS_RSS, "Business Standard", max_results=10
    )
    sources_status["Business Standard RSS"] = bs_st
    all_raw.extend(bs_hl)

    final = _clean_and_deduplicate(all_raw)[:max_results]
    return final, sources_status


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
    score = base + (intensity if base > 0 else -intensity if base < 0 else 0)
    return round(max(-1.0, min(1.0, score)), 4)


def textblob_score(text):
    """
    Score using TextBlob NLP.
    Returns -1.0 to +1.0. Returns 0.0 if TextBlob unavailable.
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
    Combined: Lexicon (60%) + TextBlob (40%).
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
            "avg_score":        0.0,
            "label":            "NEUTRAL ⚪",
            "score_0_100":      50,
            "total_headlines":  0,
            "bullish_count":    0,
            "bearish_count":    0,
            "neutral_count":    0,
            "scored_headlines": [],
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
    Now returns sources_status so dashboard can show diagnostics.
    """
    headlines, sources_status = fetch_news_headlines(
        stock_name, symbol, max_results
    )
    analysis = analyse_headlines(headlines)
    analysis["stock_name"]     = stock_name
    analysis["symbol"]         = symbol
    analysis["fetched_at"]     = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0
    analysis["sources_status"] = sources_status   # NEW — diagnostic info
    return analysis


def get_market_sentiment():
    """
    Overall Indian market sentiment from broad news.
    """
    headlines, sources_status = fetch_market_headlines(max_results=15)
    analysis = analyse_headlines(headlines)
    analysis["fetched_at"]     = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0
    analysis["sources_status"] = sources_status
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
