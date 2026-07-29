import unittest
import os
import sqlite3
from core import database

class TestPaperTrading(unittest.TestCase):
    
    def setUp(self):
        database.init_db()
        self.conn = database.get_db_connection()
        self.test_token = "test_paper_token_123"
        # Ensure a test subscriber exists
        with self.conn:
            self.conn.execute("""
                INSERT OR IGNORE INTO subscribers (email, management_token, paper_position_size)
                VALUES ('paper_test@example.com', ?, 500.0);
            """, (self.test_token,))

    def tearDown(self):
        with self.conn:
            self.conn.execute("DELETE FROM subscribers WHERE management_token = ?;", (self.test_token,))
            self.conn.execute("DELETE FROM sent_alerts WHERE ticker = 'TEST_PAPER_TICKER';")
        self.conn.close()

    def test_default_paper_position_size(self):
        size = database.get_subscriber_paper_position_size(self.test_token)
        self.assertEqual(size, 500.0)

    def test_update_paper_position_size(self):
        success = database.update_subscriber_paper_position_size(self.test_token, 1000.0)
        self.assertTrue(success)
        size = database.get_subscriber_paper_position_size(self.test_token)
        self.assertEqual(size, 1000.0)

    def test_heartbeat_blueprint_retrieval_and_dollar_math(self):
        # Insert mock alert
        sub_row = self.conn.execute("SELECT id FROM subscribers WHERE management_token = ?;", (self.test_token,)).fetchone()
        sub_id = sub_row["id"]
        
        with self.conn:
            self.conn.execute("""
                INSERT INTO sent_alerts (
                    subscriber_id, ticker, pattern_type, day1_date, day2_date,
                    entry_price, stop_loss, profit_target, outcome_status, return_pct
                ) VALUES (?, 'TEST_PAPER_TICKER', 'Heartbeat_Test', '2026-07-28', '2026-07-28',
                28.50, 27.07, 34.20, 'win', 0.20);
            """, (sub_id,))
            
        bp = database.get_ticker_heartbeat_blueprint("TEST_PAPER_TICKER")
        self.assertIsNotNone(bp)
        self.assertEqual(bp["entry_price"], 28.50)
        self.assertEqual(bp["profit_target"], 34.20)
        self.assertEqual(bp["stop_loss"], 27.07)
        
        # Test $500 benchmark gain calculation
        bench_size = 500.0
        dollar_gain = bp["return_pct"] * bench_size
        self.assertAlmostEqual(dollar_gain, 100.0)

if __name__ == "__main__":
    unittest.main()
