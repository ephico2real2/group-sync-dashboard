"""#310 Part A's verdict, read from the committed evidence: evidence/<label>-podlog.txt and evidence/<label>-metrics.txt.

Usage: python analyse.py <podlog.txt> <metrics.txt> [--lifetime 600] [--poll 60] [--renewals 2]
Prints one line per check, PASS or FAIL with its numbers, and the timeline; exits 1 when any check fails.

The rule it holds the log to is gsd/selflogin.py's: renew_at = expires_at - min(2 h, expires_in / 4) (#renew_at), checked
once per poll cycle before the poll (#SelfLoginSessions.credential_for); a renewal enters the new session, then exits
the old one — `fleet-login` (new), `fleet-logout … outcome=revoked` (old), then `self-login-renewed` (#_acquire)."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta

CLUSTER = "walk-self-login"
STAMP = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z ")
FIELD = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')


def instant(line: str) -> datetime | None:
    """The `oc logs --timestamps` prefix, to the microsecond."""
    m = STAMP.match(line)
    if not m:
        return None
    return datetime.fromisoformat(m.group(1) + "." + (m.group(2) or "0")[:6].ljust(6, "0"))


def utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def event(line: str) -> tuple[str, dict] | None:
    """(event name, fields) for a product event line about the walk cluster, else None."""
    m = re.search(r" gsd\.[\w.]+ ([a-z-]+) (.*)$", line)
    if not m:
        return None
    fields = {k: v.strip('"') for k, v in FIELD.findall(m.group(2))}
    # fleet-credential-suspended names what it stopped in `clusters=<a,b,…>` and has no `cluster=` (gsd/selflogin.py#_suspend);
    # other events list clusters too (shared-api-url), so the list counts for this event alone.
    about = fields.get("cluster") == CLUSTER or (
        m.group(1) == "fleet-credential-suspended" and CLUSTER in fields.get("clusters", "").split(","))
    return (m.group(1), fields) if about else None


def analyse(log_lines: list[str], sample_lines: list[str], lifetime: int, poll: int, renewals: int) -> list[tuple[bool, str]]:
    margin = timedelta(seconds=min(7200, lifetime / 4))
    slack = timedelta(seconds=poll + 15)                   # one cycle, plus the cycle's own work
    logins, logouts, renewed, failures, polls = [], [], [], [], []
    for line in log_lines:
        at = instant(line)
        if at is None:
            continue
        if f"polled {CLUSTER}:" in line:
            polls.append(at)
            continue
        if "Traceback" in line or " ERROR " in line or " CRITICAL " in line:
            failures.append((at, line.split(" ", 4)[-1][:120]))
            continue
        ev = event(line)
        if ev is None:
            continue
        name, f = ev
        if name == "fleet-login":
            logins.append((at, utc(f["expires_at"])))
        elif name in ("fleet-logout", "fleet-logout-failed"):
            logouts.append((at, name, f.get("outcome", "?")))
        elif name == "self-login-renewed":
            renewed.append((at, utc(f["expires_at"]), utc(f["renew_at"]), f.get("reauth")))
        else:                                              # self-login-failed, cluster-unreachable, suspended, refused
            failures.append((at, f"{name} outcome={f.get('outcome', '?')}"))

    out: list[tuple[bool, str]] = []
    if not logins:
        return [(False, "no `fleet-login cluster=walk-self-login` line: the session was never acquired")]
    first_at, first_exp = logins[0]
    lifetimes = [round((exp - at.replace(microsecond=0)).total_seconds()) for at, exp in logins]
    out.append((all(abs(s - lifetime) <= 10 for s in lifetimes),
                f"every session's expires_at - its login instant is {lifetime} s (+/-10): {lifetimes}"))
    planned = [r for r in renewed if not r[3]]
    out.append((len(planned) >= renewals and len(planned) == len(renewed),
                f"scheduled renewals (no reauth): {len(planned)} (want >= {renewals}); reauth renewals: "
                f"{len(renewed) - len(planned)} (want 0)"))
    for k, (r_at, r_exp, r_renew, _) in enumerate(renewed, start=1):
        if k >= len(logins):
            out.append((False, f"renewal {k}: no fleet-login line precedes it"))
            continue
        prev_at, prev_exp = logins[k - 1]
        new_at, new_exp = logins[k]
        due = prev_exp - margin
        old_out = [lo for lo in logouts if new_at <= lo[0] <= r_at]
        out.append((due <= new_at.replace(microsecond=0) + timedelta(seconds=1) and new_at < prev_exp and new_at <= due + slack,
                    f"renewal {k}: the new login at {new_at:%H:%M:%S.%f} is at or after renew_at {due:%H:%M:%S} "
                    f"(+{(new_at - due).total_seconds():.1f} s, within one cycle) and before the old session's "
                    f"expires_at {prev_exp:%H:%M:%S} ({(prev_exp - new_at).total_seconds():.1f} s left)"))
        out.append((len(old_out) == 1 and old_out[0][1] == "fleet-logout" and old_out[0][2] == "revoked",
                    f"renewal {k}: new session entered, THEN the old one exited: fleet-login {new_at:%H:%M:%S.%f} <= "
                    f"{', '.join(f'{n} outcome={o} {a:%H:%M:%S.%f}' for a, n, o in old_out) or 'no logout'} <= "
                    f"self-login-renewed {r_at:%H:%M:%S.%f}"))
        out.append((r_exp == new_exp and r_renew == r_exp - margin,
                    f"renewal {k}: self-login-renewed says expires_at {r_exp:%H:%M:%S}, renew_at {r_renew:%H:%M:%S} "
                    f"(= expires_at - {margin.total_seconds():.0f} s)"))
        before = [p for p in polls if r_at - slack < p <= new_at]
        after = [p for p in polls if r_at <= p < r_at + slack]
        out.append((bool(before) and bool(after),
                    f"renewal {k}: polled across the boundary — last poll before {before[-1]:%H:%M:%S}, first after "
                    f"{after[0]:%H:%M:%S}" if before and after else f"renewal {k}: no poll within one cycle on "
                    f"{'both sides' if not (before or after) else ('the before side' if not before else 'the after side')}"))
    window = [p for p in polls if p >= first_at]
    gaps = [(b - a).total_seconds() for a, b in zip(window, window[1:])]
    out.append((bool(gaps) and max(gaps) <= slack.total_seconds(),
                f"`polled {CLUSTER}:` lines from the first login: {len(window)}, the longest gap {max(gaps, default=0):.1f} s "
                f"(want <= {slack.total_seconds():.0f})"))
    out.append((not failures, f"failure lines about {CLUSTER} (or ERROR/Traceback): {len(failures)}"
                + "".join(f"\n      {a:%H:%M:%S} {t}" for a, t in failures[:10])))

    # A sample counts only once it was READ after the first poll committed: capture.sh stamps a sample before reading it,
    # and until that poll /metrics serves the cluster's stored row — for walk-self-login, a row retired by an earlier
    # walk, with that walk's last outcome and instant (gsd/metrics.py: `up` is 1 only when the last poll succeeded).
    first_poll = next((p for p in polls if p >= first_at), None)
    ups, stamps = [], []
    for line in sample_lines:
        m = re.match(r"^(\S+) gsd_cluster_(up|last_poll_timestamp_seconds)\{cluster=\"" + CLUSTER + r"\"\} (\S+)$", line)
        if m and first_poll is not None and utc(m.group(1)) > first_poll:
            (ups if m.group(2) == "up" else stamps).append((utc(m.group(1)), float(m.group(3))))
    values = sorted({v for _, v in stamps})
    steps = [b - a for a, b in zip(values, values[1:])]
    out.append((bool(ups) and all(v == 1.0 for _, v in ups),
                f"gsd_cluster_up{{cluster=\"{CLUSTER}\"}} samples read after the first poll: {len(ups)}, all 1: "
                f"{all(v == 1.0 for _, v in ups) if ups else 'no samples'}"))
    out.append((len(values) >= 2 and max(steps) <= slack.total_seconds(),
                f"gsd_cluster_last_poll_timestamp_seconds{{cluster=\"{CLUSTER}\"}}: {len(values)} distinct values, "
                f"the longest step {max(steps, default=0):.0f} s (want <= {slack.total_seconds():.0f})"))

    print("timeline (UTC):")
    print(f"  login 1   {first_at:%H:%M:%S.%f}  expires_at {first_exp:%H:%M:%S}  renew_at {first_exp - margin:%H:%M:%S}")
    for k, (r_at, r_exp, r_renew, reauth) in enumerate(renewed, start=1):
        print(f"  renewal {k} {r_at:%H:%M:%S.%f}  expires_at {r_exp:%H:%M:%S}  renew_at {r_renew:%H:%M:%S}"
              + (f"  reauth={reauth}" if reauth else ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("podlog"); ap.add_argument("metrics")
    ap.add_argument("--lifetime", type=int, default=600); ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--renewals", type=int, default=2)
    a = ap.parse_args()
    with open(a.podlog) as fh:
        log_lines = [line.rstrip("\n") for line in fh if not line.startswith("#")]
    with open(a.metrics) as fh:
        sample_lines = [line.rstrip("\n") for line in fh if not line.startswith("#")]
    results = analyse(log_lines, sample_lines, a.lifetime, a.poll, a.renewals)
    for ok, text in results:
        print(("PASS " if ok else "FAIL ") + text)
    failed = sum(not ok for ok, _ in results)
    print(f"{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
