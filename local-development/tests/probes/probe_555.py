"""#555 probe (never merged): repeat test_t303_11's steps N times; on a timeout, ask the stuck child for its Python
stack (faulthandler on SIGABRT) before killing it, so the failure names where the process was."""
import os, signal, subprocess, sys, tempfile, time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "charts/group-sync-dashboard/scripts/recovery_mode.py"
n, fails, slow = int(sys.argv[1]), 0, 0
for i in range(n):
    with tempfile.TemporaryDirectory() as tmp:
        # As the test's _env: no inherited GSD_ variable, the same four, plus faulthandler for the dump.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GSD_")}
        env.update(TMPDIR=tmp, GSD_RECOVERY_MODE="true", GSD_RECOVERY_MODE_TTL="1h", POD_NAME="gsd-recovery-test",
                   GSD_DB_PATH=f"{tmp}/data/gsd.db", PYTHONFAULTHANDLER="1")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "--release", "rel"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        banner = [proc.stdout.readline() for _ in range(4)]
        sent = time.monotonic(); proc.send_signal(signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=5)
            took = time.monotonic() - sent
            slow += took > 0.5
        except subprocess.TimeoutExpired:
            fails += 1
            proc.send_signal(signal.SIGABRT)
            out, err = proc.communicate(timeout=10)
            print(f"--- run {i}: TIMEOUT; stdout tail:\n{out[-400:]}\n--- stderr (faulthandler):\n{err[-3000:]}", flush=True)
print(f"probe 555: python {sys.version.split()[0]} runs={n} timeouts={fails} slower_than_0.5s={slow}", flush=True)
