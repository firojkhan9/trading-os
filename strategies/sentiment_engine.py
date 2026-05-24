# ================================================
# FILE: strategies/sentiment_engine.py
# PURPOSE: Sentiment Analysis Engine
#          Analyses news headlines for each stock
#          and produces a sentiment score (0-100)
#
# MILESTONE 23 — Sentiment Analysis Engine
#
# HOW IT WORKS (3 layers):
#
#   Layer 1 — News Fetch
#     Uses GNews (Google News RSS) to fetch
#     recent headlines for each stock.
#     Free, no API key, works on Streamlit Cloud.
#     Falls back gracefully if news unavailable.
#
#   Layer 2 — Sentiment Scoring (2 methods combined)
#     a) Financial Lexicon — custom dictionary of
#        250+ bullish/bearish financial words.
#        Much more accurate than general sentiment
#        for market news. (weight: 60%)
#     b) TextBlob — general NLP sentiment library.
#        Catches tone even for unusual phrasing. (weight: 40%)
#
#   Layer 3 — Aggregation
#     Scores all headlines, averages them,
#     produces a final 0-100 Sentiment Score
#     with label: VERY BULLISH / BULLISH / NEUTRAL
#                 / BEARISH / VERY BEARISH
#
# NO API KEY NEEDED. Completely free.
# ================================================

import re
from datetime import datetime, timedelta


# ── Financial Sentiment Lexicon ───────────────────
# Custom word lists tuned for Indian stock market news.
# These are words that reliably signal positive/negative
# sentiment in financial news headlines.

BULLISH_WORDS = [
    # Price action
    'surge', 'surges', 'surging', 'rally', 'rallies', 'rallying',
    'gains', 'gain', 'gained', 'rises', 'rise', 'risen', 'rising',
    'jumps', 'jump', 'jumped', 'soars', 'soar', 'soared', 'soaring',
    'climbs', 'climb', 'climbed', 'climbing', 'spikes', 'spike', 'spiked',
    'rebounds', 'rebound', 'rebounded', 'recovers', 'recover', 'recovered',
    'breakout', 'upside', 'uptrend', 'uptick', 'lifts', 'lift',

    # Business performance
    'beats', 'beat', 'outperforms', 'outperform', 'exceeds', 'exceed',
    'profit', 'profits', 'profitable', 'profitability', 'earnings',
    'revenue', 'growth', 'growing', 'grew', 'expands', 'expansion',
    'record', 'highest', 'best', 'strong', 'stronger', 'strength',
    'robust', 'stellar', 'impressive', 'healthy', 'solid', 'excellent',
    'accelerates', 'acceleration', 'momentum', 'boom', 'booming',

    # Corporate events (positive)
    'deal', 'deals', 'wins', 'win', 'won', 'contract', 'order', 'orders',
    'upgrade', 'upgraded', 'dividend', 'dividends', 'buyback', 'bonus',
    'acquisition', 'merger', 'partnership', 'collaboration', 'investment',
    'breakthrough', 'launch', 'launches', 'approved', 'approval',
    'positive', 'optimistic', 'bullish', 'upbeat', 'confident',

    # Market flows
    'inflows', 'buying', 'demand', 'interest', 'attractive', 'opportunity',
    'accumulate', 'accumulation', 'FII buying', 'DII buying',
]

BEARISH_WORDS = [
    # Price action
    'falls', 'fall', 'fallen', 'falling', 'drops', 'drop', 'dropped',
    'declines', 'decline', 'declined', 'declining', 'slumps', 'slump',
    'slumped', 'plunges', 'plunge', 'plunged', 'tumbles', 'tumble',
    'tumbled', 'crashes', 'crash', 'crashed', 'crashing', 'sinks', 'sink',
    'sank', 'slides', 'slide', 'slid', 'retreats', 'retreat', 'retreated',
    'dips', 'dip', 'dipped', 'loses', 'lose', 'lost', 'loss', 'losses',
    'downside', 'downturn', 'downtrend', 'correction',

    # Business performance
    'misses', 'miss', 'missed', 'disappoints', 'disappoint', 'disappointing',
    'disappointing', 'below', 'weak', 'weakness', 'weaker', 'weakens',
    'shrinks', 'shrink', 'contraction', 'slowdown', 'slowing', 'slows',
    'stagnant', 'stagnation', 'flat', 'pressured', 'pressure',

    # Risk factors
    'concern', 'concerns', 'worried', 'worries', 'worry', 'risk', 'risks',
    'risky', 'uncertain', 'uncertainty', 'volatile', 'volatility',
    'headwinds', 'challenges', 'challenges', 'problems', 'issues',
    'regulatory', 'regulation', 'scrutiny', 'investigation', 'probe',
    'penalty', 'fine', 'fined', 'fraud', 'scandal', 'allegation',
    'warning', 'caution', 'cautious', 'bearish', 'pessimistic',

    # Corporate events (negative)
    'downgrade', 'downgraded', 'downgrading', 'exits', 'exit', 'sells',
    'sell-off', 'selloff', 'debt', 'default', 'bankruptcy', 'restructuring',
    'cut', 'cuts', 'layoffs', 'retrenchment', 'shutdown', 'closure',

    # Market flows
    'outflows', 'selling', 'FII selling', 'FII exit', 'recession',
    'slowdown', 'stagflation', 'inflation', 'interest rate hike',
]

