import unittest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from engines import heartbeat_engine
from ai import analyst_engine
from notifications import notifier
from core import database


class TestHeartbeatEngine(unittest.TestCase):

    def test_calculate_normalized_adtv_trims_spikes(self):
        """
        Verifies that StockTitan Normalized ADTV trims extreme high-volume outlier spike days.
        """
        # 20 days of data: 18 days at 1,000,000 shares, 2 outlier spike days at 15,000,000 shares
        volumes = [1000000] * 18 + [15000000, 20000000]
        
        # Standard average would be 2.65M
        raw_mean = np.mean(volumes)
        self.assertGreater(raw_mean, 2000000)
        
        # StockTitan normalized ADTV trims top 10% outliers, giving ~1.0M
        norm_adtv = heartbeat_engine.calculate_normalized_adtv(volumes, trim_pct=0.10)
        self.assertLess(norm_adtv, 1500000)
        self.assertGreater(norm_adtv, 900000)

    def test_get_heartbeat_candidates(self):
        """
        Verifies that get_heartbeat_candidates returns a non-empty list of ticker symbols.
        """
        candidates = heartbeat_engine.get_heartbeat_candidates(max_candidates=150)
        self.assertIsInstance(candidates, list)
        self.assertGreater(len(candidates), 0)
        self.assertIn("RKLB", candidates)

    @patch("yfinance.Ticker")
    def test_scan_ticker_for_heartbeat_squeeze_detection(self, mock_ticker):
        """
        Verifies that scan_ticker_for_heartbeat detects a valid squeeze + QRS pulse.
        """
        # Mock 30 days of data
        dates = pd.date_range(end="2026-07-25", periods=30)
        
        # Squeeze data: 29 days of flat price $2.00, then day 30 breakout to $2.20 with 5x volume
        prices = [2.00] * 29 + [2.20]
        highs = [2.02] * 29 + [2.22]
        lows = [1.98] * 29 + [1.99]
        volumes = [200000] * 29 + [1000000]  # 5x volume pulse
        
        mock_df = pd.DataFrame({
            "Open": prices,
            "High": highs,
            "Low": lows,
            "Close": prices,
            "Volume": volumes
        }, index=dates)
        
        mock_obj = MagicMock()
        mock_obj.history.return_value = mock_df
        mock_ticker.return_value = mock_obj

        res = heartbeat_engine.scan_ticker_for_heartbeat("TEST")
        self.assertTrue(res.get("should_evaluate_ai"))
        self.assertEqual(res.get("ticker"), "TEST")
        self.assertEqual(res.get("latest_price"), 2.20)
        self.assertGreaterEqual(res.get("vol_mult"), 4.5)
        self.assertGreater(res.get("math_score"), 30.0)

    @patch("ai.analyst_engine.is_ai_enabled")
    def test_evaluate_heartbeat_catalyst_conviction_scoring(self, mock_ai_enabled):
        """
        Verifies 100-Point Conviction Score calculation in analyst_engine.
        """
        mock_ai_enabled.return_value = True
        h_payload = {
            "ticker": "RKLB",
            "vol_mult": 4.5,
            "price_change_pct": 8.5,
            "bb_width_pct": 7.2,
            "math_score": 55.0,
            "latest_price": 2.15,
            "prev_price": 1.98,
            "latest_vol": 5000000,
            "normalized_adtv": 1100000,
            "close_ratio": 0.85,
            "squeeze_max_high": 2.05,
            "above_200sma": True,
            "news_headlines": [{"title": "Rocket Lab Secures $515M Defense Award", "pubDate": "2026-07-25"}]
        }
        
        with patch("ai.analyst_engine._call_ai_with_fallback") as mock_ai:
            mock_ai.return_value = {
                "ai_catalyst_score": 38.0,
                "catalyst_type": "Contract Win",
                "headline_summary": "Rocket Lab awarded $515M SDA Defense contract.",
                "key_catalysts": ["$515M Defense contract"],
                "risks": ["Supply chain timing"],
                "plain_english_takeaway": "High-conviction breakout."
            }
            
            h_res = analyst_engine.evaluate_heartbeat_catalyst(h_payload)
            self.assertIsNotNone(h_res)
            self.assertEqual(h_res.get("conviction_score"), 93.0)  # 38 AI + 55 Math = 93.0
            self.assertEqual(h_res.get("ticker"), "RKLB")

    def test_format_heartbeat_digest_email_rendering(self):
        """
        Verifies that format_heartbeat_digest_email generates valid HTML containing public chart links and Trade Blueprint.
        """
        mock_setups = [
            {
                "ticker": "RKLB",
                "conviction_score": 94.5,
                "catalyst_type": "Contract Win",
                "headline_summary": "Rocket Lab awarded $515M SDA Defense contract.",
                "plain_english_takeaway": "High-conviction breakout.",
                "badge_tag": "🔥 MULTI-DAY MOMENTUM CONTINUATION",
                "badge_color": "#ff4757",
                "latest_price": 2.15,
                "price_change_pct": 8.5,
                "vol_mult": 4.8,
                "bb_width_pct": 7.2,
                "above_200sma": True,
                "key_catalysts": ["$515M Defense contract"]
            }
        ]
        
        html_out = notifier.format_heartbeat_digest_email(mock_setups, "test_token")
        self.assertIn("TRadar Heartbeat Volatility Expansion", html_out)
        self.assertIn("RKLB", html_out)
        self.assertIn("94.5 / 100", html_out)
        self.assertIn("TradingView Live Chart", html_out)
        self.assertIn("https://www.tradingview.com/chart/?symbol=RKLB", html_out)
        self.assertIn("Trailing Lock Tip:", html_out)


if __name__ == "__main__":
    unittest.main()
