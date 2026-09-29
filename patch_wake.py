p = '/home/ec2-user/tiger-brain-v6/config/thresholds.py'
s = open(p).read()

old = '    "PRE_MARKET_WAKE_TIME": "09:00",'
new = '    "PRE_MARKET_WAKE_TIME": "08:30",'
assert old in s, 'PRE_MARKET_WAKE_TIME not found'
s = s.replace(old, new, 1)

# document why the wake is deliberately early
s = s.replace(
    '    "PRE_MARKET_WAKE_TIME": "08:30",',
    '    # Wake at 08:30, NOT 09:00. Measured seed time is ~9 min for 27\n'
    '    # symbols (Angel rate limits force 5-20s backoff per symbol), and\n'
    '    # the MCX hunt now fires immediately. 45 min of headroom means the\n'
    '    # zone engine is fully warm before 09:15 NSE / 09:00 MCX open.\n'
    '    "PRE_MARKET_WAKE_TIME": "08:30",', 1)

open(p, 'w').write(s)
print("TIMING: wake 09:00 -> 08:30")
