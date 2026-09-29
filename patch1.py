import re
p = '/home/ec2-user/tiger-brain-v6/backtest/run_tiger_brain_backtest.py'
s = open(p).read()

# --- 1. signature: add allow_yfinance ---
old_sig = 'def fetch_angel_data(broker, days_15m=365, days_1m=90, use_scan_universe=False):'
new_sig = ('def fetch_angel_data(broker, days_15m=365, days_1m=90, use_scan_universe=False,\n'
           '                     allow_yfinance=True):')
assert old_sig in s, 'sig not found'
s = s.replace(old_sig, new_sig, 1)

# --- 2. Angel block: retry 1m, never silently drop, fail-closed ---
old_block = '''        # PRIMARY: Angel One se real historical candles
        if broker is not None and broker.smart_api is not None:
            try:
                d15 = fetch_angel_underlying_candles(
                    broker, sym, "FIFTEEN_MINUTE", days=days_15m)
                d1 = fetch_angel_underlying_candles(
                    broker, sym, "ONE_MINUTE", days=days_1m)
                if d15 is not None and not d15.empty:
                    d15 = _normalize_cols(d15)
                    data_map[sym] = d15
                    if d1 is not None and not d1.empty:
                        d1 = _normalize_cols(d1)
                        data_map_1m[sym] = d1
                    angel_used.append(sym)
                    print(f"  {tag:30s}: 15m={len(d15):5d}  1m={len(data_map_1m.get(sym, [])):5d}  [ANGEL]")
                    continue
            except Exception as exc:
                logger.warning(f"{tag}: Angel fetch fail — yfinance fallback: {exc}")
'''
assert old_block in s, 'angel block not found'

new_block = '''        # PRIMARY: Angel One se real historical candles
        if broker is not None and broker.smart_api is not None:
            # 1m data poora sniper path ka backbone hai. Angel rate-limit
            # pe khaali df deta hai (exception nahi) — pehle RETRY, phir
            # fail. Kahin 1m chupke se drop nahi hona chahiye, warna symbol
            # 15m-only pe gir jata hai aur delta/volume scoring mar jaati hai.
            d15 = d1 = None
            last_err = ""
            for attempt in range(_ANGEL_SEED_RETRIES):
                try:
                    d15 = fetch_angel_underlying_candles(
                        broker, sym, "FIFTEEN_MINUTE", days=days_15m)
                    d1 = fetch_angel_underlying_candles(
                        broker, sym, "ONE_MINUTE", days=days_1m)
                except Exception as exc:
                    last_err = str(exc)
                    d15 = d1 = None
                have15 = d15 is not None and not d15.empty
                have1 = d1 is not None and not d1.empty
                if have15 and have1:
                    break
                # 1m khaali hai ya 15m khaali hai — retry before giving up
                logger.warning(
                    "%s: Angel seed attempt %d/%d incomplete (15m=%s 1m=%s) %s",
                    tag, attempt + 1, _ANGEL_SEED_RETRIES,
                    "ok" if have15 else "EMPTY", "ok" if have1 else "EMPTY",
                    last_err)
                if attempt < _ANGEL_SEED_RETRIES - 1:
                    time.sleep(_ANGEL_SEED_RETRY_PAUSE * (attempt + 1))
            if d15 is not None and not d15.empty:
                d15 = _normalize_cols(d15)
                data_map[sym] = d15
                if d1 is not None and not d1.empty:
                    d1 = _normalize_cols(d1)
                    data_map_1m[sym] = d1
                else:
                    # 1m nahi mila — symbol ko half-seeded mat chhodo.
                    # Downstream isko pata chalna chahiye.
                    logger.error("%s: 1m seed EMPTY — sniper scoring OFF for %s",
                                 tag, sym)
                angel_used.append(sym)
                print(f"  {tag:30s}: 15m={len(d15):5d}  "
                      f"1m={len(data_map_1m.get(sym, [])):5d}  [ANGEL]")
                continue
'''
s = s.replace(old_block, new_block, 1)

# --- 3. yfinance fallback: gate on allow_yfinance ---
old_yf = '''        # FALLBACK: yfinance (sirf agar Angel One fail hua)
        try:'''
new_yf = '''        # FALLBACK: yfinance (sirf agar Angel One fail hua AUR allow_yfinance)
        # LIVE path me allow_yfinance=False hota hai — live trading me foreign
        # (Yahoo) data silent substitute karna data-integrity violation hai.
        # Wahan fail-closed: symbol `failed` me jayega, trade nahi karega.
        if not allow_yfinance:
            logger.error("%s: Angel seed failed, yfinance BLOCKED in live "
                         "path — skipping symbol (last_err=%s)", tag, last_err)
            failed.append(sym)
            continue
        try:'''
assert old_yf in s, 'yf block not found'
s = s.replace(old_yf, new_yf, 1)

# --- 4. constants ---
anchor = 'def fetch_angel_data(broker'
consts = ('# Angel rate-limit pe 1m seed aksar khaali aata hai. 3 attempts with\n'
          '# backoff — phir fail-closed. Silent drop nahi.\n'
          '_ANGEL_SEED_RETRIES = 3\n'
          '_ANGEL_SEED_RETRY_PAUSE = 4.0\n\n\n')
idx = s.index(anchor)
s = s[:idx] + consts + s[idx:]

open(p, 'w').write(s)
print("PATCH 1 APPLIED: retry + fail-closed + yfinance gate")
