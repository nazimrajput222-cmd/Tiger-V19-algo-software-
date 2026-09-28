"""
Tiger Brain — Dynamic daily F&O universe (WebSocket V2)
========================================================
Koi fixed index/stock list NAHI. Har din Angel One ke instrument master se:

  1. Har exchange segment (NFO, BFO, MCX) pe jin underlyings ke OPTIONS
     aaj live hain, woh sab universe mein.
  2. Har underlying ka "stream token" — jiske ticks se bars/score banta hai:
       * Index (OPTIDX)   → nearest FUTIDX (spot index ka volume 0 hota hai,
                            Brain 1 volume-velocity ke liye futures volume chahiye)
       * Stock (OPTSTK)   → NSE cash '-EQ' token (fallback: nearest FUTSTK)
       * Commodity (OPTFUT on MCX) → nearest FUTCOM
  3. Options: nearest expiry jiska DTE >= BRAIN3 MIN_DAYS_TO_EXPIRY
     (0-DTE gamma trap se bachne ke liye — locked config).

Angel SmartStream ki token capacity limited hai, poora option chain
(hazaron contracts) ek saath stream nahi ho sakta. Isliye `plan_option_tokens`
budget ke andar ATM se bahar "rings" mein bharta hai: pehle SAB underlyings
ka ATM (CE+PE), phir sab ka ATM±1, phir ±2 ... jab tak budget khatam.
Underlying chal pade to engine ATM re-center karta hai.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger("tiger_brain.universe.dynamic_fno")

OPTION_TYPES_BY_SEG = {
    "NFO": ("OPTIDX", "OPTSTK"),
    # BFO pe sirf index options (SENSEX/BANKEX). BSE stock options illiquid
    # hain aur wahi stocks NFO pe already hain (same NSE cash stream token).
    "BFO": ("OPTIDX",),
    "MCX": ("OPTFUT",),
}
SESSION_OF_SEG = {"NFO": "NSE", "BFO": "NSE", "MCX": "MCX"}


@dataclass(frozen=True)
class OptionContract:
    token: str
    symbol: str
    name: str
    exchange: str          # NFO / BFO / MCX
    strike: float
    option_type: str       # CE / PE
    expiry: date
    lotsize: int
    tick_size: float


@dataclass
class Underlying:
    name: str
    kind: str              # INDEX / STOCK / COMMODITY
    session: str           # NSE / MCX (trading hours group)
    stream_exchange: str   # NSE / NFO / BFO / MCX
    stream_token: str
    stream_symbol: str
    option_exchange: str
    expiry: date
    strikes: list = field(default_factory=list)
    chain: dict = field(default_factory=dict)   # (strike, 'CE'/'PE') → OptionContract
    priority: tuple = (9, 9, "")

    def atm_strike(self, price: float) -> float | None:
        if not self.strikes or price is None or price <= 0:
            return None
        return min(self.strikes, key=lambda s: (abs(s - price), s))

    def strikes_around(self, price: float, ring: int) -> list:
        """Ring 0 → [ATM]; ring k → [ATM-k, ATM+k] (jo exist karte hain)."""
        atm = self.atm_strike(price)
        if atm is None:
            return []
        i = self.strikes.index(atm)
        if ring == 0:
            return [atm]
        out = []
        for j in (i - ring, i + ring):
            if 0 <= j < len(self.strikes):
                out.append(self.strikes[j])
        return out


def _parse_expiry(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%d%b%Y", errors="coerce").dt.date


def _to_float(series: pd.Series, scale: float = 1.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0) / scale


def _index_futures(df: pd.DataFrame, today: date) -> dict:
    """(name, seg, instr) → non-expired future rows, expiry ke order mein."""
    futs = df[df["instrumenttype"].isin(("FUTIDX", "FUTSTK", "FUTCOM"))]
    futs = futs[futs["_expiry"].notna()]
    futs = futs[futs["_expiry"] >= today].sort_values("_expiry")
    out = {}
    for key, grp in futs.groupby(["name", "exch_seg", "instrumenttype"], sort=False):
        out[key] = [r for _, r in grp.iterrows()]
    return out


def _future_on_or_after(futures: dict, key: tuple, min_expiry: date):
    """Pehla future jiski expiry >= min_expiry (MCX option ka asli underlying)."""
    for r in futures.get(key, ()):
        if r["_expiry"] >= min_expiry:
            return r
    return None


def build_daily_universe(
    master: pd.DataFrame,
    today: date | None = None,
    min_days_to_expiry: int = 1,
    segments: tuple = ("NFO", "BFO", "MCX"),
    mcx_roots: tuple | None = None,
) -> list[Underlying]:
    """Instrument master → aaj ka poora optionable universe (priority order mein)."""
    from universe.fno_universe import liquidity_tier

    today = today or datetime.now().date()
    if master is None or master.empty:
        return []
    df = master.copy()
    for col in ("token", "symbol", "name", "exch_seg", "instrumenttype", "expiry"):
        if col not in df.columns:
            raise ValueError(f"instrument master mein '{col}' column nahi hai")
        df[col] = df[col].astype(str).str.strip()
    df["_expiry"] = _parse_expiry(df["expiry"])
    df["_strike"] = _to_float(df.get("strike", pd.Series(0, index=df.index)), 100.0)
    df["_lot"] = pd.to_numeric(df.get("lotsize", 1), errors="coerce").fillna(1).astype(int)
    df["_tick"] = _to_float(df.get("tick_size", pd.Series(5, index=df.index)), 100.0)

    eq_index = df[(df["exch_seg"] == "NSE") & df["symbol"].str.endswith("-EQ")]
    eq_by_symbol = dict(zip(eq_index["symbol"], zip(eq_index["token"], eq_index["symbol"])))
    futures = _index_futures(df, today)

    universe: list[Underlying] = []
    seen_names: set = set()
    for seg in segments:
        opt_types = OPTION_TYPES_BY_SEG.get(seg)
        if not opt_types:
            continue
        opts = df[(df["exch_seg"] == seg) & (df["instrumenttype"].isin(opt_types))]
        opts = opts[opts["_expiry"].notna() & (opts["_strike"] > 0)]
        opts = opts[opts["symbol"].str[-2:].isin(("CE", "PE"))]
        if opts.empty:
            continue
        for name, grp in opts.groupby("name"):
            if name in seen_names:
                # Ek underlying ek hi baar (pehle wala segment — NFO — jeetta hai)
                continue
            if seg == "MCX" and mcx_roots and name.upper() not in mcx_roots:
                continue
            valid = grp[grp["_expiry"].map(lambda d: (d - today).days >= min_days_to_expiry)]
            if valid.empty:
                continue
            expiry = min(valid["_expiry"])
            chain_rows = valid[valid["_expiry"] == expiry]
            instr = chain_rows["instrumenttype"].iloc[0]

            if seg == "MCX":
                kind = "COMMODITY"
                # MCX options futures pe bante hain: underlying = pehla future
                # jo option expiry ke baad expire ho (front-month option ↔
                # uska apna future). Future sirf DATA ke liye — trade kabhi nahi.
                fut = _future_on_or_after(futures, (name, "MCX", "FUTCOM"), expiry)
                if fut is None:
                    continue
                stream = ("MCX", fut["token"], fut["symbol"])
            elif instr == "OPTIDX":
                kind = "INDEX"
                fut = _future_on_or_after(futures, (name, seg, "FUTIDX"), today)
                if fut is None:
                    continue
                stream = (seg, fut["token"], fut["symbol"])
            else:
                kind = "STOCK"
                eq = eq_by_symbol.get(f"{name}-EQ")
                if eq is not None:
                    stream = ("NSE", eq[0], eq[1])
                else:
                    fut = _future_on_or_after(futures, (name, seg, "FUTSTK"), today)
                    if fut is None:
                        continue
                    stream = (seg, fut["token"], fut["symbol"])

            chain = {}
            for _, r in chain_rows.iterrows():
                c = OptionContract(
                    token=r["token"], symbol=r["symbol"], name=name, exchange=seg,
                    strike=float(r["_strike"]), option_type=r["symbol"][-2:],
                    expiry=expiry, lotsize=int(r["_lot"]) or 1,
                    tick_size=float(r["_tick"]) or 0.05,
                )
                chain[(c.strike, c.option_type)] = c
            strikes = sorted({k[0] for k in chain
                              if (k[0], "CE") in chain and (k[0], "PE") in chain})
            if not strikes:
                continue
            kind_rank = {"INDEX": 0, "STOCK": 1, "COMMODITY": 2}[kind]
            seen_names.add(name)
            universe.append(Underlying(
                name=name, kind=kind, session=SESSION_OF_SEG[seg],
                stream_exchange=stream[0], stream_token=str(stream[1]),
                stream_symbol=str(stream[2]), option_exchange=seg, expiry=expiry,
                strikes=strikes, chain=chain,
                priority=(kind_rank, liquidity_tier(name), name),
            ))
    universe.sort(key=lambda u: u.priority)
    logger.info("🌐 Dynamic F&O universe: %d underlyings (%s)", len(universe),
                ", ".join(f"{k}={sum(1 for u in universe if u.kind == k)}"
                          for k in ("INDEX", "STOCK", "COMMODITY")))
    return universe


def plan_option_tokens(
    universe: list[Underlying], prices: dict, budget: int, max_rings: int = 3,
) -> dict:
    """Budget ke andar ring-by-ring option contracts chuno.

    Args:
        universe: priority-ordered underlyings
        prices: underlying name → latest price (bina price wale skip)
        budget: kitne option tokens subscribe ho sakte hain
        max_rings: ATM se kitne strikes door tak

    Returns: token → OptionContract
    """
    chosen: dict[str, OptionContract] = {}
    if budget <= 0:
        return chosen
    for ring in range(0, max_rings + 1):
        for u in universe:
            price = prices.get(u.name)
            if not price:
                continue
            batch = []
            for strike in u.strikes_around(price, ring):
                for ot in ("CE", "PE"):
                    c = u.chain.get((strike, ot))
                    if c is not None and c.token not in chosen:
                        batch.append(c)
            if len(chosen) + len(batch) > budget:
                continue   # is underlying ka ring nahi aata — chhote wale try karo
            for c in batch:
                chosen[c.token] = c
    return chosen
