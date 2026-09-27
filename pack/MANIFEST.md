# Tiger Brain V6 — Version Pack

**Main version (yeh chahiye):** `84724d639e30fb15eed9efe98e8285c0c7863c10`
**Location:** `../tiger-brain-v6/`
**Status:** exact match, verified byte-for-byte against git tree object.

---

## 1. MAIN — `tiger-brain-v6/`

| Field | Value |
|---|---|
| Commit | `84724d6` (full: `84724d639e30fb15eed9efe98e8285c0c7863c20`) |
| Tree | `1dd0cdbadd0efcb6b3f6f670ac17076aeaa9e831` |
| Author / Committer | `openhands <openhands@all-hands.dev>` (both, same second) |
| Created (UTC) | `2026-09-07 17:21:59` |
| Created (IST) | `2026-09-07 22:51:59` — **Monday** |
| Parent | `30eaa97` |
| Size | 4 files changed, +239 / −20 |
| Message | `FEAT: Real Angel One data + exit orders + 80% capital + session fix` |

**Files changed in this commit**
```
117 / 5    automation/tiger_live.py
 83 / 0    data/loader.py
 30 / 7    backtest/run_tiger_brain_backtest.py
  9 / 8    backtest/tiger_session_brain.py
```

**Deploy history (verified from EC2 systemd journal + git reflog)**
```
2026-09-07 22:51:59  IST   commit bana
2026-09-07 22:54:47  IST   git pull — box pe pahuncha
2026-09-07 22:55:18  IST   service restart -> LIVE  ★
2026-09-07 22:57:36  IST   replaced by own child 003a9ff
```
Ran live for **~2 min 18 sec**. Author se deploy tak: **3 min 19 sec**.

**Tags containing it:** `v19.0.0-life-locked`, `v19-locked`, `v1.0-LOCKED`
**Tags NOT containing it:** `v19.0.0`

---

## 2. SIDE PACK — `pack/versions/`

| # | Directory | Commit | Date (IST) | What it is |
|---|---|---|---|---|
| 01 | `01-github-main-8ad42c0` | `8ad42c0` | 2026-09-24 | GitHub `main` HEAD — latest **pushed** |
| 02 | `02-003a9ff-life-locked` | `003a9ff` | 2026-09-07 | tag `v19.0.0-life-locked` — 84724d6 ka direct child |
| 03 | `03-v19.0.0-0dc5d75` | `0dc5d75` | 2026-09-07 | tag `v19.0.0` FINAL freeze — 84724d6 se **pehle** wala |
| 04 | `04-v1.0-LOCKED-be1dbe1` | `be1dbe1` | 2026-09-09 | tag `v1.0-LOCKED` — 84724d6 ko contain karta hai |
| 05 | `05-LIVE-server-d9a5694` | `d9a5694` | 2026-09-25 | **ABHI LIVE CHAL RAHA HAI** — sirf EC2 pe hai, GitHub pe nahi |

Each folder carries `_VERSION.txt` with its ref and label.

---

## 3. LIVE SERVER VERSION (the important one)

This one is **NOT on GitHub**. It existed only on the EC2 box.

| Field | Value |
|---|---|
| Commit | `d9a5694e302fa7ddb4561eb521d4afd7cc692d80` |
| Message | `Fix: NoneType guard in _place_exit_orders (003a9ff crash)` |
| Author | `openhands <openhands@all-hands.dev>` |
| Authored | `2026-09-25 14:53:31 +0000` (IST 20:23:31) |
| Branch on server | `life-pure-003a9ff` |
| Repo path on EC2 | `/home/ec2-user/tiger-brain-v6` |
| Host | `3.108.53.100` — `ip-172-31-12-42.ap-south-1.compute.internal` |
| Service | `tiger-brain.service` — **active**, PID 1444731 |
| Running since | `2026-09-25 20:24:12 IST` |
| TZ | `Asia/Kolkata` (confirmed) |
| Retrieved | 2026-09-28 from `pack/history/LIVE-SERVER.bundle` (bundle verified, complete history) |

### ★ KEY FINDING — the live version is a FORK of 84724d6, not a descendant of main

`git merge-base 84724d6 d9a5694` = **84724d6 itself**.

So `84724d6` is literally the fork point. The live branch is only **4 commits**
ahead of your main version:

```
d9a5694 | 2026-09-25 14:53 | Fix: NoneType guard in _place_exit_orders (003a9ff crash)
e0fd543 | 2026-09-25 14:45 | Fix: RESCAN_INTERVAL_MINUTES in AUTOMATION dict (dead key)
df6dd33 | 2026-09-25 14:38 | 003a9ff + RESCAN 20→2 min (MCX night trading, till 23:30)
003a9ff | 2026-09-07 17:26 | FIX: Rate limit detection (AB1021) + 1s symbol gap
--------- 84724d6  (your main — the fork point) ---------
```

And in the **other** direction, the live branch is **missing 86 commits** that
exist on main — the whole WebSocket V2 rewrite, ML ensemble, SMC + Greeks engine,
rate-limit hardening V2, etc. all of that is **NOT running**.

**Meaning:** the bot is running a deliberately minimal, hand-patched recovery
line based on `84724d6` + 4 hotfixes. Your choice of `84724d6` as "main" matches
exactly what the live system is derived from.

### Why this version matters

Its commit message names a crash in the exit-order code that `84724d6` introduced
(its W5 `_place_exit_orders()`). That code **did crash in production**, was fixed
on the server on Sep 25, and the fix was never pushed to GitHub.

So the 3 hotfixes above are the *only* delta between your main and the running
system — and all three are server-only.

---

## 4. HISTORY — `pack/history/`

| Bundle | Size | Contents |
|---|---|---|
| `ALL-HISTORY.bundle` | 1.5 MB | All 9 branches from **GitHub** |
| `LIVE-SERVER.bundle` | 1.0 MB | All branches from the **EC2 box** — contains `d9a5694` (verified: complete history, sha1) |

Restorable offline, no network needed:

```bash
git clone pack/history/ALL-HISTORY.bundle    myrepo-github
git clone pack/history/LIVE-SERVER.bundle    myrepo-live
```

---

## 5. QUICK REFERENCE

| I want to… | Look at |
|---|---|
| The version you asked for / the base of the live system | `tiger-brain-v6/` (= `84724d6`) |
| The version actually trading right now | `pack/versions/05-LIVE-server-d9a5694/` |
| Latest pushed to GitHub | `pack/versions/01-github-main-8ad42c0/` |
| Full history, offline | `pack/history/*.bundle` |

**Lineage in one line:**
`84724d6` (your main, = fork point) → `003a9ff` → `df6dd33` → `e0fd543` → `d9a5694` (LIVE)

The live system = your main + 3 server-only hotfixes. It does **not** contain
the 86 commits of development that are on main and in GitHub.

