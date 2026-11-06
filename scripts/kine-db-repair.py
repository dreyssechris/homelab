"""Repair a WORKING COPY of a k3s kine SQLite datastore and verify it against the original.

Only run with k3s stopped. See docs/troubleshooting.md ("k3s datastore bloated or corrupted").

Usage (from your PC, script is piped via stdin, nothing is stored on the Pi):
  ssh pi-local "sudo python3 - <work>/state.db <backup>/state.db [extra keys to drop ...]" \
      < scripts/kine-db-repair.py
  Example extra key: /registry/masterleases/192.168.0.168 (master lease of an old node IP)

Steps (all on the working copy, the original is opened read-only):
  1. REINDEX (rebuilds all indexes; fixes "database disk image is malformed" index damage)
  2. Compact to the current revision using kine's own compaction query
  3. Drop all (ephemeral) events and the extra keys given on the command line
  4. VACUUM
  5. Verify: integrity_check ok, autoincrement sequence and max revision unchanged,
     every remaining live key has exactly the same latest revision and value as the original
Prints RESULT: OK or RESULT: FAILED at the end. Only swap the copy in on RESULT: OK.
"""
import sqlite3
import sys
import time

work, orig = sys.argv[1], sys.argv[2]
STALE_KEYS = sys.argv[3:]
DROP_RANGES = [("/registry/events/", "/registry/events0")]
# Same statement kine runs every 5 minutes (sqlite dialect), here with target = current revision.
COMPACT_SQL = """
DELETE FROM kine AS kv WHERE kv.id IN (
    SELECT kp.prev_revision AS id FROM kine AS kp
     WHERE kp.name != 'compact_rev_key' AND kp.prev_revision != 0 AND kp.id <= ?
    UNION
    SELECT kd.id AS id FROM kine AS kd WHERE kd.deleted != 0 AND kd.id <= ?
)"""

t0 = time.time()
ok = True


def log(*args):
    print(f"[{time.time() - t0:7.1f}s]", *args, flush=True)


def dropped(name):
    return name in STALE_KEYS or any(lo <= name < hi for lo, hi in DROP_RANGES)


def latest_live(con):
    """name -> (id, value) of the newest non-deleted revision per key (full table scan)."""
    latest = {}
    for rid, name, deleted, value in con.execute("SELECT id, name, deleted, value FROM kine"):
        prev = latest.get(name)
        if prev is None or rid > prev[0]:
            latest[name] = (rid, deleted, value)
    return {n: (v[0], v[2]) for n, v in latest.items() if not v[1]}


con = sqlite3.connect(work, isolation_level=None)
con.execute("PRAGMA busy_timeout=30000")
seq_before = con.execute("SELECT seq FROM sqlite_sequence WHERE name = 'kine'").fetchone()[0]
max_before = con.execute("SELECT MAX(id) FROM kine").fetchone()[0]
rows_before = con.execute("SELECT COUNT(*) FROM kine").fetchone()[0]
log(f"before: rows={rows_before} max_id={max_before} seq={seq_before}")
max_row = con.execute("SELECT name, deleted FROM kine WHERE id = ?", (max_before,)).fetchone()
log(f"row with max id: {max_row}")

log("REINDEX ...")
con.execute("REINDEX")
log("REINDEX done")

con.execute("BEGIN IMMEDIATE")
n = con.execute(COMPACT_SQL, (max_before, max_before)).rowcount
log(f"compacted rows deleted: {n}")
con.execute("UPDATE kine SET prev_revision = ? WHERE name = 'compact_rev_key'", (max_before,))
for key in STALE_KEYS:
    log(f"stale key {key}: deleted {con.execute('DELETE FROM kine WHERE name = ?', (key,)).rowcount} rows")
for lo, hi in DROP_RANGES:
    log(f"range {lo}: deleted {con.execute('DELETE FROM kine WHERE name >= ? AND name < ?', (lo, hi)).rowcount} rows")
con.execute("COMMIT")

log("VACUUM ...")
con.execute("VACUUM")
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
log("VACUUM done")

# ---- verification ----
integrity = con.execute("PRAGMA integrity_check").fetchall()
log(f"integrity_check: {integrity}")
ok &= integrity == [("ok",)]

seq_after = con.execute("SELECT seq FROM sqlite_sequence WHERE name = 'kine'").fetchone()[0]
max_after = con.execute("SELECT MAX(id) FROM kine").fetchone()[0]
rows_after = con.execute("SELECT COUNT(*) FROM kine").fetchone()[0]
compact_rev = con.execute("SELECT prev_revision FROM kine WHERE name = 'compact_rev_key'").fetchone()[0]
pages = con.execute("PRAGMA page_count").fetchone()[0] * con.execute("PRAGMA page_size").fetchone()[0]
log(f"after: rows={rows_after} max_id={max_after} seq={seq_after} compact_rev={compact_rev} size={pages / 1e6:.1f} MB")
if seq_after != seq_before:
    log("FAIL: autoincrement sequence changed")
    ok = False
if max_after != max_before:
    log("WARN: max id changed (row with max id was removed); new revisions still continue from seq")

log("comparing live keys with the original (read-only) ...")
src = sqlite3.connect(f"file:{orig}?mode=ro", uri=True)
want = {n: v for n, v in latest_live(src).items() if not dropped(n)}
got = latest_live(con)
missing = [n for n in want if n not in got]
extra = [n for n in got if n not in want]
changed = [n for n in want if n in got and got[n] != want[n]]
log(f"live keys expected={len(want)} got={len(got)} missing={len(missing)} extra={len(extra)} changed={len(changed)}")
for label, lst in (("missing", missing), ("extra", extra), ("changed", changed)):
    for n in lst[:10]:
        log(f"   {label}: {n}")
ok &= not (missing or extra or changed)
leftover = [n for n in got if n.startswith("/registry/masterleases/")]
log(f"remaining masterleases: {leftover}")
con.close()
log("RESULT: OK" if ok else "RESULT: FAILED")
