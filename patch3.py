p = '/home/ec2-user/tiger-brain-v6/backtest/run_tiger_brain_backtest.py'
s = open(p).read()
old = '''    import yfinance as yf
    to_date = datetime.now()
    # yfinance caps: 15m=30d (safe), 1m=7d'''
new = '''    import yfinance as yf

    # yfinance apna requests/urllib3 session pool download ke baad bhi
    # socket CLOSE-WAIT me pending chhod deta hai. FD leak nahi hai (count
    # flat rehta hai) lekin prod me stale socket (fd=10) dikhta hai.
    # Targeted cleanup — sirf yfinance ka apna session, koi aur socket nahi.
    # NOTE: SmartStream WebSocket (fd=4) yahan se bilkul alag hai, ye
    # cleanup use kabhi nahi chhoota.
    try:
        for attr in ("_shared_session", "_session"):
            sess = getattr(yf, attr, None)
            closer = getattr(sess, "close", None)
            if callable(closer):
                closer()
    except Exception:  # cleanup best-effort — kabhi seed fail nahi hona chahiye
        pass

    to_date = datetime.now()
    # yfinance caps: 15m=30d (safe), 1m=7d'''
assert old in s, 'anchor not found'
open(p, 'w').write(s.replace(old, new, 1))
print("PATCH 3 APPLIED: targeted yfinance session close")
