p = '/home/ec2-user/tiger-brain-v6/automation/tiger_live.py'
s = open(p).read()

# ---------------------------------------------------------------------------
# BUG: the Telegram bridge read the WRONG field for premium/qty, so every
# alert printed "Premium ₹0.00 | qty 550" — the numbers came from
# t.get('entry_price') / t.get('quantity'), which the backtest stores under
# different keys. A signal showing ₹0.00 premium is meaningless and, worse,
# it looks like a tradable order when none exists.
#
# Fix: read the real fields with a safe fallback chain, and — critically —
# do NOT emit a SIGNAL/WATCH for a trade that has already exited. A closed
# historical trade is not an actionable alert.
# ---------------------------------------------------------------------------
old = '''                side = "CALL" if t.get("option_type") == "CE" else "PUT"
                is_signal = score >= signal_min
                mkt = "MCX" if seg == "commodity" else "NSE"
                msg = (f"{'🚨 TIGER SIGNAL' if is_signal else '👀 TIGER WATCH'}\\n"
                       f"{sym} {mkt} {side} {t.get('strike', '?')}\\n"
                       f"Score: {score:.1f} (signal ≥{signal_min:g}, watch ≥{watch_min:g})"
                       f"\\nPremium ₹{float(t.get('entry_price') or 0):.2f}"
                       f" | qty {t.get('quantity', '?')}")
                logger.info(msg.replace("\\n", " | "))
                if self.notifier is not None:
                    self.notifier.notify(msg)'''

new = '''                # An already-closed trade is not an actionable alert.
                # Skip it — otherwise the user gets a "🚨 SIGNAL" for a
                # position that no longer exists.
                if t.get("exit_ts") is not None:
                    continue

                # Premium/qty live under several key names depending on which
                # engine branch produced the trade. Try them in order, and
                # if we genuinely cannot find a price, say so instead of
                # printing a misleading ₹0.00.
                prem = None
                for k in ("entry_premium", "entry_price", "premium",
                          "entry_prem"):
                    v = t.get(k)
                    if v:
                        try:
                            prem = float(v)
                            break
                        except (TypeError, ValueError):
                            continue
                qty = (t.get("quantity") or t.get("qty")
                       or t.get("lots") or "?")

                side = "CALL" if t.get("option_type") == "CE" else "PUT"
                is_signal = score >= signal_min
                mkt = "MCX" if seg == "commodity" else "NSE"
                prem_txt = (f"₹{prem:.2f}" if prem is not None
                            else "n/a (premium unavailable)")
                msg = (f"{'🚨 TIGER SIGNAL' if is_signal else '👀 TIGER WATCH'}\\n"
                       f"{sym} {mkt} {side} {t.get('strike', '?')}\\n"
                       f"Score: {score:.1f} (signal ≥{signal_min:g}, watch ≥{watch_min:g})"
                       f"\\nPremium {prem_txt} | qty {qty}")
                logger.info(msg.replace("\\n", " | "))
                if self.notifier is not None:
                    self.notifier.notify(msg)'''

assert old in s, 'notify block not found'
s = s.replace(old, new, 1)
open(p, 'w').write(s)
print("FIX: premium/qty read correctly + closed trades no longer alert")
