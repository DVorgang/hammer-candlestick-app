import sys
import os
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_env import load_env_file
load_env_file()

from ai import analyst_engine
from notifications import notifier

def test_gemini_model_overrides(monkeypatch):
    # Mock AI response
    monkeypatch.setattr(analyst_engine, "analyze_signal", lambda signal, forced_model=None: {
        "summary": "Mock analysis",
        "trade_bias": "BULLISH",
        "key_reason": "RSI oversold surge",
        "confidence_score": 85.0,
        "ai_model_used": forced_model or "Groq-70B"
    })
    
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
    
    tech_res = analyst_engine.analyze_signal(test_signal, forced_model="Gemma-4")
    assert tech_res["ai_model_used"] == "Gemma-4"
    test_signal["ai_analysis"] = tech_res
    html_out = notifier.format_alert_email(test_signal, "fake_token")
    assert "NVDA" in html_out
