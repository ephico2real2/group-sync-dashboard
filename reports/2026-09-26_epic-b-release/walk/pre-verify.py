"""Check each pre-upgrade copy in a directory against its .sha256 sidecar, then its integrity and schema.

    python3.14 pre-verify.py /data/pre-upgrade        (or a walk's /tmp/work/301/pre-upgrade)
"""
import hashlib, pathlib, sqlite3, sys
for side in sorted(pathlib.Path(sys.argv[1]).glob("*.db.sha256")):
    want, name = side.read_text().split()
    db = side.with_name(name)
    print(name + ":", "OK" if hashlib.sha256(db.read_bytes()).hexdigest() == want else "FAILED")
    c = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    print("integrity_check:", c.execute("PRAGMA integrity_check").fetchone()[0])
    print("user_version:", c.execute("PRAGMA user_version").fetchone()[0])
