# Heartbeat Blueprint Audit Fix

## What Happened

The Heartbeat email for AMTB correctly included a full trade blueprint:

- Current price / entry: $28.50
- Suggested entry zone: $27.93 to $29.64
- Stop-loss protection: $27.07
- Take-profit target: $34.20
- Reward-to-risk ratio: 4.0 to 1

However, the app only saved the entry price into the local database. It did not save the stop-loss or take-profit target from the Heartbeat blueprint.

Because of that, the System Learning & Post-Trade Outcome Matrix showed the AMTB alert with:

- Entry: $28.50
- Stop Loss: N/A
- Target: N/A
- Status: Pending Evaluation

The alert was also appearing in the Technical Reversals audit table even though it was actually a Heartbeat alert.

## Why It Happened

The Heartbeat email template calculated the trade blueprint inside the email formatter, but the Heartbeat scanner did not pass those same calculated values into `database.record_sent_alert()`.

The database row for AMTB was recorded as:

- `pattern_type`: `Heartbeat_Earnings Beat`
- `entry_price`: `28.50`
- `stop_loss`: `NULL`
- `profit_target`: `NULL`

The outcome resolver also only treated Hammer and Hanging Man alerts as stop/target trades. Heartbeat alerts were not yet included in that win/loss logic.

## What Was Fixed

The fix stores Heartbeat blueprint values when a Heartbeat digest email is sent.

For future Heartbeat alerts, the scanner now saves:

- `entry_price`
- `stop_loss`
- `profit_target`
- `vol_mult`

The outcome resolver now treats `Heartbeat_*` alerts as bullish stop/target trades:

- WIN if price hits the Heartbeat profit target
- LOSS if price hits the Heartbeat stop loss
- TIMEOUT if neither level is hit after 10 trading bars

The dashboard was also adjusted so Heartbeat alerts no longer appear inside the Technical Reversals audit table. Heartbeat now has its own outcome table inside the Heartbeat Volatility Audit tab.

## AMTB Backfill

The existing AMTB Heartbeat alert was backfilled in the local database with the blueprint values from the email:

- Entry: $28.50
- Stop Loss: $27.07
- Target: $34.20
- Status: Pending Evaluation

The outcome resolver was run after the backfill. AMTB stayed pending because it had not hit either the $34.20 target or the $27.07 stop.

## Commit

Code fix commit:

`902c0a9 fix: persist and audit Heartbeat trade blueprints`

