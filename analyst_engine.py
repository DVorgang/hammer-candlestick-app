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


def analyze_signal(signal):
    """
    Adds an optional AI analyst layer after the deterministic signal is found.
    The math engine remains the source of truth for pattern detection.
    """
    if not is_ai_enabled():
        return None

    provider = os.environ.get("AI_PROVIDER", "groq").lower()
    model = os.environ.get("AI_ANALYST_MODEL") or ("llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini")
    use_web_search = os.environ.get("AI_ANALYST_WEB_SEARCH", "true").lower() != "false" and provider == "openai"
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

    if provider == "groq":
        return _analyze_with_groq(model, instructions, prompt)

    return _analyze_with_openai(model, instructions, prompt, use_web_search)


def _analyze_with_openai(model, instructions, prompt, use_web_search):
    try:
        from openai import OpenAI
    except ImportError:
        logging.warning("OpenAI package is not installed. Skipping AI analyst notes.")
        return None

    client = OpenAI()
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": prompt},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return _validate_analysis(_extract_json(content))
    except Exception as exc:
        logging.warning(f"OpenAI analyst call failed: {exc}")
        return None


def _analyze_with_groq(model, instructions, prompt):
    try:
        from openai import OpenAI
    except ImportError:
        logging.warning("OpenAI package is not installed. Skipping Groq analyst notes.")
        return None

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    try:
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
        return _validate_analysis(_extract_json(content))
    except Exception as exc:
        logging.warning(f"Groq analyst call failed: {exc}")
        return None
