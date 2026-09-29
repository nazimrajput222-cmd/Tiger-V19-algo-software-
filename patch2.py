p = '/home/ec2-user/tiger-brain-v6/automation/tiger_live.py'
s = open(p).read()
old = '''            self.data_map, self.data_map_1m, failed = fetch_angel_data(
                self.broker, days_15m=30, days_1m=7, use_scan_universe=True)'''
new = '''            # allow_yfinance=False — LIVE path me foreign (Yahoo) data
            # substitute nahi hoga. Angel se data nahi mila to symbol
            # fail-closed hoga. Reason: yfinance 1m data ~15 min late hota
            # hai, jo live sniper scoring ko silently galat signal deta hai.
            self.data_map, self.data_map_1m, failed = fetch_angel_data(
                self.broker, days_15m=30, days_1m=7, use_scan_universe=True,
                allow_yfinance=False)'''
assert old in s, 'live caller not found'
open(p, 'w').write(s.replace(old, new, 1))
print("PATCH 2 APPLIED: live path fail-closed on yfinance")
