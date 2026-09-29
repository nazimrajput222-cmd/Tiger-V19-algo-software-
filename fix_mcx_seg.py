p = '/home/ec2-user/tiger-brain-v6/universe/fno_universe.py'
s = open(p).read()

# BUG: COMMODITY_SYMBOLS predates the MCX contract rename. The live
# exchange now streams GOLDM (gold mini) and SILVERM (silver mini) — the
# old GOLDM-less names mean segment_of("GOLDM") fell through to "stock",
# so MCX symbols were scored on the NSE floor and Telegram never emitted
# an MCX alert.
old = '''COMMODITY_SYMBOLS = {
    "CRUDEOIL": "CL=F",
    "NATURALGAS": "NG=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",  # MCX Silver (US futures proxy)
}'''

new = '''# NOTE: include BOTH the legacy contract roots AND the current MCX
# exchange symbols. Angel One streams GOLDM / SILVERM (mini contracts);
# omitting them made segment_of() return "stock", which silently scored
# them against the NSE floor and suppressed every MCX alert.
COMMODITY_SYMBOLS = {
    "CRUDEOIL": "CL=F",
    "NATURALGAS": "NG=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",   # MCX Silver (US futures proxy)
    # --- current Angel One MCX stream symbols (mini contracts) ---
    "GOLDM": "GC=F",
    "SILVERM": "SI=F",
    "CRUDEOILM": "CL=F",
    "NATURALGASM": "NG=F",
}'''
assert old in s, 'COMMODITY_SYMBOLS not found'
s = s.replace(old, new, 1)
open(p, 'w').write(s)
print("FIXED: GOLDM/SILVERM/CRUDEOILM added to commodity segment")
