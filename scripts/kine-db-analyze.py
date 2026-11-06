"""Read-only analysis of a k3s kine SQLite datastore (state.db).

Usage (from your PC, script is piped via stdin, nothing is stored on the Pi):
  ssh pi-local "sudo python3 - /mnt/storage/backups/<dir>/state.db" < scripts/kine-db-analyze.py
Run it against a backup copy taken with k3s stopped. Opens the database with mode=ro, never writes.
Reports size, compaction state, master leases, bytes per resource type, keys with the most
revisions and PRAGMA integrity_check (the last step takes several minutes on the USB disk).
"""
import collections
import sqlite3
import sys
import time

path = sys.argv[1]
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
t0 = time.time()


def log(*args):
    print(f"[{time.time() - t0:7.1f}s]", *args, flush=True)


def q(sql, *params):
    try:
        return con.execute(sql, params).fetchall()
    except sqlite3.DatabaseError as e:
        return f"ERROR: {e}"


ps = q("PRAGMA page_size")[0][0]
pc = q("PRAGMA page_count")[0][0]
fl = q("PRAGMA freelist_count")[0][0]
log(f"page_size={ps} page_count={pc} ({pc * ps / 1e6:.0f} MB) freelist={fl} ({fl * ps / 1e6:.0f} MB)")
log("schema:", q("SELECT type, name FROM sqlite_master"))
log("compact_rev_key:", q("SELECT id, prev_revision FROM kine WHERE name = 'compact_rev_key' ORDER BY id DESC LIMIT 3"))
log("max id:", q("SELECT MAX(id) FROM kine"))
log("masterleases:")
rows = q(
    "SELECT id, name, created, deleted, create_revision, prev_revision, lease FROM kine "
    "WHERE name >= '/registry/masterleases/' AND name < '/registry/masterleases0' ORDER BY id DESC LIMIT 12"
)
for r in rows if isinstance(rows, list) else [rows]:
    log("   ", r)

# Full scan: aggregate per resource type, track latest revision per key.
agg = collections.defaultdict(lambda: [0, 0, 0])  # rows, bytes, deleted rows
revs = collections.Counter()
latest = {}  # name -> (id, deleted, bytes)
scanned = 0
try:
    for rid, name, vlen, ovlen, deleted in con.execute(
        "SELECT id, name, length(value), length(old_value), deleted FROM kine"
    ):
        scanned += 1
        parts = name.split("/")
        key = "/".join(parts[:3]) if name.startswith("/registry/") else name[:40]
        size = (vlen or 0) + (ovlen or 0)
        a = agg[key]
        a[0] += 1
        a[1] += size
        a[2] += 1 if deleted else 0
        revs[name] += 1
        prev = latest.get(name)
        if prev is None or rid > prev[0]:
            latest[name] = (rid, deleted, vlen or 0)
    log(f"full scan ok, rows={scanned}")
except sqlite3.DatabaseError as e:
    log(f"full scan FAILED after {scanned} rows: {e}")

live = {n: v for n, v in latest.items() if not v[1]}
log(f"distinct keys={len(latest)} live keys={len(live)} live value bytes={sum(v[2] for v in live.values()) / 1e6:.1f} MB")
live_by_type = collections.Counter()
for n in live:
    parts = n.split("/")
    live_by_type["/".join(parts[:3]) if n.startswith("/registry/") else n[:40]] += 1

log("top resource types by stored bytes (rows, MB, deleted rows, live keys):")
for key, (cnt, size, dele) in sorted(agg.items(), key=lambda kv: -kv[1][1])[:25]:
    log(f"   {key:<55} rows={cnt:>8} MB={size / 1e6:>8.1f} deleted={dele:>7} live={live_by_type[key]:>5}")

log("keys with most revisions:")
for name, cnt in revs.most_common(15):
    log(f"   {cnt:>8}  {name}")

log("integrity_check (max 40 errors), this takes a while ...")
res = q("PRAGMA integrity_check(40)")
for r in res if isinstance(res, list) else [res]:
    log("   ", r)
log("done")
