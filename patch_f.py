p = '/home/ec2-user/tiger-brain-v6/backtest/run_tiger_brain_backtest.py'
s = open(p).read()

# Move the per-bar hunt computation OUT of the symbol loop, BEFORE it.
old = '''            day_candidates = []
            for sym, df_sym in data_map.items():
                if ts not in df_sym.index:
                    continue
                idx = df_sym.index.get_loc(ts)
                if idx < 40:
                    continue
                seg = segment_of(sym)

                # --- Brain 1: Gate ---
                b1 = brain1_intraday_pass(df_sym, idx, segment=seg)'''
new = '''            # MANDATORY HUNT: compute the adaptive floor ONCE per bar,
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

            day_candidates = []
            for sym, df_sym in data_map.items():
                if ts not in df_sym.index:
                    continue
                idx = df_sym.index.get_loc(ts)
                if idx < 40:
                    continue
                seg = segment_of(sym)

                # --- Brain 1: Gate ---
                b1 = brain1_intraday_pass(df_sym, idx, segment=seg)'''
assert old in s, 'F anchor not found'
s = s.replace(old, new, 1)

# Remove the duplicate per-symbol hunt computation that is now dead.
old_dup = '''                # MANDATORY HUNT: the adaptive floor is computed HERE,
                # BEFORE the candidate scan, and threaded INTO the entry
                # gate. (Previously adjusted_score_threshold was computed
                # AFTER find_tiger_brain_entry had already rejected the
                # candidate — it was a dead variable. Now it actually
                # opens the gate.)
                _force_hunt = False
                _hunt_floor = None
                if daily_hunt is not None:
                    _ts_ist = _to_ist(ts)
                    _ts_time = _ts_ist.time() if hasattr(_ts_ist, "time") else ts.time()
                    _force_hunt, _hunt_floor, _ = should_force_hunt(
                        _ts_time, daily_hunt, seg)

                if use_sniper and data_map_1m and sym in data_map_1m:'''
new_dup = '''                if use_sniper and data_map_1m and sym in data_map_1m:'''
assert old_dup in s, 'F dup not found'
s = s.replace(old_dup, new_dup, 1)

open(p, 'w').write(s)
print("PATCH F: hunt computed once per bar, before symbol loop")
