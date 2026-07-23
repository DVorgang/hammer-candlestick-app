import json
import logging
import os
import re


DEFAULT_ANALYSIS = {
    "status": "Unavailable",
    "summary": "AI analysis was not run for this alert.",
    "caution_flags": [],
    "supporting_context": [],
    "plain_english_takeaway": "Use the math-based trading blueprint as the primary alert.",
}


def is_ai_enabled():
    if os.environ.get("AI_ANALYST_ENABLED", "true").lower() == "false":
        return False

    provider = os.environ.get("AI_PROVIDER", "groq").lower()
    if provider == "groq":
        return bool(os.environ.get("GROQ_API_KEY"))
    return bool(os.environ.get("OPENAI_API_KEY"))


def _clean_value(value):
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _signal_payload(signal):
    keys = [
        "ticker",
        "pattern_type",
        "confidence_score",
        "rsi_14",
        "vol_mult",
        "day1_date",
        "day1_open",
        "day1_high",
        "day1_low",
        "day1_close",
        "day2_date",
        "day2_close",
        "confirmed",
    ]
    return {key: _clean_value(signal.get(key)) for key in keys if key in signal}


def _extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _validate_analysis(data):
    analysis = DEFAULT_ANALYSIS.copy()
    if not isinstance(data, dict):
        return analysis

    analysis["status"] = str(data.get("status") or "Available")[:40]
    analysis["summary"] = str(data.get("summary") or analysis["summary"])[:700]
    analysis["plain_english_takeaway"] = str(data.get("plain_english_takeaway") or analysis["plain_english_takeaway"])[:700]

    for key in ("caution_flags", "supporting_context"):
        items = data.get(key) or []
        if isinstance(items, str):
            items = [items]
        analysis[key] = [str(item)[:220] for item in items[:4] if str(item).strip()]

    return analysis


# ─── AI Model Fallback Chain ───
# When a model hits rate limits (429), automatically cascade to the next one.
# Chain: Groq 70B → Groq 8B (same key, 5x higher limits) → Gemini Flash (free, if key set)

def _build_fallback_chain():
    """
    Builds an ordered list of (provider_name, base_url, api_key, model) tuples.
    Only includes providers that have API keys configured.
    """
    chain = []
    
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        primary_model = os.environ.get("AI_ANALYST_MODEL") or "llama-3.3-70b-versatile"
        chain.append(("Groq-70B", "https://api.groq.com/openai/v1", groq_key, primary_model))
        # Fallback: smaller Groq model with 5x higher rate limits (same API key)
        if primary_model != "llama-3.1-8b-instant":
            chain.append(("Groq-8B", "https://api.groq.com/openai/v1", groq_key, "llama-3.1-8b-instant"))
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        chain.append(("Gemini-Flash", "https://generativelanguage.googleapis.com/v1beta/openai/", gemini_key, "gemini-2.0-flash"))
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        chain.append(("OpenAI", None, openai_key, os.environ.get("AI_ANALYST_MODEL") or "gpt-4o-mini"))
    
    return chain


def _call_ai_with_fallback(instructions, prompt, context_label="AI"):
    """
    Calls the AI model chain with automatic 429 fallback.
    Returns the raw parsed JSON dict, or None if all models fail.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logging.warning("OpenAI package is not installed. Skipping AI analysis.")
        return None

    chain = _build_fallback_chain()
    if not chain:
        logging.warning("No AI API keys configured. Skipping AI analysis.")
        return None

    for provider_name, base_url, api_key, model in chain:
        try:
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = OpenAI(**kwargs)
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_completion_tokens=700,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = _extract_json(content)
            logging.info(f"{context_label} evaluation succeeded via {provider_name} ({model})")
            return data
            
        except Exception as exc:
            error_str = str(exc)
            is_rate_limit = "429" in error_str or "rate_limit" in error_str.lower()
            
            if is_rate_limit:
                logging.warning(f"⚡ {provider_name} ({model}) rate-limited for {context_label}. Falling back to next model...")
                continue
            else:
                logging.warning(f"{provider_name} ({model}) failed for {context_label}: {exc}")
                return None
    
    logging.warning(f"All AI models exhausted for {context_label}. No fallback available.")
    return None


def analyze_signal(signal):
    """
    Adds an optional AI analyst layer after the deterministic signal is found.
    The math engine remains the source of truth for pattern detection.
    Uses the automatic fallback chain (Groq 70B → Groq 8B → Gemini Flash).
    """
    if not is_ai_enabled():
        return None

    ticker = signal.get("ticker", "UNKNOWN")
    payload = _signal_payload(signal)

    instructions = (
        "You are an assistant inside a candlestick alert app. You do not give financial advice, "
        "price predictions, or instructions to buy or sell. The deterministic math engine has already "
        "identified the candlestick setup. Your job is to add beginner-friendly context, recent caution "
        "flags, and plain-English explanation. Return JSON only with keys: status, summary, "
        "caution_flags, supporting_context, plain_english_takeaway."
    )
    prompt = (
        f"Analyze this stock alert for {ticker}. If web search is available, check recent company news, "
        "earnings timing, and broad market/sector context. Keep it concise and understandable for a beginner. "
        "Do not say the user should buy or sell. Signal data:\n"
        f"{json.dumps(payload, indent=2)}"
    )

    data = _call_ai_with_fallback(instructions, prompt, context_label=f"Technical-{ticker}")
    if data:
        return _validate_analysis(data)
    return None


def evaluate_growth_catalyst(growth_payload):
    """
    Evaluates news headlines & volume multiplier to rate Growth Potential (1-10).
    Uses the automatic fallback chain (Groq 70B → Groq 8B → Gemini Flash).
    """
    if not is_ai_enabled():
        return None

    ticker = growth_payload.get("ticker", "UNKNOWN")
    vol_mult = growth_payload.get("vol_mult", 1.0)
    news = growth_payload.get("news", [])
    
    if not news:
        return None

    instructions = (
        "You are a Wall Street Fundamental Growth Analyst. Your job is to analyze real-time company news headlines "
        "and volume surges to determine if a stock has a high-growth catalyst (such as a major contract win, "
        "strategic partnership, earnings beat, FDA approval, or product launch). "
        "Rate the growth potential on a scale of 1.0 to 10.0. "
        "Return ONLY JSON with keys: growth_score (float 1-10), catalyst_type (string, e.g. Contract Win, Partnership, Earnings Beat, FDA Approval, General News), "
        "headline_summary (string), key_catalysts (array of strings), risks (array of strings), plain_english_takeaway (string)."
    )

    prompt = f"""
    Analyze the growth catalyst potential for ticker {ticker}:
    - Trading Volume Multiplier: {vol_mult:.2f}x (vs 20-Day Average Volume)
    - Recent Headlines:
    {json.dumps(news, indent=2)}

    Evaluate if this is a high-growth fundamental catalyst (contract, earnings, partnership, milestone) or just minor chatter.
    """

    data = _call_ai_with_fallback(instructions, prompt, context_label=f"Growth-{ticker}")
    if data:
        data["growth_score"] = float(data.get("growth_score") or 5.0)
        # Pass through original news items so the email can include article links
        data["news_articles"] = news
        data["ticker"] = ticker
        data["vol_mult"] = vol_mult
        return data
    return None

