import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import database

import uuid

def test_paper_trade_editing():
    # 1. Create a test subscriber with unique email
    rand_email = f"paper_edit_{uuid.uuid4().hex[:8]}@example.com"
    sub_id, token = database.create_subscriber(rand_email)
    assert sub_id is not None

    # 2. Add an initial paper trade
    ok, msg = database.add_paper_trade(
        subscriber_id=sub_id,
        ticker="AAPL",
        shares=10.0,
        entry_price=150.00,
        account_label="Test Portfolio"
    )
    assert ok is True

    # 3. Retrieve the open trade
    trades = database.get_open_paper_trades(sub_id, account_label="Test Portfolio")
    assert len(trades) == 1
    t_id = trades[0]["id"]
    assert float(trades[0]["entry_price"]) == 150.00
    assert float(trades[0]["total_invested"]) == 1500.00

    # 4. Fetch historical price for a past date
    hist_price = database.fetch_historical_price_on_date("AAPL", "2024-01-15")
    assert hist_price is not None
    assert isinstance(hist_price, float)
    assert hist_price > 0

    # 5. Update trade with new date and auto-calculated historical price
    new_date = "2024-01-15 09:30"
    new_invested = 10.0 * hist_price
    upd_ok, upd_msg = database.update_paper_trade(
        trade_id=t_id,
        entry_date=new_date,
        entry_price=hist_price,
        shares=10.0,
        total_invested=new_invested
    )
    assert upd_ok is True

    # 6. Verify updated open trade values
    updated_trades = database.get_open_paper_trades(sub_id, account_label="Test Portfolio")
    assert len(updated_trades) == 1
    upd_trade = updated_trades[0]
    assert upd_trade["entry_date"] == new_date
    assert float(upd_trade["entry_price"]) == hist_price
    assert float(upd_trade["total_invested"]) == new_invested
