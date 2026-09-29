p = '/home/ec2-user/tiger-brain-v6/backtest/run_tiger_brain_backtest.py'
s = open(p).read()

# ---------------------------------------------------------------------------
# BUG 1: `should_force_hunt`'s 3rd param is named `segment`, not `seg`.
#        `seg=` raised TypeError on EVERY scan since the hunt went live.
# BUG 2: the hunt was evaluated once per bar with a hardcoded "nse" segment,
#        so MCX symbols never got the MCX floor. It must be evaluated per
#        symbol, using that symbol's own segment.
# ---------------------------------------------------------------------------
old = '''            # MANDATORY HUNT: compute the adaptive floor ONCE per bar,
            # BEFORE the symbol loop. (Previously this was inside the
            # loop AFTER find_tiger_brain_entry — so if the entry function
            # rejected, should_force_hunt never ran and the hunt never
            # fired, even though a valid marginal setup existed.)
            _force_hunt = False
            _hunt_floor = None
            if daily_hunt is not None:
                _ts_ist = _to_ist(ts)
                _ts_time = _ts_ist.time() if hasattr(_ts_ist, "time") else ts.time()
                _force_hunt, _hunt_floor, _ = should_force_hunt(
                    _ts_time, daily_hunt, seg="nse")

            day_candidates = []'''

new = '''            # MANDATORY HUNT: resolve the bar's IST time once per bar.
            # The hunt itself is evaluated PER SYMBOL further down, because
            # the adaptive floor is segment-specific (NSE vs MCX) and
            # should_force_hunt counts nse_trades / mcx_trades separately.
            # Evaluating it once with a hardcoded segment meant MCX symbols
            # were scored against the NSE floor.
            _ts_time = None
            if daily_hunt is not None:
                _ts_ist = _to_ist(ts)
                _ts_time = _ts_ist.time() if hasattr(_ts_ist, "time") else ts.time()

            day_candidates = []'''
assert old in s, 'per-bar hunt block not found'
s = s.replace(old, new, 1)

# now insert the per-symbol evaluation right after `seg` is known
old2 = '''                seg = segment_of(sym)

                # --- Brain 1: Gate ---'''
new2 = '''                seg = segment_of(sym)

                # MANDATORY HUNT (per symbol, per segment). The structural
                # gates below are untouched — only the score floor relaxes.
                _force_hunt = False
                _hunt_floor = None
                if daily_hunt is not None and _ts_time is not None:
                    _hunt_seg = "mcx" if seg == "commodity" else "nse"
                    _force_hunt, _hunt_floor, _ = should_force_hunt(
                        _ts_time, daily_hunt, _hunt_seg)

                # --- Brain 1: Gate ---'''
assert old2 in s, 'seg anchor not found'
s = s.replace(old2, new2, 1)

open(p, 'w').write(s)
print("FIXED: keyword bug + per-segment hunt evaluation")
