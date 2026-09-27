"""The fleet account's Lease: the claim every bind path takes, the durable half of the credential gate, and
the daily ping's bookkeeping (#285, SPEC_S4c §3.3).

ONE Lease per fleet account in the release namespace, `gsd-fleet-<sha256(username)[:16]>`:

  spec         the CLAIM — who may put this account's password on the wire right now
  annotations  the GATE — `refused`, ONE entry per account: the last answered failure for one password, the
               target that answered kept as evidence, never as the key (#315: a lockout is per directory
               account) — and the PING's instants

WHAT A LEASE GUARANTEES, from the documents that define it. The Kubernetes API conventions ("Concurrency
Control and Consistency"): a PUT carrying the resourceVersion just read fails with 409 when the object
changed since, and the client's duty is to "GET the resource again, apply the changes afresh, and try
submitting again". So two processes cannot both win one claim, whatever their clocks — the API server
arbitrates. What it CANNOT be is a fence: client-go's leaderelection package says so of itself ("does not
guarantee that only one client is acting as a leader"), and a holder paused past the claim's duration can
still send the password after another process took the claim over. What keeps that to one bind is the
attempt's reservation, not the claim (SPEC_S4c §3.2, B1): written before the wire against the claim's own
resourceVersion, it gates the process that took over, and a holder paused before writing it meets the 409.

FAIL CLOSED. A Lease that cannot be read or written is `FleetStateUnavailable`, and no path binds without
its claim: a missed login while the RBAC is fixed is one stale cluster; a bind without the gate is the
lockout walk this object exists to stop (SPEC_S4a §3.1's asymmetry).

THE CALLER OWNS THE CLAIM. One `FleetLease` per attempt: `claim()` holds it; `reserve()` records the attempt
BEFORE the password is on the wire (#419, D1), so a crash, a lost write, a restart or a second process finds it;
`complete()` removes it after a session or a provably unbound failure, `refuse()` turns it into the answer;
`release()` lets the claim go — so the ping's due-ness is decided on the read its claim writes against, and
nothing here is shared between threads.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import math
import os
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import failure
from .fleetlogin import RETRY_POLICY
from .kube import ClusterClient, ClusterError
from .leader import LEASE_API

log = logging.getLogger(__name__)

PREFIX = "groupsync-dashboard.io/"
LEASE_TYPE_LABEL = PREFIX + "lease-type"
LEASE_TYPE = "fleet-account"
#: The instants this module writes: fixed-width UTC, `gsd/timeutil.py`'s stamp — never an age.
STAMP = "%Y-%m-%dT%H:%M:%SZ"
#: A write that met a 409 is re-read and re-applied at most this many times (the API conventions' duty).
CAS_TRIES = 3
#: The action every `fleet-state-unavailable` names: the grant the chart renders, and where.
GRANT = ("grant get/create/update on coordination.k8s.io/leases in this namespace to the dashboard's "
         "ServiceAccount — the chart renders it under leaderElection.enabled or a fleet account in use")

_DIGESTS: dict[tuple[str, str, str], str] = {}


class ClaimHeld(Exception):
    """Another claim on this account is live, or the Lease changed since the read a decision rests on. Not a
    failure: the caller binds nothing and tries on its next cycle."""


class FleetStateUnavailable(Exception):
    """The Lease could not be read or written: a 403 (the grant is absent), a 5xx, a write that met a 409
    `CAS_TRIES` times. FAIL CLOSED — nothing binds. Shaped as the finding it becomes, with the lookup's
    refusal fields (`gsd/fleetlookup.py#LookupRefused`): free, announced when it appears, rechecked every cycle."""

    code, spent, gated, secrets = "fleet-state-unavailable", False, False, ()

    def __init__(self, detail: str, action: str = GRANT):
        super().__init__(f"{self.code}: {detail}")
        self.detail, self.action = detail, action


def lease_name(account: str) -> str:
    """`gsd-fleet-` + sha256(username)[:16]: a DNS-1123 name whatever the username holds."""
    return "gsd-fleet-" + hashlib.sha256(account.encode("utf-8")).hexdigest()[:16]


def lease_digest(account: str, password: str, salt: str) -> str:
    """The password's fingerprint AS THE LEASE RECORDS IT: scrypt at the OWASP Password Storage Cheat Sheet's 16 MiB
    setting (N=2^14, r=8, p=5), 64 bits kept, salted with the account AND `salt` — the password Secret's own
    `metadata.uid`, which `gsd/fleetlookup.py#fleet_password` reads with the password, in the same GET.

    WHY THE UID (#419, D2): a Lease is read by whoever holds `get leases` in this namespace — `cluster-reader` among
    them, measured on the reference cluster, which cannot read the password Secret — and `ping-digest` fingerprints
    the VALID password every day. A fingerprint whose every other input is public verifies a guess offline, slow or
    not; the uid is readable only by whoever reads the Secret, who has the password already. It survives an update
    in place (a rotation) and changes only when the Secret is deleted and recreated, which re-arms the gate once.
    NOT the in-memory gate's sha256 prefix, which never leaves the process. 64 bits over-block on a collision and
    never bind (R3-2's rule). Computed once per (account, salt, password) per process; the cache is keyed on the
    password's sha256, never on the password."""
    key = (account, salt, hashlib.sha256(password.encode("utf-8")).hexdigest())
    if key not in _DIGESTS:
        _DIGESTS[key] = hashlib.scrypt(password.encode("utf-8"), salt=f"{account}\0{salt}".encode("utf-8"),
                                       n=2**14, r=8, p=5, dklen=8).hex()
    return _DIGESTS[key]


def claim_seconds(settings) -> int:
    """How long a claim stands before another process may judge it abandoned: the longest bind path under the
    settings it runs with — the login under `RETRY_POLICY` (each attempt at most discovery + authorize, two
    request timeouts, plus the policy's backoff) and then the read and the revoke (two more) — floored at 60.
    195 s at the defaults. Computed, never a constant: a longer requestTimeoutSeconds must not let a live
    claim look abandoned mid-login."""
    timeout = float(settings.request_timeout_seconds)
    backoff = sum(RETRY_POLICY.wait_after(n) for n in range(1, RETRY_POLICY.attempts))
    return max(60, math.ceil(RETRY_POLICY.attempts * 2 * timeout + backoff + 2 * timeout))


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STAMP)


def _micro(moment: datetime) -> str:
    """A Kubernetes MicroTime: EXACTLY six fractional digits (`gsd/leader.py#LeaderElector._now` says why)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _instant(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


@dataclass(frozen=True)
class FleetRecord:
    """One account's Lease as read: the claim, the gate, the ping's instants. Immutable; a write returns the
    next one."""

    account: str
    resource_version: str | None
    holder: str
    holder_until: datetime | None          # renewTime + leaseDurationSeconds, or None when unheld
    refused: dict | None                   # {digest, at, code, target[, uncertain, attempt]}: the account entry
    ping_last_attempt: datetime | None
    ping_last_ok: datetime | None
    ping_last_outcome: str | None
    ping_last_target: str | None
    ping_digest: str | None                # the password the last ATTEMPT was for (B3)
    raw: dict | None = field(default=None, repr=False, compare=False)

    def gated(self, digest: str) -> dict | None:
        """The account entry when its digest matches, whatever the target — every bind path's rule (B2) — compared in
        constant time (`hmac.compare_digest`). An entry whose digest is not this dashboard's gates every password: the
        safe direction, until it is removed."""
        if self.refused is None:
            return None
        saved = self.refused.get("digest")
        if not isinstance(saved, str) or not saved.isascii():
            return self.refused
        return self.refused if hmac.compare_digest(saved, digest) else None

    def in_flight(self, now: datetime) -> bool:
        """A live claim holds the account: another process may be binding as it now — `claim()`'s rule."""
        return bool(self.holder) and self.holder_until is not None and self.holder_until > now

    def reservation_pending(self, now: datetime, seconds: int) -> bool:
        """An `uncertain` entry inside its own attempt's window — `at` + `seconds`, + 1 for `stamp`'s truncation —
        may be an attempt under way; a confirmed refusal never is, and a later claim does not extend it (round 2)."""
        entry = self.refused or {}
        at = _instant(entry.get("at"))
        return bool(entry.get("uncertain")) and at is not None and now < at + timedelta(seconds=seconds + 1)

    def view(self) -> dict:
        """What the API and `/metrics` serve: instants and words as the Lease holds them, never the digest."""
        entry = self.refused
        return {"lease": lease_name(self.account),
                "last_attempt": stamp(self.ping_last_attempt) if self.ping_last_attempt else None,
                "last_ok": stamp(self.ping_last_ok) if self.ping_last_ok else None,
                "last_outcome": self.ping_last_outcome, "last_target": self.ping_last_target,
                "suspended": [{"target": entry.get("target"), "since": entry.get("at"), "code": entry.get("code")}]
                if entry else []}


def _record(account: str, obj: dict | None) -> FleetRecord:
    if not isinstance(obj, dict):
        return FleetRecord(account, None, "", None, None, None, None, None, None, None)
    meta, spec = obj.get("metadata") or {}, obj.get("spec") or {}
    ann = meta.get("annotations") or {}
    renewed, seconds = _instant(spec.get("renewTime")), spec.get("leaseDurationSeconds")
    refused = ann.get(PREFIX + "refused")
    if refused is not None:
        try:
            refused = json.loads(refused)
        except ValueError:
            refused = None
        # An entry that is not this dashboard's JSON gates every password (the safe direction) until removed.
        refused = refused if isinstance(refused, dict) else {"digest": None, "code": "login-refused", "target": "", "at": ""}
    return FleetRecord(
        account=account, resource_version=meta.get("resourceVersion"), holder=spec.get("holderIdentity") or "",
        holder_until=renewed + timedelta(seconds=seconds) if renewed and isinstance(seconds, int) else None,
        refused=refused, ping_last_attempt=_instant(ann.get(PREFIX + "ping-last-attempt")),
        ping_last_ok=_instant(ann.get(PREFIX + "ping-last-ok")), ping_last_outcome=ann.get(PREFIX + "ping-last-outcome"),
        ping_last_target=ann.get(PREFIX + "ping-last-target"), ping_digest=ann.get(PREFIX + "ping-digest"), raw=obj)


class FleetLease:
    """One attempt's handle on an account's Lease, through the host cluster's client: the pod's own
    ServiceAccount, the identity the lookup writes the cluster Secret with. Never shared between threads."""

    def __init__(self, host: ClusterClient, namespace: str, account: str, *, claim_seconds: int,
                 identity: str | None = None, clock: Callable[[], datetime] | None = None):
        self.host, self.namespace, self.account = host, namespace, account
        self.name = lease_name(account)
        # The pod's name, so `oc get leases.coordination.k8s.io` names the holder — the elector's rule.
        self.identity = identity or os.environ.get("POD_NAME") or socket.gethostname()
        self.claim_seconds = claim_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        #: The claim this instance holds, as its last write left it; None when it holds none.
        self.record: FleetRecord | None = None
        #: A write met a 409: the claim was judged expired and taken, so its holder is no longer ours to clear.
        self._lost = False

    def _call(self, method: str, obj: dict | None = None) -> dict | None:
        path = LEASE_API.format(ns=self.namespace)
        with self.host._client() as client:
            if method == "GET":
                return self.host._get(client, f"{path}/{self.name}", {})
            return self.host._send(client, method, path if method == "POST" else f"{path}/{self.name}", json=obj)

    def _unavailable(self, what: str, exc: ClusterError) -> FleetStateUnavailable:
        return FleetStateUnavailable(f"cannot {what} Lease {self.namespace}/{self.name}: {exc.outcome}: "
                                     f"{exc.message.split(': ', 1)[0]}")

    def read(self) -> FleetRecord:
        """The Lease without a claim; an absent one is an empty record, not an error."""
        try:
            obj = self._call("GET")
        except ClusterError as exc:
            if exc.message.startswith("HTTP 404"):
                return _record(self.account, None)
            raise self._unavailable("read", exc) from exc
        return _record(self.account, obj)

    def claim(self, read: FleetRecord | None = None, **changes: str | None) -> FleetRecord:
        """Hold the account: ONE write carrying the resourceVersion of `read` — the record a caller decided on —
        or of a fresh read. A live claim, anyone's, this process's included, is ClaimHeld; so is a 409, because the
        Lease changed since that read. `changes` ride the same write: the ping's attempt is recorded atomically
        with its claim, before its bind, so a second replica or a crash cannot ping twice (B3)."""
        now = self._clock()
        record = read if read is not None else self.read()
        if record.in_flight(now):
            raise ClaimHeld(f"{record.holder} holds {self.name} until {stamp(record.holder_until)}")
        obj = _applied(record.raw or {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                                      "metadata": {"name": self.name, "namespace": self.namespace,
                                                   "labels": {LEASE_TYPE_LABEL: LEASE_TYPE}}},
                       {"account": self.account, **changes})
        obj["spec"] = {**(obj.get("spec") or {}), "holderIdentity": self.identity,
                       "leaseDurationSeconds": self.claim_seconds, "acquireTime": _micro(now), "renewTime": _micro(now)}
        try:
            written = self._call("POST" if record.raw is None else "PUT", obj)
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise ClaimHeld(f"{self.name} changed since it was read") from exc
            raise self._unavailable("claim", exc) from exc
        self.record, self._lost = (_record(self.account, written) if isinstance(written, dict) else self.read()), False
        return self.record

    def reserve(self, target: str, digest: str) -> None:
        """THE ATTEMPT, ON THE LEASE BEFORE THE PASSWORD IS ON THE WIRE (#419, D1): the account entry itself, marked
        `uncertain`, written against the claim's own resourceVersion. A 409 is ClaimHeld — the claim was taken
        meanwhile, and this attempt is abandoned, NEVER re-applied (re-applying is how a paused holder binds after
        the process that took over did); any other failure is FleetStateUnavailable, and nothing binds. From here a
        crash, a lost refusal write, a restart and a second process all find the entry: the directory may have seen
        the password. Its nonce, `attempt`, tells it from another reservation of the same password (round 2)."""
        entry = json.dumps({"digest": digest, "at": stamp(self._clock()), "code": "login-failed", "target": target,
                            "uncertain": True, "attempt": uuid.uuid4().hex}, sort_keys=True)
        try:
            written = self._call("PUT", _applied(self.record.raw, {"refused": entry}))
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise ClaimHeld(f"{self.name} changed since it was claimed") from exc
            raise self._unavailable("reserve", exc) from exc
        self.record = _record(self.account, written) if isinstance(written, dict) else self.read()

    def complete(self) -> None:
        """The attempt ended without the directory refusing it — a session came back, or the password was provably
        never written — so its entry goes. Never raises: after a 409 it goes only while it is still this attempt's
        reservation (`_put`), and a removal that fails leaves the safe direction."""
        try:
            self._put({"refused": None}, release=False)
        except FleetStateUnavailable as exc:
            failure(log, "fleet-state-unavailable", phase="credential", outcome=exc.code, account=self.account,
                    lease=self.name, action=f"the attempt's entry stays on the Lease and gates this password until "
                                            f"it is removed: {exc.action}", detail=exc.detail)
        except Exception:  # noqa: BLE001 - cleanup never replaces the outcome it follows
            log.exception("clearing the attempt's entry on Lease %s/%s failed; it stays", self.namespace, self.name)

    def refuse(self, target: str, digest: str, code: str) -> None:
        """A bound answer, recorded on the Lease BEFORE the process's gate and before the finding (SPEC_S4c §3.3,
        step 5), so that a restart and another replica read it — after a 409, only over this attempt's own reservation
        (`_put`). Never raises: when the Lease cannot take it, one line says the process's gate is the only memory
        until it restarts, and the caller's refusal goes on."""
        entry = json.dumps({"digest": digest, "at": stamp(self._clock()), "code": code, "target": target}, sort_keys=True)
        try:
            self._put({"refused": entry}, release=False)
        except FleetStateUnavailable as exc:
            failure(log, "fleet-state-unavailable", phase="credential", outcome=exc.code, account=self.account,
                    lease=self.name, action=f"the refusal is held in this process only, so a restart or another replica "
                                            f"may send this password once more: {exc.action}", detail=exc.detail)
        except Exception:  # noqa: BLE001 - it runs inside the caller's refusal, which it must never replace
            log.exception("recording a refusal on Lease %s/%s failed; this process's gate holds it", self.namespace, self.name)

    def release(self, **changes: str | None) -> FleetRecord | None:
        """Let the claim go, with any last changes, in one write; the record it left, or None. NEVER raises —
        cleanup never replaces the exception it is cleaning up after (#283's rule): a failure is one line, and the
        claim expires by itself."""
        try:
            if self.record is not None:
                return self._put(changes, release=True)
        except FleetStateUnavailable as exc:
            failure(log, "fleet-state-unavailable", phase="credential", outcome=exc.code, account=self.account,
                    lease=self.name, action=f"the claim expires by itself within {self.claim_seconds}s: {exc.action}",
                    detail=exc.detail)
        except Exception:  # noqa: BLE001 - a release must never raise past its caller
            log.exception("releasing Lease %s/%s failed; the claim expires by itself", self.namespace, self.name)
        finally:
            self.record = None
        return None

    def _put(self, changes: dict, *, release: bool) -> FleetRecord:
        record = self.record
        based_on = (record.raw["metadata"].get("annotations") or {}).get(PREFIX + "refused")
        for _ in range(CAS_TRIES):
            obj = _applied(record.raw, changes)
            if release and not self._lost:
                obj["spec"]["holderIdentity"] = ""
            try:
                written = self._call("PUT", obj)
            except ClusterError as exc:
                if not exc.message.startswith("HTTP 409"):
                    raise self._unavailable("write", exc) from exc
                # The Lease changed under the claim — it was judged expired and taken. The changes are re-applied
                # to it as it now is; its holder is not ours to clear, and the entry is touched only while it is
                # still, byte for byte, the one this write was decided on — its nonce names it (#419, round 2).
                record, self._lost = self.read(), True
                if record.raw is None:
                    raise FleetStateUnavailable(f"Lease {self.namespace}/{self.name} was deleted under a claim") from exc
                if (record.raw["metadata"].get("annotations") or {}).get(PREFIX + "refused") != based_on:
                    changes = {k: v for k, v in changes.items() if k != "refused"}
                continue
            self.record = _record(self.account, written) if isinstance(written, dict) else self.read()
            return self.record
        raise FleetStateUnavailable(f"Lease {self.namespace}/{self.name} changed under each of {CAS_TRIES} writes")


def _applied(obj: dict, changes: dict) -> dict:
    """A copy of the Lease with annotation changes applied: `ping_last_ok` is `ping-last-ok`; None removes one."""
    out = copy.deepcopy(obj)
    ann = out.setdefault("metadata", {}).setdefault("annotations", {})
    for key, value in changes.items():
        if value is None:
            ann.pop(PREFIX + key.replace("_", "-"), None)
        else:
            ann[PREFIX + key.replace("_", "-")] = value
    return out


__all__ = ["CAS_TRIES", "ClaimHeld", "FleetLease", "FleetRecord", "FleetStateUnavailable", "LEASE_TYPE",
           "LEASE_TYPE_LABEL", "claim_seconds", "lease_digest", "lease_name", "stamp"]
