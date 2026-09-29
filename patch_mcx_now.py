p = '/home/ec2-user/tiger-brain-v6/backtest/tiger_session_brain.py'
s = open(p).read()

old = '''    # ---- MCX: progressive floor reduction from 22:30 ----
    if segment == "mcx" and time(22, 30) <= t < time(23, 15):
        if hunt.mcx_trades == 0:
            if t < time(22, 35):
                floor = 60.0
            else:
                floor = 55.0
            return (True, floor,
                    f"force_hunt: MCX closing, 0 MCX entries — floor {floor:.0f}")

    return (False, 0.0, "")'''

new = '''    # ---- MCX: IMMEDIATE hunt — active for the whole MCX window ----
    # Owner directive: 22:30/22:35 gating removed. The MCX Adaptive Hunt
    # engages as soon as the MCX segment is live and mcx_trades == 0, so
    # the strongest active zone breakout on GOLDM/SILVERM/CRUDEOIL can be
    # captured in whatever window is currently open.
    #
    # SAFETY (unchanged, still 100% enforced downstream):
    #   - OI >= 1000              (liquidity guard in the option chain)
    #   - Bid-Ask spread <= 1.5%  (slippage guard)
    #   - zone touch, volume delta, rocket confluence, affordability
    # ONLY the SCORE floor relaxes. If no structurally valid zone exists,
    # the hunt still takes nothing — it does not manufacture a trade.
    if segment == "mcx" and time(9, 0) <= t < time(23, 15):
        if hunt.mcx_trades == 0:
            return (True, 55.0,
                    "force_hunt: MCX live, 0 MCX entries — floor 55")

    return (False, 0.0, "")'''

assert old in s, 'MCX branch not found'
s = s.replace(old, new, 1)

# keep the docstring in sync with the new behaviour
s = s.replace(
    "      MCX: once 22:30 passes with 0 MCX entries, the floor steps down:\n"
    "           22:30→60, 22:35→55 (min). Never below 55.0.",
    "      MCX: whenever the MCX segment is live with 0 MCX entries, the floor\n"
    "           drops to 55.0 immediately. Never below 55.0.")

open(p, 'w').write(s)
print("PATCH: MCX hunt now immediate, floor 55")
