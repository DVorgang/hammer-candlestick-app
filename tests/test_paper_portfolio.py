import unittest
from core import database

class TestPaperPortfolio(unittest.TestCase):
    def setUp(self):
        # Create a mock subscriber for paper trading tests
        self.conn = database.get_db_connection()
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO subscribers (id, email, management_token) VALUES (999, 'paper_portfolio_test@example.com', 'test_token_portfolio_999');")
            self.conn.execute("DELETE FROM paper_trades WHERE subscriber_id = 999;")
            self.conn.execute("DELETE FROM paper_accounts WHERE subscriber_id = 999;")

    def tearDown(self):
        with self.conn:
            self.conn.execute("DELETE FROM paper_trades WHERE subscriber_id = 999;")
            self.conn.execute("DELETE FROM paper_accounts WHERE subscriber_id = 999;")
            self.conn.execute("DELETE FROM subscribers WHERE id = 999;")
        self.conn.close()

    def test_add_and_get_paper_trade(self):
        success, msg = database.add_paper_trade(999, "NVDA", total_invested=5000.0, entry_price=100.0)
        self.assertTrue(success)

        open_trades = database.get_open_paper_trades(999)
        self.assertEqual(len(open_trades), 1)
        self.assertEqual(open_trades[0]["ticker"], "NVDA")
        self.assertEqual(open_trades[0]["total_invested"], 5000.0)
        self.assertEqual(open_trades[0]["shares"], 50.0)

    def test_add_by_shares_quantity(self):
        success, msg = database.add_paper_trade(999, "AAPL", shares=25.0, entry_price=200.0)
        self.assertTrue(success)

        open_trades = database.get_open_paper_trades(999)
        self.assertEqual(len(open_trades), 1)
        self.assertEqual(open_trades[0]["ticker"], "AAPL")
        self.assertEqual(open_trades[0]["shares"], 25.0)
        self.assertEqual(open_trades[0]["total_invested"], 5000.0)

    def test_paper_accounts_are_separate(self):
        success_a, msg_a = database.add_paper_trade(
            999, "NVDA", total_invested=1000.0, entry_price=100.0, account_label="Account 1"
        )
        success_b, msg_b = database.add_paper_trade(
            999, "AMD", total_invested=2000.0, entry_price=100.0, account_label="Account 2"
        )
        self.assertTrue(success_a, msg_a)
        self.assertTrue(success_b, msg_b)

        account_1_trades = database.get_open_paper_trades(999, account_label="Account 1")
        account_2_trades = database.get_open_paper_trades(999, account_label="Account 2")

        self.assertEqual([t["ticker"] for t in account_1_trades], ["NVDA"])
        self.assertEqual([t["ticker"] for t in account_2_trades], ["AMD"])

    def test_get_and_add_paper_accounts(self):
        accounts = database.get_paper_accounts(999)
        self.assertEqual([a["account_label"] for a in accounts], ["Account 1", "Account 2"])

        success, msg = database.add_paper_account(999, "Swing Trades")
        self.assertTrue(success, msg)

        accounts_after = database.get_paper_accounts(999)
        self.assertEqual(
            [a["account_label"] for a in accounts_after],
            ["Account 1", "Account 2", "Swing Trades"]
        )

    def test_paper_accounts_are_limited_to_five(self):
        for label in ["Account 3", "Account 4", "Account 5"]:
            success, msg = database.add_paper_account(999, label)
            self.assertTrue(success, msg)

        success, msg = database.add_paper_account(999, "Account 6")
        self.assertFalse(success)
        self.assertIn("up to 5", msg)

        accounts = database.get_paper_accounts(999)
        self.assertEqual(len(accounts), 5)

    def test_delete_paper_account_removes_its_trades(self):
        success, msg = database.add_paper_account(999, "Delete Me")
        self.assertTrue(success, msg)
        trade_success, trade_msg = database.add_paper_trade(
            999, "TSLA", total_invested=1000.0, entry_price=100.0, account_label="Delete Me"
        )
        self.assertTrue(trade_success, trade_msg)

        delete_success, delete_msg = database.delete_paper_account(999, "Delete Me")
        self.assertTrue(delete_success, delete_msg)

        accounts = database.get_paper_accounts(999)
        self.assertNotIn("Delete Me", [a["account_label"] for a in accounts])
        self.assertEqual(database.get_open_paper_trades(999, account_label="Delete Me"), [])

    def test_close_paper_trade(self):
        database.add_paper_trade(999, "AMD", 2000.0, entry_price=100.0)
        open_trades = database.get_open_paper_trades(999)
        trade_id = open_trades[0]["id"]

        success, msg = database.close_paper_trade(trade_id, exit_price=120.0)
        self.assertTrue(success)

        open_after = database.get_open_paper_trades(999)
        self.assertEqual(len(open_after), 0)

        closed_trades = database.get_closed_paper_trades(999)
        self.assertEqual(len(closed_trades), 1)
        self.assertEqual(closed_trades[0]["ticker"], "AMD")
        self.assertEqual(closed_trades[0]["realized_pnl"], 400.0)  # (120 - 100) * 20 shares = $400 gain

    def test_delete_paper_trade(self):
        database.add_paper_trade(999, "PLTR", 1000.0, entry_price=25.0)
        open_trades = database.get_open_paper_trades(999)
        trade_id = open_trades[0]["id"]

        deleted = database.delete_paper_trade(trade_id)
        self.assertTrue(deleted)

        open_after = database.get_open_paper_trades(999)
        self.assertEqual(len(open_after), 0)

if __name__ == "__main__":
    unittest.main()
