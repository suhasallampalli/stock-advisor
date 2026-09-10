from datetime import date

from advisor.models import Trade
from advisor.portfolio import fifo_realised, _merge_holdings
from advisor.models import Holding


def test_fifo_partial_and_full_match():
    trades = [
        Trade("INFY", "BUY", 10, 100.0, date(2024, 1, 1), "z"),
        Trade("INFY", "BUY", 10, 120.0, date(2024, 2, 1), "z"),
        Trade("INFY", "SELL", 15, 150.0, date(2024, 3, 1), "z"),
    ]
    lots = fifo_realised(trades)
    assert len(lots) == 2
    # first lot: 10 @100 -> 150
    assert lots[0].quantity == 10 and lots[0].pnl == 500.0
    # second lot: 5 @120 -> 150
    assert lots[1].quantity == 5 and lots[1].pnl == 150.0
    assert sum(l.pnl for l in lots) == 650.0


def test_fifo_ignores_oversell():
    trades = [
        Trade("X", "BUY", 5, 10.0, date(2024, 1, 1), "z"),
        Trade("X", "SELL", 8, 20.0, date(2024, 1, 2), "z"),
    ]
    lots = fifo_realised(trades)
    assert len(lots) == 1
    assert lots[0].quantity == 5


def test_merge_holdings_blends_cost():
    rows = [
        Holding("TCS", 10, 3000.0, 3200.0, "zerodha"),
        Holding("TCS", 10, 3400.0, 3200.0, "upstox"),
    ]
    merged = _merge_holdings(rows)
    assert len(merged) == 1
    assert merged[0].quantity == 20
    assert merged[0].avg_price == 3200.0
    assert "upstox" in merged[0].broker and "zerodha" in merged[0].broker