# Words that intensify sentiment
INTENSIFIERS = [
    'sharply', 'significantly', 'massively', 'hugely', 'dramatically',
    'strongly', 'substantially', 'considerably', 'record', 'historic',
    'unprecedented', 'major', 'heavy', 'deep', 'steep',
]


# ── News Fetcher ──────────────────────────────────

def fetch_news_headlines(stock_name, symbol, max_results=10):
    """
    Fetch recent news headlines for a stock.
    Uses GNews (Google News RSS wrapper) — free, no API key.

    Falls back gracefully if news is unavailable.
    Returns list of headline strings.
    """
    headlines = []

    # ── Method 1: GNews library ───────────────────
    try:
        from gnews import GNews

        # Remove .NS from symbol for cleaner search
        clean_symbol = symbol.replace('.NS', '').replace('.BO', '')

        gn = GNews(
            language='en',
            country='IN',
            period='7d',          # Last 7 days
            max_results=max_results
        )

        # Search by company name + stock context
        query = f"{stock_name} NSE stock"
        results = gn.get_news(query)

        for item in results:
            title = item.get('title', '')
            if title:
                headlines.append(title)

        # If first search got few results, try with symbol
        if len(headlines) < 3:
            results2 = gn.get_news(f"{clean_symbol} India share market")
            for item in results2:
                title = item.get('title', '')
                if title and title not in headlines:
                    headlines.append(title)

    except ImportError:
        pass  # GNews not installed — use fallback
    except Exception:
        pass  # Network issue or rate limit — use fallback

    # ── Method 2: feedparser RSS fallback ─────────
    if not headlines:
        try:
            import feedparser
            clean_symbol = symbol.replace('.NS', '').replace('.BO', '')

            # Google News RSS — works on Streamlit Cloud
            url = (
                f"https://news.google.com/rss/search?"
                f"q={stock_name.replace(' ', '+')}+NSE+stock"
                f"&hl=en-IN&gl=IN&ceid=IN:en"
            )
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_results]:
                if hasattr(entry, 'title'):
                    headlines.append(entry.title)

        except Exception:
            pass

    return headlines[:max_results]


def fetch_market_headlines(max_results=15):
    """
    Fetch general Indian market news headlines.
    Used for overall market sentiment context.
    """
    headlines = []

    try:
        from gnews import GNews
        gn = GNews(language='en', country='IN', period='3d', max_results=max_results)
        results = gn.get_news("Nifty 50 BSE NSE Indian stock market")
        for item in results:
            title = item.get('title', '')
            if title:
                headlines.append(title)
    except Exception:
        pass

    if not headlines:
        try:
            import feedparser
            url = "https://news.google.com/rss/search?q=Nifty+NSE+BSE+Indian+market&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_results]:
                if hasattr(entry, 'title'):
                    headlines.append(entry.title)
        except Exception:
            pass

    return headlines


# ── Sentiment Scorer ──────────────────────────────

def lexicon_score(text):
    """
    Score a headline using the financial word lexicon.
    Returns a score from -1.0 (very bearish) to +1.0 (very bullish).

    This is the core of our sentiment engine.
    Financial-specific words are far more accurate than
    general NLP for market news.
    """
    if not text:
        return 0.0

    text_lower = text.lower()
    words      = re.findall(r'\b\w+\b', text_lower)

    bull_count = 0
    bear_count = 0

    for word in words:
        if word in BULLISH_WORDS:
            bull_count += 1
        if word in BEARISH_WORDS:
            bear_count += 1

    # Intensifier boost — words like "sharply", "massively"
    # indicate stronger sentiment regardless of direction
    intensity_boost = sum(1 for w in words if w in INTENSIFIERS) * 0.1

    net   = (bull_count - bear_count)
    total = (bull_count + bear_count)

    if total == 0:
        return 0.0

    base_score = net / total

    # Apply intensity in the direction of existing sentiment
    if base_score > 0:
        score = min(1.0, base_score + intensity_boost)
    elif base_score < 0:
        score = max(-1.0, base_score - intensity_boost)
    else:
        score = base_score

    return round(score, 4)


