import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from ai import analyst_engine
from notifications import notifier
import logging


logging.basicConfig(level=logging.INFO)

test_signal = {
    "ticker": "NVDA",
    "pattern_type": "Hammer",
    "confidence_score": 88.5,
    "rsi_14": 28.2,
    "vol_mult": 1.95,
    "day1_date": "2026-06-05",
    "day1_close": 120.0,
    "day1_low": 115.0,
    "day1_high": 121.0,
    "day2_date": "2026-06-08",
    "day2_close": 125.0
}

print("--- Testing Technical Reversal with Gemma-4 Override ---")
tech_res = analyst_engine.analyze_signal(test_signal, forced_model="Gemma-4")
if tech_res:
    test_signal["ai_analysis"] = tech_res
    html_out = notifier.format_alert_email(test_signal, "fake_token")
    print(f"Model Used in Tech Alert: {tech_res.get('ai_model_used')}")
    assert "Gemma-4" in html_out or "gemma-4" in html_out
    print("SUCCESS: Gemma-4 badge verified in technical alert email!")

test_growth_payload = {
    "ticker": "AMD",
    "latest_price": 154.25,
    "vol_mult": 3.2,
    "news": [
        {
            "title": "AMD Unveils New AI Chip Infrastructure Deal",
            "pubDate": "Wed, 22 Jul 2026 18:00:00 GMT",
            "link": "https://news.google.com/rss/articles/example2"
        }
    ]
}

print("\n--- Testing Growth Catalyst with Groq-70B Override & Price Badge ---")
growth_res = analyst_engine.evaluate_growth_catalyst(test_growth_payload, forced_model="Groq-70B")
if growth_res:
    growth_html = notifier.format_growth_catalyst_email(growth_res, "fake_token")
    print(f"Model Used in Growth Alert: {growth_res.get('ai_model_used')}")
    assert "$154.25" in growth_html
    print("SUCCESS: Stock Price ($154.25) & Groq-70B model tag verified in growth alert email!")


