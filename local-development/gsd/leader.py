"""Leader election via the Kubernetes Lease API.

Only the leader polls. Every replica still serves the API and /metrics, so scaling up adds
read capacity without adding writers.

WHY THIS IS NEEDED even at one replica: `Recreate` is not instantaneous, a `kubectl scale`
is one keystroke, and a partitioned node can leave an old pod running while a new one
starts. Any of those puts two pollers on one database, and the poll loop is not idempotent
across writers — two of them racing on `sync_members` produce membership events for changes
that never happened.

WHAT THIS DOES NOT SOLVE: the store is SQLite on a ReadWriteOnce volume, so a second replica
cannot mount it at all. Election makes concurrent pollers safe; it does not make the storage
shared. Running more than one replica additionally requires ReadWriteMany, and SQLite over a
network filesystem has its own locking caveats. See the chart README.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import UTC, datetime, timedelta

import httpx

log = logging.getLogger(__name__)

LEASE_API = "/apis/coordination.k8s.io/v1/namespaces/{ns}/leases"
SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SA_NAMESPACE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


def _in_cluster() -> bool:
    return os.path.isfile(SA_TOKEN)


class LeaderElector:
    """Acquires and renews a Lease, and reports whether this process holds it.

    Deliberately hand-rolled against the REST API rather than pulling in the kubernetes
    client: the app already speaks to the API with httpx and a projected token, and one more
    dependency for one more resource is not worth it.
    """

    def __init__(
        self,
        name: str,
        namespace: str | None = None,
        identity: str | None = None,
        lease_seconds: int = 30,
        renew_seconds: int = 10,
    ):
        self.name = name
        self.namespace = namespace or self._namespace()
        # The pod name, so `oc get lease` names the actual holder. Falling back to hostname
        # keeps this usable outside a cluster.
        self.identity = identity or os.environ.get("POD_NAME") or socket.gethostname()
        self.lease_seconds = lease_seconds
        self.renew_seconds = renew_seconds

        self._is_leader = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def _namespace() -> str:
        try:
            with open(SA_NAMESPACE, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            return "default"

    @property
    def is_leader(self) -> bool:
        return self._is_leader.is_set()

    def _client(self) -> httpx.Client:
        with open(SA_TOKEN, encoding="utf-8") as handle:
            token = handle.read().strip()
        return httpx.Client(
            base_url="https://kubernetes.default.svc",
            headers={"Authorization": f"Bearer {token}"},
            verify=SA_CA,
            timeout=10.0,
        )

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _body(self, transitions: int) -> dict:
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": {"name": self.name, "namespace": self.namespace},
            "spec": {
                "holderIdentity": self.identity,
                "leaseDurationSeconds": self.lease_seconds,
                "acquireTime": self._now(),
                "renewTime": self._now(),
                "leaseTransitions": transitions,
            },
        }

    def _try_acquire(self, client: httpx.Client) -> bool:
        """One election round. Returns whether this process holds the lease afterwards."""
        path = LEASE_API.format(ns=self.namespace)
        response = client.get(f"{path}/{self.name}")

        if response.status_code == 404:
            created = client.post(path, json=self._body(0))
            # 409 means another replica created it in the same instant; it won, and that is
            # a normal outcome rather than an error.
            return created.status_code in (200, 201)

        if response.status_code != 200:
            log.warning("leader election: GET lease returned %s", response.status_code)
            return False

        lease = response.json()
        spec = lease.get("spec") or {}
        holder = spec.get("holderIdentity")
        transitions = spec.get("leaseTransitions", 0) or 0

        renew = spec.get("renewTime")
        expired = True
        if renew:
            try:
                last = datetime.fromisoformat(renew.replace("Z", "+00:00"))
                expired = (datetime.now(UTC) - last) > timedelta(seconds=self.lease_seconds)
            except ValueError:
                expired = True

        if holder == self.identity:
            body = self._body(transitions)
            # Keep acquireTime as it was; only renewTime moves while we hold it.
            body["spec"]["acquireTime"] = spec.get("acquireTime") or self._now()
        elif expired:
            log.info("leader election: lease held by %r has expired, taking it", holder)
            body = self._body(transitions + 1)
        else:
            return False

        body["metadata"]["resourceVersion"] = lease["metadata"]["resourceVersion"]
        updated = client.put(f"{path}/{self.name}", json=body)
        # 409 = someone else wrote first. Losing a race is the mechanism working, not a fault.
        return updated.status_code == 200

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._client() as client:
                    held = self._try_acquire(client)
            except Exception:  # noqa: BLE001
                # Never let an API blip end the loop. Losing leadership on error is the safe
                # direction: a pod that cannot confirm it leads must stop polling, or a
                # network partition produces two writers.
                log.exception("leader election round failed; standing down")
                held = False

            if held and not self._is_leader.is_set():
                log.info("became leader (%s/%s as %s)", self.namespace, self.name, self.identity)
                self._is_leader.set()
            elif not held and self._is_leader.is_set():
                log.warning("lost leadership; the poller will stop")
                self._is_leader.clear()

            self._stop.wait(self.renew_seconds)

    def start(self) -> None:
        if not _in_cluster():
            # Outside a cluster there is nothing to contend with, so run as leader rather
            # than refusing to poll and looking broken in local development.
            log.info("no ServiceAccount token; assuming sole instance and polling")
            self._is_leader.set()
            return
        self._thread = threading.Thread(target=self._run, name="leader-election", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._is_leader.clear()
        if self._thread:
            self._thread.join(timeout=5)
