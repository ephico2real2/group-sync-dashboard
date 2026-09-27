import sys, pathlib, re
sys.path.insert(0, sys.argv[2])
from render import render
E = pathlib.Path(sys.argv[1]); rd = lambda n: (E / n).read_text()
walk = rd("walk.out")
pick = lambda *keys: "\n".join(l for l in walk.splitlines() if l.startswith(("PASS", "FAIL")) and any(k in l for k in keys))
render(str(E / "backup-pre-upgrade-copy-success.png"), "A successful pre-upgrade copy (#301)",
       "CRC lab, application 0.37.0 in a throwaway pod, on a copy of the newest backup, with a walk-only no-op migration 21; "
       "the copy is stamped 2026-09-27T00:29:48Z. Lines are the pod's output; each block shows the lines for this picture.",
       [("python3.14 walk_epic_b.py /tmp/backup.db /tmp/work   # the #301 checks", pick("#301")),
        ("ls -l /tmp/work/301/pre-upgrade", rd("pre-ls.txt")),
        ("cat /tmp/work/301/pre-upgrade/*.sha256", rd("pre-sidecar.txt")),
        ("python3.14 -c '<the sidecar, integrity and schema check; walk/pre-verify.py does the same>'", rd("pre-verify.txt"))])
render(str(E / "backup-restore-check-success.png"), "A backup proven restorable (R1–R5)",
       "CRC lab, application 0.37.0 in a throwaway pod, on byte-verified copies (sha256 matched) of "
       f"{pathlib.Path(rd('backup-name.txt').strip()).name} and of #301's copy. The live database was never touched.",
       [("python3.14 walk_epic_b.py /tmp/backup.db /tmp/work   # R1-R4 on the backup, R5 on the pre-upgrade copy",
         pick(" R1 ", " R2 ", " R3 ", " R4 ") + "\n\n" + walk.strip().splitlines()[-1])])
