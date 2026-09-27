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

This one is **NOT on GitHub**. It exists only on the EC2 box and is therefore
**newer than every GitHub commit**.

| Field | Value |
|---|---|
| Commit | `d9a5694` — `Fix: NoneType guard in _place_exit_orders (003a9ff crash)` |
| Authored | `2026-09-25 14:53:31 +0000` (IST 20:23:31) |
| Branch on server | `life-pure-003a9ff` |
| Repo path on EC2 | `/home/ec2-user/tiger-brain-v6` |
| Host | `3.108.53.100` — `ip-172-31-12-42.ap-south-1.compute.internal` |
| Service | `tiger-brain.service` — **active**, PID 1444731 |
| Running since | `2026-09-25 20:24:12 IST` |
| TZ | `Asia/Kolkata` (confirmed) |
| Uptime of box | 4 weeks 2 days |

### To fetch it (run on EC2, as ec2-user)

```bash
git -C /home/ec2-user/tiger-brain-v6 bundle create /tmp/live.bundle --all
scp ec2-user@3.108.53.100:/tmp/live.bundle .
```

Then unpack into `pack/versions/05-LIVE-server-d9a5694/`:

```bash
mkdir -p pack/versions/05-LIVE-server-d9a5694
git clone pack/versions/05-LIVE-server-d9a5694/live.bundle _tmp_live
git -C _tmp_live archive d9a5694 | tar -x -C pack/versions/05-LIVE-server-d9a5694
rm -rf _tmp_live
```

> Note: do **not** put the bundle inside the destination folder being extracted
> into — use the path above exactly.

### Why this version matters

Its commit message is literally about a crash in the exit-order code that
`84724d6` introduced:

> `Fix: NoneType guard in _place_exit_orders (003a9ff crash)`

So `_place_exit_orders()` from 84724d6 (its W5) **did crash in production**, and
the fix was made on the server on Sep 25 and never pushed to GitHub.

---

## 4. HISTORY — `pack/history/ALL-HISTORY.bundle`

Complete history of all 9 remote branches, single file (1.5 MB), restorable
offline without network:

```bash
git clone pack/history/ALL-HISTORY.bundle myrepo
```

---

## 5. IMPORTANT WARNING

`pack/versions/01..04` are all from **GitHub**.

The version **actually trading real money** is `05-LIVE-server-d9a5694`, and it
is only on the EC2 box. If you are going to work from this pack, make sure you
are looking at the right one — GitHub `main` is **2 days older** than what the
bot is running.