def textblob_score(text):
    """
    Score a headline using TextBlob NLP library.
    Returns polarity from -1.0 to +1.0.
    Catches sentiment even for unusual phrasing.
    """
    if not text:
        return 0.0
    try:
        from textblob import TextBlob
        blob = TextBlob(text)
        return round(blob.sentiment.polarity, 4)
    except ImportError:
        return 0.0
    except Exception:
        return 0.0


def score_headline(text):
    """
    Combined headline sentiment score.
    Merges financial lexicon (60%) + TextBlob (40%).

    Financial lexicon gets more weight because it's
    tuned specifically for market news vocabulary.

    Returns:
        combined_score : -1.0 to +1.0
        lex            : lexicon component
        tb             : TextBlob component
    """
    lex = lexicon_score(text)
    tb  = textblob_score(text)

    # Weighted combination
    combined = (lex * 0.60) + (tb * 0.40)
    combined = max(-1.0, min(1.0, combined))

    return round(combined, 4), round(lex, 4), round(tb, 4)


def score_to_label(score):
    """
    Convert numeric score to human-readable sentiment label.
    Thresholds tuned for financial news (which tends to be mild).
    """
    if score >= 0.40:
        return "VERY BULLISH 🟢🟢"
    elif score >= 0.15:
        return "BULLISH 🟢"
    elif score <= -0.40:
        return "VERY BEARISH 🔴🔴"
    elif score <= -0.15:
        return "BEARISH 🔴"
    else:
        return "NEUTRAL ⚪"


def score_to_0_100(score):
    """
    Convert -1 to +1 score → 0 to 100 scale.
    50 = neutral, 100 = very bullish, 0 = very bearish.
    Consistent with our other scoring dimensions.
    """
    return round((score + 1) / 2 * 100)


# ── Aggregation Engine ────────────────────────────

def analyse_headlines(headlines):
    """
    Score a list of headlines and aggregate results.
    Returns a full analysis dict.
    """
    if not headlines:
        return {
            "avg_score":      0.0,
            "label":          "NEUTRAL ⚪",
            "score_0_100":    50,
            "total_headlines":0,
            "bullish_count":  0,
            "bearish_count":  0,
            "neutral_count":  0,
            "scored_headlines":[],
        }

    scored = []
    for headline in headlines:
        combined, lex, tb = score_headline(headline)
        label = score_to_label(combined)
        scored.append({
            "Headline":   headline,
            "Score":      combined,
            "Lex Score":  lex,
            "TB Score":   tb,
            "Sentiment":  label,
        })

    # Aggregate
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


# ── Master Functions ──────────────────────────────

def get_stock_sentiment(stock_name, symbol, max_results=10):
    """
    Full sentiment analysis for one stock.
    Fetches news + scores + aggregates.

    Returns everything needed for dashboard display.
    Call this from app.py.
    """
    headlines = fetch_news_headlines(stock_name, symbol, max_results)
    analysis  = analyse_headlines(headlines)

    # Add metadata
    analysis["stock_name"] = stock_name
    analysis["symbol"]     = symbol
    analysis["fetched_at"] = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0

    return analysis


def get_market_sentiment():
    """
    Overall Indian market sentiment from broad news.
    Useful as a context indicator alongside stock-specific sentiment.
    """
    headlines = fetch_market_headlines(max_results=15)
    analysis  = analyse_headlines(headlines)
    analysis["fetched_at"] = datetime.now().strftime('%d %b %Y %H:%M')
    analysis["news_available"] = len(headlines) > 0
    return analysis


def get_sentiment_score_only(stock_name, symbol):
    """
    Lightweight version — just returns score 0-100.
    Used by scoring_engine.py to add sentiment dimension.
    Returns 50 (neutral) if no news available.
    """
    try:
        result = get_stock_sentiment(stock_name, symbol, max_results=8)
        return result["score_0_100"]
    except Exception:
        return 50  # Neutral fallback — never crash the main engine


def demo_sentiment(text_list):
    """
    Analyse a user-supplied list of headlines.
    Useful for testing or manual override in the dashboard.
    """
    return analyse_headlines(text_list)
