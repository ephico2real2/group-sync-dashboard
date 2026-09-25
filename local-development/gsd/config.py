"""Cluster configuration.

A cluster's bearer token is deliberately kept out of this module's data model. It is
resolved on demand from a file or environment variable (PLAN §5: "Tokens live in Secrets
mounted into the backend, never in the config object and never returned by the API"), so a
ClusterConfig can be serialised into an API response without leaking anything.

In-cluster the token arrives as a mounted Secret -> ``tokenFile``. For local development
against CRC it is easiest to pass ``oc whoami -t`` -> ``tokenEnv``. Both resolve to the
same thing; the plan's ``tokenSecretRef`` is the Kubernetes-side name of the file mount.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
import stat
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

# The visibility tier cache lifetime, in seconds — declared HERE and nowhere else.
#
# It lives in this module because gsd.kube imports gsd.config and not the reverse, so this is
# the only direction a shared constant can travel. `gsd.kube.TIER_TTL_SECONDS` re-exports it.
#
# WHY ONE DECLARATION MATTERS. The number was previously written out twice — a Settings default
# here and an identical constructor default in kube.py — and that is exactly how the knob
# shipped inert: nothing passed the setting through to the resolver, the resolver fell back to
# its own 60, and every test exercising the default agreed with the bug because both halves
# said the same thing. Two literals that must agree will eventually disagree; one cannot.
VISIBILITY_TIER_TTL_DEFAULT = 60

# ── Per-cluster authorization (docs/ACCESS_CONTROL.md §11) ─────────────────────────────────────
# The oauth-proxy authenticates a viewer against the HOSTING cluster only, so what a viewer may see
# ABOUT ANOTHER cluster is a per-cluster decision. Four policies, and the words are the wire
# vocabulary (/api/whoami and /api/clusters carry them), so they are declared once, here.
VISIBILITY_INHERIT = "inherit"        # the host's tier decides — today's behaviour
VISIBILITY_SELF_ONLY = "self-only"    # every viewer is the self tier on this cluster
VISIBILITY_HIDDEN = "hidden"          # polled, never served through /api
VISIBILITY_REMOTE_SAR = "remote-sar"  # this cluster's own RBAC decides, by SubjectAccessReview
CLUSTER_VISIBILITIES = (
    VISIBILITY_INHERIT, VISIBILITY_SELF_ONLY, VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR,
)
# Whether the reader's OpenShift username — the `User` object's name, which the host authenticated — names
# the same person on this cluster. Readers are matched by that name on every cluster (design D3); `none` says
# the name is nobody here, so nothing on this cluster is keyed by it.
IDENTITY_SAME_AS_HOST = "same-as-host"
IDENTITY_NONE = "none"
CLUSTER_IDENTITIES = (IDENTITY_SAME_AS_HOST, IDENTITY_NONE)


def remote_policy(visibility: str | None, identity: str | None) -> tuple[str, str]:
    """A non-host cluster's (visibility, identity) with the defaults resolved (SPEC_D2b §3.2, design D2).

    A remote that states nothing is asked about the reader itself: remote-sar + same-as-host. `identity: none`
    says the host's username is nobody on that cluster, so it cannot be asked about them: with no visibility
    stated it keeps self-only, as before. Resolution only — the explicit pair remote-sar + none is refused
    where it is READ (the loader, the Secret parser, the chart), not here."""
    if visibility is None:
        visibility = VISIBILITY_SELF_ONLY if identity == IDENTITY_NONE else VISIBILITY_REMOTE_SAR
    if identity is None:
        identity = IDENTITY_SAME_AS_HOST if visibility == VISIBILITY_REMOTE_SAR else IDENTITY_NONE
    return visibility, identity


class ConfigError(Exception):
    """Raised for a malformed or unusable cluster configuration."""


_ca_cache: dict[str, tuple[tuple, ssl.SSLContext]] = {}
_ca_cache_lock = threading.Lock()


def _trusted_ca_context() -> ssl.SSLContext | None:
    """Build one SSL context from every CA bundle mounted into the pod.

    GSD_TRUSTED_CA_FILE is colon-separated, like SSL_CERT_FILE, because two independent
    sources can be mounted: the bundle OpenShift injects (system trust merged with
    proxy/cluster.spec.trustedCA) and a ConfigMap supplied by hand for a CA the cluster has
    never been told about. Either, both, or neither.

    They are LOADED IN TURN rather than concatenated into a temporary file: the root
    filesystem is read-only, and writing certificates to /tmp to work around that would put
    them somewhere less controlled than where they started.

    Cached, because this is consulted on every poll of every cluster and parsing a 226 KB,
    148-certificate bundle each time is pure waste. Three details matter:

    * the cache is keyed on the ENV VALUE, not global, so changing the configured paths
      takes effect rather than being masked by a stale entry;
    * an entry holds only while every file is the one it was built from (#340). kubelet
      updates a mounted ConfigMap by writing a new timestamped directory and swapping the
      `..data` symlink the file resolves through, so `os.stat` sees a new inode; a file
      rewritten in place changes its mtime, at the filesystem's timestamp granularity. A replaced bundle is then read as a restart
      would read it, including failing the same way if it does not load;
    * a null result is NOT cached. The injected ConfigMap is populated asynchronously, so
      it can legitimately be absent for the first moments of a pod's life; caching that
      absence would mean never picking it up without a restart.
    """
    raw = os.environ.get("GSD_TRUSTED_CA_FILE", "")
    if not raw:
        return None

    paths, identity = [], []
    for path in (part.strip() for part in raw.split(":")):
        try:
            st = os.stat(path) if path else None
        except OSError:
            continue
        if st is not None and stat.S_ISREG(st.st_mode):
            paths.append(path)
            identity.append((path, st.st_ino, st.st_mtime_ns, st.st_size))
    if not paths:
        return None  # deliberately uncached — see above

    cached = _ca_cache.get(raw)
    if cached is not None and cached[0] == tuple(identity):
        return cached[1]

    context = ssl.create_default_context()
    for path in paths:
        try:
            context.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError) as exc:
            raise ConfigError(f"cannot load trusted CA bundle {path!r}: {exc}") from exc

    with _ca_cache_lock:
        _ca_cache[raw] = (tuple(identity), context)
    log.info("loaded %d trusted CA bundle(s): %s", len(paths), ", ".join(paths))
    return context


SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


# The shipped rule's own constants, imported rather than restated: two copies of this list is the
# divergence #255 exists to end (`gsd/home.py` is import-free, so there is no cycle).
from .home import PLATFORM_NAMESPACE_PREFIXES, PLATFORM_NAMESPACES


@dataclass(frozen=True)
class PlatformNamespaces:
    """Which namespaces are the platform's rather than a workload's (#255).

    THREE AXES, AND EACH ONE IS LOAD-BEARING — measured on the reference cluster against the seven
    infrastructure namespaces the shipped prefix rule calls application namespaces:
    `-operator` catches three (`cert-manager-operator`, `group-sync-operator`,
    `namespace-configuration-operator`), `-manager` one (`cert-manager`), `-provisioner` one
    (`hostpath-provisioner`), and `kyverno` and `group-sync-dashboard` match no pattern at all and
    must be named. Prefixes alone miss all seven.

    Plain prefix / suffix / exact-name matching, deliberately: a glob or a regular expression in a
    values file is an injection surface and an unreviewable diff, and these three cover every case
    measured. `additional_*` APPENDS to the shipped defaults — an estate that restated the Red Hat
    list would have to maintain it across OpenShift releases, and the common case is additive.
    """

    prefixes: tuple[str, ...] = PLATFORM_NAMESPACE_PREFIXES
    suffixes: tuple[str, ...] = ()
    names: frozenset[str] = PLATFORM_NAMESPACES
    additional_prefixes: tuple[str, ...] = ()
    additional_suffixes: tuple[str, ...] = ()
    additional_names: frozenset[str] = frozenset()

    # THE namespace classifier — names, prefixes, suffixes, each with its values.yaml
    # `platformNamespaces.additional*` axis appended; every consumer of "is this namespace the platform's" calls it.
    # PLATFORM-CLASSIFICATION (#255, #353)
    def matches(self, name: str) -> bool:
        """Whether this namespace is the platform's. Exact names first: the cheapest test, and the
        one an operator reaches for when a name has no pattern in it."""
        if name in self.names or name in self.additional_names:
            return True
        if self.prefixes and name.startswith(self.prefixes):
            return True
        if self.additional_prefixes and name.startswith(self.additional_prefixes):
            return True
        if self.suffixes and name.endswith(self.suffixes):
            return True
        return bool(self.additional_suffixes) and name.endswith(self.additional_suffixes)

    def unmatched(self, names: list[str]) -> dict[str, list[str]]:
        """Every configured pattern that matches nothing in `names`, by axis.

        A pattern catching zero namespaces is a typo or a convention that was decommissioned, and a
        stale entry is exactly how an allowlist rots — so it is reportable rather than inert. Only
        the `additional_*` axes are reported: the shipped defaults legitimately match nothing on a
        cluster that happens to have no `kube-public`, and telling an operator their defaults are
        stale would be noise they cannot act on.
        """
        stale: dict[str, list[str]] = {}
        for axis, values, test in (
            ("additionalPrefixes", self.additional_prefixes, str.startswith),
            ("additionalSuffixes", self.additional_suffixes, str.endswith),
        ):
            missing = [v for v in values if not any(test(n, v) for n in names)]
            if missing:
                stale[axis] = missing
        missing_names = sorted(n for n in self.additional_names if n not in set(names))
        if missing_names:
            stale["additionalNames"] = missing_names
        return stale
# ── Connection modes (SPEC_S3 §3/§4 — S3a ships the keys, S3b connects) ─────────────────────────
# A values stanza, or a Secret's `config`, may declare HOW the dashboard obtains a remote cluster's
# credential instead of carrying one. Both readers learn the same three keys (§2's equivalence), and
# a cluster declaring a mode is listed with a credential kind that cannot be resolved yet — the way
# `oauth` (#119 P2) already is — and is not polled, so it never reaches the poll path as a false
# `auth_failed` for a credential that was never presented (§4.2).
CONNECTION_MODE_KEYS = ("saTokenLookup", "userSelfLogin")
BOOTSTRAP_KEY = "ldapConnectionBootstrap"
CONNECTION_KEYS = (*CONNECTION_MODE_KEYS, BOOTSTRAP_KEY)
CREDENTIAL_LOOKUP = "remote-lookup"     # saTokenLookup: a ServiceAccount token READ FROM the target
#: `remote-lookup`, not `lookup`: the word is shown on the tab and written into a Secret's
#: `token-source`, where "lookup" alone says nothing about WHERE it was looked up or what was
#: found. It pairs with `self-login` — both say how the credential was got, in two words.
CREDENTIAL_SELF_LOGIN = "self-login"    # userSelfLogin: the bootstrap account polls as itself
#: Credential kinds the process cannot resolve yet, each with the reason the poller logs instead of
#: polling. A kind in this table is never handed to ClusterClient.
CREDENTIAL_PENDING_REASONS = {
    "oauth": "declares oauth (#119 P2, not built)",
    CREDENTIAL_LOOKUP: "declares saTokenLookup — S3b's lookup has not retrieved a credential yet; the Cluster "
                       "Configurations tab's findings say why when it is late",
    CREDENTIAL_SELF_LOGIN: "declares userSelfLogin — the self-login mode is S3b's #285, not built; nothing has been obtained yet",
}
#: Every key a values stanza may carry. The parser's accepted `config` keys include CONNECTION_KEYS
#: too, and tests/test_connection_modes.py fails the commit on which the two sets diverge (§4.1).
VALUES_CLUSTER_KEYS = frozenset({
    "name", "apiUrl", "tokenEnv", "tokenFile", "caBundleFile", "insecureSkipVerify", "enabled",
    "visibility", "identity", "dashboardController", *CONNECTION_KEYS,
})
# The bootstrap account is a username the target's OAuth server will be asked to bind: letters,
# digits and the separators an LDAP uid or an OpenShift user name carries. Not free text — a space, a
# colon or a slash is a paste error, refused by name and never sent to a directory. Refusals do not
# repeat the value, in case something other than a username was written into it.
_BOOTSTRAP_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,254}$")


def valid_bootstrap_username(value: object) -> bool:
    return isinstance(value, str) and bool(_BOOTSTRAP_USERNAME.match(value))


@dataclass(frozen=True)
class ClusterConfig:
    """One observed cluster.

    ``name`` doubles as the cluster id used in API paths (PLAN §11), so it must be URL-safe
    and stable — renaming a cluster orphans its stored observations.
    """

    name: str
    api_url: str
    token_env: str | None = None
    token_file: str | None = None
    ca_bundle_file: str | None = None
    insecure_skip_verify: bool = False
    enabled: bool = True
    # None means "not set", resolved by Settings.cluster_policy: the host is inherit/same-as-host
    # (its viewer IS a host identity), every other cluster by remote_policy — remote-sar/same-as-host
    # when it states nothing, self-only/none when it states only `identity: none` (SPEC_D2b §3.2).
    # Resolved there and not here so a hand-built Settings and a chart-rendered one agree on what a
    # second cluster serves by default: its own RBAC decides, and every failure is the self tier.
    visibility: str | None = None
    identity: str | None = None
    # THE CONTROLLER (#249): this pod's own cluster — the one the oauth-proxy authenticates readers
    # against, whose Services the Kyverno breaker URL names, that `same-as-host`/`inherit` resolve
    # against, and on which the visibility tiers ask their SubjectAccessReviews. Declared rather than
    # inferred from list order: alphabetising `clusters[]`, or disabling the first entry for a
    # moment, used to move all four silently. A values concept only — a Secret-sourced cluster is by
    # definition remote, and the parser refuses the key there.
    dashboard_controller: bool = False
    # A Secret-sourced cluster (docs/specs/SPEC_S1_cluster_secrets.md): the credential lives in the
    # process's memory, read from the Secret each discovery — never on disk, never in a repr, never
    # compared (two configs that differ only by a rotated token are the same cluster).
    token_value: str | None = field(default=None, repr=False, compare=False)
    ca_data: str | None = field(default=None, repr=False, compare=False)   # PEM text from tlsClientConfig.caData
    oauth_username: str | None = field(default=None, repr=False, compare=False)
    oauth_password: str | None = field(default=None, repr=False, compare=False)
    source: str = "values"                       # values | secret:<name> | configmap:<name>:<index>
    # SPEC_S5: ConfigMap name, UID and connection digest; no credential, no second registry.
    onboarding: tuple[str, str, str] = ()
    labels: tuple[tuple[str, str], ...] = ()     # the Secret's other labels, the fleet's metadata for the tab
    # SPEC_S3 §3 (S3a): the connection mode declared instead of a credential, and the bootstrap account
    # that performs the login. Inert until S3b connects: the cluster is listed with a pending credential
    # kind (`credential_pending`) and is not polled.
    sa_token_lookup: bool = False
    user_self_login: bool = False
    ldap_connection_bootstrap: str | None = None
    # A Secret-sourced cluster's `groupsync-dashboard.io/token-source` annotation, recorded by the reader
    # (SPEC_D2b §3.4). When it names the credential kind of the values stanza of the same name, the Secret
    # is the lookup's own write for that stanza: ClusterRegistry.merge keeps its credential and serves the
    # stanza's policy and `enabled`. None for a values entry and for a Secret that carries no annotation.
    token_source: str | None = field(default=None, repr=False)

    @property
    def tls_mode(self) -> dict:
        """How this cluster's API server certificate is verified, for the wire (SPEC_S1 notes, the
        operator's ruling of 2026-09-20): `insecure` — verification off; `ca` — `caData` (a Secret's own
        bundle), `caBundleFile` (a values entry's named file), `serviceAccount` (the pod's SA CA path),
        or `trusted-bundle` (the default: GSD_TRUSTED_CA_FILE — the chart's trustedCA bundles — plus the
        system store). Never the PEM."""
        if self.insecure_skip_verify:
            return {"insecure": True, "ca": None}
        if self.ca_data:
            return {"insecure": False, "ca": "caData"}
        if self.ca_bundle_file == SA_CA_PATH:
            return {"insecure": False, "ca": "serviceAccount"}
        if self.ca_bundle_file:
            return {"insecure": False, "ca": "caBundleFile"}
        return {"insecure": False, "ca": "trusted-bundle"}

    @property
    def credential_kind(self) -> str:
        """What authenticates this cluster, as a word the API may say: in-cluster (the pod's SA token
        path), file (a values entry's tokenFile/tokenEnv), bearer (a Secret's bearerToken), oauth (a
        Secret's username/password — #119 P2, not resolvable yet), lookup / self-login (a declared
        connection mode, SPEC_S3 — not resolvable until S3b). Never the value."""
        if self.oauth_username is not None or self.oauth_password is not None:
            return "oauth"
        if self.token_value is not None:
            return "bearer"
        if self.token_file == SA_TOKEN_PATH:
            return "in-cluster"
        if self.sa_token_lookup:
            return CREDENTIAL_LOOKUP
        if self.user_self_login:
            return CREDENTIAL_SELF_LOGIN
        return "file"

    @property
    def connection_mode(self) -> str | None:
        """The declared mode's key — `saTokenLookup` or `userSelfLogin` — or None (SPEC_S3 §3)."""
        if self.sa_token_lookup:
            return "saTokenLookup"
        if self.user_self_login:
            return "userSelfLogin"
        return None

    @property
    def credential_pending(self) -> str | None:
        """Why this cluster's credential cannot be resolved yet, or None when it can (SPEC_S3 §4.2).
        The poller lists a pending cluster and does not poll it; `oauth` and the S3 modes share the gate."""
        return CREDENTIAL_PENDING_REASONS.get(self.credential_kind)

    def resolve_token(self) -> str:
        """Read the token at the moment it is needed.

        Deliberately re-read rather than cached: a mounted Secret is updated in place when
        the token is rotated, and a long-lived process that cached the value at startup
        would keep presenting the stale one until restarted (PLAN §13 Q1).
        """
        if self.token_value is not None:
            if not self.token_value.strip():
                raise ConfigError(f"cluster {self.name!r}: the Secret's bearerToken is empty")
            return self.token_value.strip()
        if self.oauth_username is not None or self.oauth_password is not None:
            # The kind parses and is listed so the tab can say what the Secret declares; exchanging it
            # for a token against the remote OAuth server is #119 P2 and is not built.
            raise ConfigError(
                f"cluster {self.name!r}: username/password exchange against the OAuth server is #119 P2, not built"
            )
        if self.connection_mode is not None:
            # Listed so the tab can say what the stanza declares; obtaining the credential is S3b. The
            # poller never asks (`credential_pending`), so this is reached only by a direct caller.
            raise ConfigError(f"cluster {self.name!r}: {CREDENTIAL_PENDING_REASONS[self.credential_kind]}")
        if self.token_file:
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigError(
                    f"cluster {self.name!r}: cannot read tokenFile {self.token_file!r}: {exc}"
                ) from exc
            if not token:
                raise ConfigError(f"cluster {self.name!r}: tokenFile {self.token_file!r} is empty")
            return token

        if self.token_env:
            token = os.environ.get(self.token_env, "").strip()
            if not token:
                raise ConfigError(
                    f"cluster {self.name!r}: tokenEnv {self.token_env!r} is unset or empty"
                )
            return token

        raise ConfigError(f"cluster {self.name!r}: neither tokenFile nor tokenEnv configured")

    def verify(self) -> bool | ssl.SSLContext:
        """The value httpx expects for ``verify``.

        An SSLContext rather than a path: httpx deprecated the bare-string form, and
        building the context here fails loudly at configuration time if the CA bundle is
        missing or malformed, instead of at the first poll.
        """
        if self.insecure_skip_verify:
            return False

        # A Secret-sourced cluster carries its CA as text (tlsClientConfig.caData, decoded at parse
        # time — a bundle that does not load was refused there, so this cannot raise for a parsed one).
        if self.ca_data:
            try:
                return ssl.create_default_context(cadata=self.ca_data)
            except ssl.SSLError as exc:
                raise ConfigError(f"cluster {self.name!r}: the Secret's caData does not load: {exc}") from exc

        # An explicit per-cluster bundle always wins.
        bundle = self.ca_bundle_file

        # Otherwise fall back to the cluster-wide trusted CA bundle, if one is mounted.
        #
        # This is what makes EXTERNAL clusters work without per-cluster configuration. Their
        # API servers are usually signed by a corporate CA, which is not in Python's default
        # trust store, so verification fails and the cluster shows as unreachable — a TLS
        # problem that presents as an outage. OpenShift will inject that CA for us: an empty
        # ConfigMap labelled `config.openshift.io/inject-trusted-cabundle: "true"` is filled
        # with the system bundle MERGED with proxy/cluster's trustedCA. Measured on a stock
        # cluster: 148 certificates.
        #
        # Deliberately a fallback rather than a merge: a cluster that names its own bundle is
        # making a specific statement about what it trusts, and silently widening that would
        # be the wrong kind of helpful.
        if bundle:
            try:
                return ssl.create_default_context(cafile=bundle)
            except (OSError, ssl.SSLError) as exc:
                # Name the SOURCE, not only the path: "cannot load /etc/pki/..." sends
                # someone hunting a file when the fix is in whichever setting named it.
                raise ConfigError(
                    f"cluster {self.name!r}: cannot load caBundleFile {bundle!r}: {exc}"
                ) from exc

        return _trusted_ca_context() or True

    def connection_fingerprint(self) -> str:
        """A digest of everything a ClusterClient connects with that is fixed on this object. Equality cannot see a
        rotated Secret credential (those fields are compare=False by design), so a resolver keyed on this is rebuilt
        when — and only when — the connection changes. A tokenFile's content, a tokenEnv's value and an explicit
        caBundleFile are re-read by every ClusterClient._client call and need no rebuild; their names are here."""
        material = json.dumps([self.api_url, self.credential_kind, self.token_value or "", self.token_file or "",
                               self.token_env or "", self.oauth_username or "", self.oauth_password or "",
                               self.ca_data or "", self.ca_bundle_file or "", bool(self.insecure_skip_verify)])
        return hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class Settings:
    """Process-wide settings."""

    clusters: list[ClusterConfig] = field(default_factory=list)
    """The values-declared clusters — the bootstrap source, strict at load. The runtime source is
    `cluster_registry` (labelled Secrets, docs/specs/SPEC_S1_cluster_secrets.md); read the two merged
    through `effective_clusters()` / `cluster()`, never this list alone, except for the host."""
    poll_interval_seconds: int = 60
    """PLAN §6: 60s, far finer than the fastest schedule seen in practice."""

    schedule_grace_seconds: int = 120
    """Slack added before a CR is called late.

    A sync does not land exactly on its cron minute — 3-14s of scheduler latency was
    measured on CRC — and our own poll adds up to ``poll_interval_seconds`` on top. Without
    this grace, the age of a healthy CR briefly exceeds one interval near the end of every
    cycle and the state flaps to ``late`` on each pass. See state.py.
    """

    binding_interval_seconds: int = 3600

    discovery_interval_seconds: int = 300
    """Cluster discovery and the #284 lookup's retry backoff. Its own timer, so an hourly binding
    refresh never delays a cluster applied with oc or GitOps (the operator, 2026-09-25)."""

    # Login capture. OFF by default: it needs a read grant the chart only creates when asked, and it
    # records nothing at all unless the authentication operator's logLevel is Debug — so enabling it
    # here alone is inert rather than broken.
    login_capture_enabled: bool = False
    # Where the oauth-server runs. A value rather than a constant only because the chart's Role is
    # created in this namespace and the two must agree; it is fixed on any normal OpenShift cluster.
    login_capture_namespace: str = "openshift-authentication"
    # Providers whose SUCCESSES are break-glass rather than people — kubeadmin and developer arrive on
    # the HTPasswd provider. Passed to the store so ungoverned-user counts exclude them; the store
    # cannot know which of a cluster's providers are local.
    login_capture_htpasswd_providers: tuple[str, ...] = ("developer",)
    # 0 disables pruning. These rows are the only record that survives the pods, so the default is
    # generous — over a year — and the prune is bounded per cycle so a long backlog cannot hold the
    # single writer.
    login_retention_days: int = 400
    # WHICH LOG. `pod-log` reads the oauth-server pods' logs, which name a person only at
    # spec.logLevel: Debug on the authentication operator CR. `audit-log` reads
    # /var/log/oauth-server/audit.log on the control-plane nodes through the API server's node
    # proxy: no Debug, no OAuth roll, history back to the rotated files — and a cluster-wide read
    # grant, which is why the chart defaults it off. Anything unrecognised is pod-log: the
    # shipped default, and inert rather than wide.
    login_capture_source: str = "pod-log"
    # Which nodes hold the audit log: the control-plane ones, by selector — or by name, in which
    # case no node is ever listed and the nodes/proxy grant is pinned to those names.
    login_capture_audit_node_selector: str = "node-role.kubernetes.io/master="
    login_capture_audit_node_names: tuple[str, ...] = ()
    # Which identity providers a login's username may resolve to (identity_match): empty means
    # every provider configured on oauth.config.openshift.io/cluster, read each cycle. And which
    # identities are not people: patterns matched case-insensitively against the Identity's
    # providerUserName and the decoded suffix of its name — service identities such as an LDAP bind
    # account in `ou=TrustedApplications` produce allows and denies that are not personnel events.
    login_capture_audit_providers: tuple[str, ...] = ()
    login_capture_audit_ignore_identity_patterns: tuple[str, ...] = ("ou=TrustedApplications",)
    # ── THE LOGIN-GATE GROUP ───────────────────────────────────────────────────────────────────────
    # The FULL DN of the group whose membership is required to authenticate at all — the clause the
    # identity provider's search filter carries. Set it, and the dashboard can answer the question the
    # oauth log cannot: whether a person who was refused is a real person outside that group.
    #
    # A DN, not a name, because that is what identifies the group unambiguously and what a synced
    # Group already carries in `openshift.io/ldap.uid`. Matching on the cn would break the moment two
    # branches of a directory both had a `cluster-access` group.
    #
    # EMPTY MEANS DISCOVER IT from the OAuth CR's LDAP identity provider, whose filter names the group.
    # Set it explicitly when the gate lives somewhere that filter does not show, or when the dashboard
    # is not permitted to read the OAuth CR. Discovery is best-effort by design: it is the convenience,
    # and this value is the contract.
    cluster_access_group: str = ""
    """How often to re-read RoleBindings/ClusterRoleBindings — deliberately slower than
    the group poll.

    Bindings change on administrative action, not on a sync schedule, so minute-level
    freshness buys nothing. The cost is not hypothetical: this resource is listed across
    every namespace, and at 100x the measured CRC scale (530 RoleBindings, 236
    ClusterRoleBindings) a refresh is roughly 154 paged API requests. Five minutes cuts
    that by 80% against a 60s poll while staying operationally current.
    """

    request_timeout_seconds: float = 15.0
    """Per-request timeout against a cluster's API server.

    Configurable rather than hardcoded because it is the main lever for not overwhelming
    a busy API server: a slow cluster should time out and degrade to a card, not stall its
    poll thread indefinitely.
    """

    leader_election: bool = True
    """Only the lease holder polls; every replica still serves reads.

    On by default because the cost is one Lease object and the failure it prevents — two
    pollers writing one database — is silent and corrupts accumulated history."""

    leader_lease_name: str = "group-sync-dashboard"

    db_path: str = "gsd.db"
    # SQLite concurrency. Defaults are the tested ones; see Store's docstring for why each
    # exists. sqlite_busy_timeout_ms is the important one — SQLite's own default is 0, which
    # means "raise database-is-locked immediately", with no retry.
    sqlite_busy_timeout_ms: int = 5000
    sqlite_reader_busy_timeout_ms: int = 2000
    sqlite_synchronous: str = "NORMAL"
    sqlite_wal_checkpoint_mb: float = 8.0
    # Backups of the ONLY data in this system that cannot be re-fetched. Empty disables.
    backup_dir: str = ""
    backup_interval_hours: float = 6.0
    backup_keep: int = 4
    # off | log. Discovery only — nothing here writes to a cluster; see
    # docs/unmanaged-audit-design.md. `log` publishes each finding to the pod log, `off`
    # silences the log while the RBAC policy tab and the API still show them. There was an
    # `annotate` mode that labelled findings; it is gone, and a config still asking for it
    # is downgraded to `log` below rather than failing to start.
    unmanaged_audit_mode: str = "off"
    unmanaged_audit_max_per_cycle: int = 20
    # The group-count cliff alert (docs/specs/SPEC_B4_group_count_cliff.md).
    # ON by default: read-only, no RBAC beyond the Group list the poll already makes, one
    # indexed query per cluster per read. The floor is what keeps ON quiet — below ten
    # members, half is one or two people. Validated in load_settings: a ratio outside (0, 1],
    # a floor below 1 or a non-positive window refuses to start, because an alert that can
    # never or always fire is a misconfiguration rather than a preference.
    group_count_cliff_enabled: bool = True
    group_count_cliff_min_members: int = 10
    group_count_cliff_drop_ratio: float = 0.5
    group_count_cliff_window_hours: float = 24.0
    # Exact names or fnmatch globs. A match is reported as silenced, never dropped.
    group_count_cliff_silence: tuple[str, ...] = ()
    # The KPI page's thresholds (#157): the amber mark on each system meter, as percentages. Every
    # threshold is configuration, and the tile states the rule that produced its colour.
    kpi_memory_warn_percent: float = 80.0
    kpi_cpu_warn_percent: float = 80.0
    kpi_throttled_warn_percent: float = 1.0
    kpi_disk_warn_percent: float = 80.0
    # The doors out of the KPI page (#157). Grafana is optional and operator-owned — OpenShift removed
    # its bundled Grafana in 4.11 — so the link renders only when a URL is set; the console's
    # Observe → Dashboards always ships, at consoleUrl when set.
    grafana_url: str = ""
    grafana_dashboard_uid: str = ""
    # Empty grafana_url means DISCOVERED: the poll thread reads the Route carrying this label
    # selector in the pod's own namespace — the openshift-grafana chart labels its Route with its
    # own name. Empty selector switches discovery off.
    grafana_route_selector: str = ""
    console_url: str = ""

    # Whether the oauth-proxy sidecar is in front of us. The app cannot detect this for
    # itself, and it must not infer it from the presence of X-Forwarded-User — that header
    # is exactly what an unauthenticated caller would supply. Reported by the chart from
    # its own oauthProxy.enabled; false means no identity is trustworthy.
    oauth_proxy_enabled: bool = False

    # The proxy's own URL prefix, reported by the chart from oauthProxy.proxyPrefix. Everything
    # the proxy serves lives under it, and /api/whoami composes the sign-out link from it rather
    # than hardcoding "/oauth" — so a --proxy-prefix override reaches the page instead of leaving
    # it pointing at a path the proxy no longer answers.
    oauth_proxy_prefix: str = "/oauth"

    # The proxy's session cap in seconds, restated from the SAME chart value that renders the
    # sidecar's -cookie-expire flag. RESTATED, never enforced here: the session cookie is
    # HttpOnly and the proxy forwards no session-age header, so the app cannot observe the real
    # expiry and must not pretend to. It exists so a page can warn before the cap rather than
    # discovering it as a failed request.
    session_cookie_expire_seconds: int = 14400

    # Zero, and it stays zero unless somebody deliberately re-enables a flag the chart refuses.
    # Measured on provider=openshift: the proxy's refresh-time revalidation sends the token as a
    # query parameter, the API server answers 403 as system:anonymous, and the session is CLEARED
    # at every interval instead of extended. Reported so a page can tell a sliding session from
    # an absolute one without guessing.
    session_cookie_refresh_seconds: int = 0

    # ── IDLE TIMEOUT (docs/DESIGN_session_and_signout.md, "Idle timeout") ──────────────────────────
    # OFF by default: it signs people out, which is a session policy the platform team chooses.
    # Its OWN keys, never derived from the cookie pair — the cookie does not slide, so an idle
    # window computed from `expire - refresh` is meaningless here (the first lesson recorded there).
    # Seconds internally; the chart speaks in minutes. The page enforces nothing itself: at zero it
    # sends the browser to the proxy's sign_out, and the proxy's absolute cap remains the guarantee
    # for a tab that never gets there.
    session_idle_timeout_enabled: bool = False
    session_idle_timeout_seconds: int = 1800
    session_idle_timeout_warning_seconds: int = 60

    # ── OPTIONAL MODULES ───────────────────────────────────────────────────────────────────────────
    # Each module has its own switch; the default is chosen per module and the values comment
    # says why. CSV/JSON export (docs/DESIGN_export.md) is ON: it runs in the browser over rows
    # the server already served this reader, makes no request and needs no grant. Off removes
    # the control from the filter bar and nothing else changes.
    ui_export_enabled: bool = True

    # ── USERS TAB MODULES (docs/DESIGN_users_tab_logins.md, "Decisions after 0.9.0") ─────────────
    # Identity-provider names the Users tab lists. EMPTY MEANS ALL — a value that is simply empty
    # by default. Applied at READ time, never at the poll, so changing it needs no re-poll and the
    # stored record stays the whole cluster; recorded on the wire as `providers_filter` so the tab
    # can say "showing providers: x, y" instead of quietly listing fewer people.
    users_providers: tuple[str, ...] = ()
    # Whether the poller reads Identity objects for the first-login time. One wire from the chart's
    # rbac.identities, like oauthProxyEnabled: the app cannot see its own RBAC, and trying a read
    # that is refused every poll would put a 403 a minute into the API server's audit log.
    identities_read_enabled: bool = False

    # The Kyverno policy module (#165, #170): read the CEL policy family through the policy reports.
    # Auto-detected per cluster — a cluster serving no report API records "not installed" — so the
    # switch is about the RBAC and the reads, not about whether Kyverno exists. `kyverno_metrics_url`
    # is the reports controller's metrics endpoint the dashboard can reach (in-cluster on the host
    # cluster; empty = the breaker's truncation state is unknown). `kyverno_events_retention_days`
    # bounds the appeared/cleared history like the other event tables.
    kyverno_enabled: bool = True
    # Clusters declared as labelled Secrets in the pod's own namespace, discovered on the binding
    # cadence (SPEC_S1). The registry is the one mutable thing on Settings: the discovery thread
    # replaces its contents, everything else reads. Excluded from equality and repr — it holds the
    # in-memory credentials, and two Settings are the same configuration whatever was discovered.
    cluster_secrets_enabled: bool = True
    # SPEC_S2 C6: the tab's writes (create, rotate, delete). OFF by default — the dashboard is a reader
    # (test_r6_the_api_is_read_only, the chart's only-write-is-the-lease guard): off, no write route is
    # registered and the chart renders no write verb; on, the four routes and the three verbs exist.
    cluster_secrets_writes_enabled: bool = False
    # SPEC_S3 §3.1 / SPEC_S4b: the fleet account and the ADDRESS of its password (never the value —
    # read at connect time through the chart's one-Secret grant), and what saTokenLookup reads on
    # every target. `fleet_password_secret_namespace` empty means the pod's own namespace;
    # `sa_token_lookup_secret_name` empty means `<service account>-token`.
    fleet_account_username: str = ""
    fleet_password_secret_namespace: str = ""
    fleet_password_secret_name: str = "gsd-fleet-account"
    fleet_password_secret_key: str = "password"
    sa_token_lookup_namespace: str = "group-sync-operator"
    sa_token_lookup_service_account: str = "group-sync-dashboard-cluster-poller"
    sa_token_lookup_secret_name: str = ""
    # How many replicas the chart runs (ConfigMap `replicaCount`): the lookup refuses to run above one
    # without an elector, because every replica would log in (SPEC_S4 §6; review of #295, P0-2).
    replica_count: int = 1
    cluster_registry: "ClusterRegistry" = field(default_factory=lambda: _registry(), compare=False, repr=False)
    kyverno_metrics_url: str = ""
    kyverno_events_retention_days: int = 90

    user_activity_enabled: bool = True
    # "self" | "all". Who may read /api/dashboard/activity. Defaults to self, because the
    # response is identifiable personnel data — who was present, when, and how much — and
    # the dashboard's usual "you could read this with oc anyway" argument does not cover it.
    user_activity_visibility: str = "self"
    user_activity_flush_seconds: int = 60
    user_activity_retention_days: int = 400

    # ── RETENTION ON THE ACCUMULATED HISTORY ──────────────────────────────────────────────────────
    # The two tables the backup exists for. 0 keeps a table forever. Pruned by the leader after
    # the cycle's backup and never before one has succeeded in this process's life, 5000 rows per
    # table per cycle (poller.HISTORY_PRUNE_BATCH), so a first prune over years of rows cannot
    # hold the single writer.
    #
    # membership_event keeps FOREVER by default: one row per join or leave, a megabyte a year at
    # reference scale, and it is the answer to "when did this person lose access?" — deleting it
    # is a policy only an operator can set. sync_event keeps two years: one row per observed sync
    # per CR, tens of megabytes a year on a claim that also holds every backup copy, naming CRs
    # and counts and never a person.
    membership_events_retention_days: int = 0
    sync_events_retention_days: int = 730

    # ── PER-USER VISIBILITY ────────────────────────────────────────────────────────────────────────
    # ON by default: with restrictions off, every authenticated reader sees the ServiceAccount's
    # view of the cluster — the full RBAC binding surface and every person's login failures — which
    # a plain user cannot read with oc. `false` restores that wide view as a deliberate choice.
    #
    # The chart wires this as GSD_ENABLE_VIEW_RESTRICTIONS on the Deployment, and the spelling is
    # load-bearing: a misspelt variable is simply never read, and the default here is True, so a
    # typo leaves the control ON rather than silently disabling a security control.
    view_restrictions_enabled: bool = True
    # The SubjectAccessReview separating the wide tier from the self tier, chosen by the operator
    # (chart: visibility.adminSar). Expressed as the check itself, not role names: a name list
    # would miss cluster-reader and every custom role.
    #
    # THE DEFAULT WAS `list groups.user.openshift.io` AND THAT WAS THE WRONG FLOOR. It is the
    # threshold this repository documents as "WRONG — a privilege escalation, proven on the
    # reference cluster" when it was the BEARER path's check (values.yaml, oauthProxy.apiTokenAccess):
    # an account holding only `list groups` answered no to `list clusterrolebindings` and no to
    # `list rolebindings`, yet /bindings/findings handed it 229 bindings including
    # app-ocp-rbac-alpha-cluster-admin-crb. The bearer floor was raised to cluster-wide RBAC read for
    # exactly that reason, and `require_admin_tier` claimed in its own docstring to be "the same
    # floor, applied where it was missing" — while actually posting `list groups`. The claim was the
    # correct decision; only the implementation was one rung lower.
    #
    # RAISING IT COSTS NO ADMITTED PERSONA, which is why it is a default change rather than a
    # breaking one. Measured on the reference cluster, SubjectAccessReview per persona with their
    # real group memberships, both thresholds side by side:
    #
    #   kubeadmin   (cluster-admin)   list groups=true   list clusterrolebindings=true
    #   dana.lee    (cluster-reader)  list groups=true   list clusterrolebindings=true
    #   lateef.o    (ordinary)        list groups=false  list clusterrolebindings=false
    #   jane.smith  (decoy: in a group NAMED ...-cluster-admin, no binding behind it)
    #                                 list groups=false  list clusterrolebindings=false
    #
    # No read check separates cluster-admin from cluster-reader, so both stock roles that should
    # hold the wide tier still do. What changes is the cluster this default was wrong for: one whose
    # custom or aggregated role grants directory read without RBAC read. There, `list groups` handed
    # the whole binding surface — which groups hold which admin role — to an identity entitled only
    # to read the directory, and nothing else re-checked, because -openshift-delegate-urls governs
    # bearer tokens and client certs only and never sees a cookie session.
    #
    # `list rolebindings` would also admit cluster-wide `admin`; `edit`/`view` pass no cluster-scoped
    # list at all. An operator who wants the old, laxer threshold can still set it explicitly.
    visibility_admin_sar_api_group: str = "rbac.authorization.k8s.io"
    visibility_admin_sar_resource: str = "clusterrolebindings"
    # Split out of a "resource/subresource" spelling (e.g. pods/log) at parse time, so the SAR
    # builder never re-parses the string.
    visibility_admin_sar_subresource: str = ""
    visibility_admin_sar_verb: str = "list"
    # Empty means a cluster-scoped check.
    visibility_admin_sar_namespace: str = ""

    # The SECOND, STRICTER threshold, for the Usage tab alone (chart: visibility.usageAdminSar).
    # Usage is dashboard-usage data — who opened this dashboard, on which days — and it lives
    # only in the dashboard's own SQLite, so unlike every other wide view it cannot be reproduced
    # with `oc`. That is why it gets a HIGHER bar than the audit views: cluster-reader (the
    # auditor persona) keeps every wide audit view but must NOT see colleagues' presence records.
    # Measured: no read check separates cluster-admin from cluster-reader, so the default asks a
    # write verb — `update clusterrolebindings` — which the dashboard never performs; a SAR only
    # asks. See docs/SPEC_usage_admin_tier.md.
    visibility_usage_admin_sar_api_group: str = "rbac.authorization.k8s.io"
    visibility_usage_admin_sar_resource: str = "clusterrolebindings"
    visibility_usage_admin_sar_subresource: str = ""
    visibility_usage_admin_sar_verb: str = "update"
    visibility_usage_admin_sar_namespace: str = ""

    # THE CLUSTER-CONFIGURATION TIER — two levels of its own (#230; the operator's ruling of
    # 2026-09-20, "a new tier boss — look at how argocd does it"). Argo CD's RBAC carries a
    # first-class `clusters` resource with `get` and `create/update/delete` actions, granted to
    # roles bound to SSO groups, default-deny. We carry no policy file — every tier here is a
    # SubjectAccessReview against the host cluster, so OpenShift groups and RoleBindings already
    # ARE that mapping — so the tier is a named pair of SAR questions about the very objects this
    # surface exposes, the cluster Secrets themselves:
    #
    #   clusterconfig:view    (Argo `clusters, get`)     — `get secrets` in the dashboard's namespace
    #   clusterconfig:manage  (Argo `clusters, create…`) — `create secrets` in that namespace
    #
    # It reads as what it is: you may SEE cluster credentials if you may read the Secrets that hold
    # them, and CHANGE them if you may create those Secrets. Measured on CRC 2026-09-20: the
    # `cluster-reader` ClusterRole — the deliberate auditor persona, which passes the WIDE tier by
    # design — has ZERO of its 172 rules covering core/`secrets`, and `oc auth can-i {get,list,
    # create,update,delete} secrets` answers `no` for a non-admin; so the auditor fails both levels
    # by construction and a cluster-admin passes both. No borrowed Usage-tab question and no new
    # vocabulary for an operator to learn.
    #
    # Each level is asked SEPARATELY and has its own resolver and cache: `manage` does not imply
    # `view` in code, so a site may grant them apart. An empty namespace here means THE POD'S OWN
    # (the namespace the Secrets live in), not a cluster-scoped check — the opposite of the wide
    # tier's empty, because these questions are namespaced by nature.
    visibility_clusterconfig_view_sar_api_group: str = ""
    visibility_clusterconfig_view_sar_resource: str = "secrets"
    visibility_clusterconfig_view_sar_subresource: str = ""
    visibility_clusterconfig_view_sar_verb: str = "get"
    visibility_clusterconfig_view_sar_namespace: str = ""
    visibility_clusterconfig_manage_sar_api_group: str = ""
    visibility_clusterconfig_manage_sar_resource: str = "secrets"
    visibility_clusterconfig_manage_sar_subresource: str = ""
    visibility_clusterconfig_manage_sar_verb: str = "create"
    visibility_clusterconfig_manage_sar_namespace: str = ""
    # How long a viewer's tier verdict may be reused before it is re-decided.
    #
    # THE WORST-CASE STALENESS WINDOW, stated where the number lives: the SAR evaluates live RBAC,
    # but its verdict is cached for this long, and the viewer's groups are supplied to it from a
    # fresh read taken when the cache misses — never from the poll snapshot, whose interval is
    # tuned for history resolution, not authorization. A user REMOVED from an admin group
    # therefore keeps the wide view for at most this many seconds plus one in-flight page (the
    # fail-open direction); a user ADDED waits the same. An indeterminate answer (SAR error,
    # timeout) is never cached and always yields the self tier.
    #
    # The literal lives in VISIBILITY_TIER_TTL_DEFAULT above, and gsd.kube re-exports it as
    # TIER_TTL_SECONDS, so this number is declared ONCE. It used to be declared here AND in
    # kube.py, and that duplication is what let the knob ship inert: nothing passed the setting
    # to the resolver, the resolver fell back to its own identical 60, and every test that
    # exercised the default agreed with the bug.
    visibility_tier_ttl_seconds: int = VISIBILITY_TIER_TTL_DEFAULT
    # ── REPORTING (docs/specs/SPEC_C3_reporting_microservice.md) ─────────────────────────────────────
    # The report service's Service URL inside the cluster, e.g. https://gsd-report.ns.svc:8443.
    # Empty means the module is off: no ticket endpoint, no snapshot, no usage pull, no tab.
    reporting_url: str = ""
    # The shared token both pods mount: signs tickets here, authenticates the usage pull there.
    reporting_token_file: str = "/etc/gsd/report/token"
    # The CA the report Service's certificate chains to (openshift-service-ca.crt); "" = system trust.
    reporting_ca_file: str = ""
    # Where the leader writes VACUUM INTO copies for the report pod, and how often. Under /data so
    # the report pod's read-only mount of the data claim sees it; never the live gsd.db (§4).
    reporting_snapshot_dir: str = "/data/report"
    reporting_snapshot_interval_seconds: int = 300
    reporting_snapshot_keep: int = 2
    # How long a minted ticket lives. The page re-mints on a 401/403 from the report service.
    reporting_ticket_ttl_seconds: int = 300
    # Whether the poller reads Namespace objects (rbac.namespaces) — lets the namespace report
    # attest ABSENCE. Kept from the first C3 body.
    namespaces_read_enabled: bool = False
    # The Namespace label keys the poll captures per namespace, so the namespace-access report
    # can select on them (docs/DESIGN_reporting_auditors_and_ns_selector.md §3). Bounded — only
    # these keys, never the whole label map; default () is off. Read from the ConfigMap key
    # `namespaceMetadataLabels` (rendered with toJson), the same convention as the audit lists.
    namespace_metadata_labels: tuple[str, ...] = ()
    # Which namespaces are the platform's (#255). Defaults to the rule gsd/home.py ships.
    # PLATFORM-CLASSIFICATION (#255, #353): the settings every consumer reads it from (values.yaml platformNamespaces → clusters.yaml)
    platform_namespaces: PlatformNamespaces = PlatformNamespaces()

    def effective_clusters(self) -> list[ClusterConfig]:
        """The values list with the Secret-sourced clusters merged (SPEC_S1 C2: a Secret shadows a
        values entry of the same name; the host is never replaced)."""
        return self.cluster_registry.merge(list(self.clusters))

    def cluster(self, name: str) -> ClusterConfig | None:
        for c in self.effective_clusters():
            if c.name == name:
                return c
        return None

    def host_cluster(self) -> ClusterConfig | None:
        """The cluster the oauth-proxy authenticates against, `same-as-host`/`inherit` resolve
        against, the Kyverno breaker is scraped from, and the visibility tiers ask their SARs on.

        DECLARED, not inferred (#249): the entry carrying `dashboardController: true`. Falling back
        to the first enabled entry keeps an existing install working, and `controller_is_declared`
        says which happened so the page and the startup log can name it — position was load-bearing
        and invisible, and alphabetising the list moved all four of the things above at once.
        `load_settings` refuses two declared controllers and a declared-but-disabled one, so this
        cannot pick between rivals.
        """
        return (next((c for c in self.clusters if c.enabled and c.dashboard_controller), None)
                or next((c for c in self.clusters if c.enabled), None))

    @property
    def controller_is_declared(self) -> bool:
        """True when an entry carries `dashboardController: true`; False when the host is the first
        enabled entry by fallback. Surfaced so "inferred-from-order" is visible rather than assumed."""
        return any(c.enabled and c.dashboard_controller for c in self.clusters)

    def cluster_policy(self, name: str) -> tuple[str, str]:
        """(visibility, identity) for one cluster id, defaults resolved.

        A cluster the config no longer names is RETIRED (enabled=0 at poll start, #96) and the
        surfacing endpoints skip it before consulting this — so the inherit/same-as-host resolved
        for an unconfigured id here is a defensive default, not the served behaviour it once was
        (a retired cluster no longer appears at all). Retiring keeps the history; not a tier
        decision.
        """
        host = self.host_cluster()
        cluster = self.cluster(name)
        if cluster is None:
            return VISIBILITY_INHERIT, IDENTITY_SAME_AS_HOST
        is_host = host is not None and cluster.name == host.name
        if is_host:
            # identity is forced, not defaulted: the host's viewer is a host identity by
            # construction, and a values file saying otherwise would be describing a control
            # that cannot mean anything.
            return cluster.visibility or VISIBILITY_INHERIT, IDENTITY_SAME_AS_HOST
        return remote_policy(cluster.visibility, cluster.identity)


def _num_setting(raw: dict, env_name: str, yaml_key: str, default, cast):
    """Env wins over the ConfigMap, and a malformed value falls back rather than crashing.

    These tune SQLite locking, so a typo in one is not worth refusing to start over — the
    dashboard running with a default timeout beats the dashboard not running. The log line
    is what makes the fallback discoverable.
    """
    source = os.environ.get(env_name)
    if source is None:
        if yaml_key not in raw:
            return default
        source = raw[yaml_key]
    try:
        return cast(source)
    except (TypeError, ValueError):
        log.warning("%s=%r is not a number; using %r", env_name, source, default)
        return default


def _audit_mode_setting(raw: dict) -> str:
    """Fail SAFE: anything unrecognised means off, never a write mode.

    Same reasoning as the visibility setting — a typo must not be the thing that turns on
    the only code path that patches cluster objects.
    """
    source = os.environ.get("GSD_UNMANAGED_AUDIT_MODE")
    if source is None:
        source = raw.get("unmanagedAuditMode", "off")
    word = str(source).strip().lower()
    if word in ("off", "log"):
        return word
    if word == "annotate":
        # DOWNGRADE to log, deliberately not to `off`. `annotate` labelled the binding objects
        # so they could be selected with `oc get ... -l rbac.ocp.io/unmanaged=true`, and it was
        # removed along with the RBAC grant that enabled it, because Kubernetes refuses a
        # metadata patch on an RBAC object unless the writer already holds everything that
        # object grants — measured, 0 of 4 landed.
        #
        # Falling back to `off` would silently take the FINDINGS away from anyone upgrading
        # with this set, and the findings were always the valuable half. `log` publishes them
        # identically and needs no write access.
        log.warning(
            "unmanagedAuditMode=annotate has been removed — it could never write, because "
            "Kubernetes privilege-escalation prevention refuses the patch. Running in 'log', "
            "which publishes the same findings with no write access. Set mode: log to silence "
            "this."
        )
        return "log"
    log.warning("unmanagedAuditMode=%r is not off/log; using 'off'", source)
    return "off"


# PLATFORM-CLASSIFICATION (#255, #353): values.yaml `platformNamespaces` → the chart's configmap → clusters.yaml → this parse
def _platform_namespaces_setting(raw: dict) -> PlatformNamespaces:
    """`platformNamespaces` from the settings file (#255), or the shipped rule when absent.

    Six keys, refused by name like every other stanza this loader reads — a typo must not be a
    silent no-op that leaves an estate wondering why `-operator` never took effect. `prefixes`,
    `suffixes` and `names` REPLACE the defaults; the `additional_*` three append to them, which is
    the case an estate actually wants: adding the operators it installs without restating a Red Hat
    list that changes between releases.
    """
    source = raw.get("platformNamespaces")
    if source is None:
        return PlatformNamespaces()
    if not isinstance(source, dict):
        raise ConfigError(f"platformNamespaces: expected a mapping, got {source!r}")
    known = {"prefixes", "suffixes", "names", "additionalPrefixes", "additionalSuffixes", "additionalNames"}
    unknown = set(source) - known
    if unknown:
        raise ConfigError(f"platformNamespaces: unknown key(s) {sorted(unknown)}; "
                          f"expected any of {', '.join(sorted(known))}")

    def axis(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        # A LIST IS NEVER SPLIT here either: a namespace name cannot contain a comma, but a
        # comma-separated string is how a hand-written settings file expresses one, and
        # _string_list_setting already draws that line for every other list in this file.
        #
        # It also strips and drops empties, which is why the padded/empty check an earlier version of
        # this function carried was DEAD CODE — it ran after the stripping and could never fire
        # (review of #259, Codex C3). What is worth refusing is the thing the stripping cannot fix:
        values = _string_list_setting(source, key, default)
        for value in values:
            # MATCHING IS LITERAL. Someone writing `team-*` or `oud-?` means a glob, and silence
            # would leave them with a pattern that matches one absurd namespace and no error. The
            # three axes are deliberately not globs (#255) — say so where it is written.
            bad = {c for c in "*?[]" if c in value}
            if bad:
                raise ConfigError(
                    f"platformNamespaces.{key}: {value!r} contains {''.join(sorted(bad))} — matching is "
                    f"literal, not a glob. A prefix, a suffix or a full name; `team-*` is a prefix "
                    f"`team-` on additionalPrefixes.")
        # A repeated pattern is harmless to matching and noise in a diff; collapse it rather than
        # refusing a values file over a duplicated line.
        return tuple(dict.fromkeys(values))

    return PlatformNamespaces(
        prefixes=axis("prefixes", PLATFORM_NAMESPACE_PREFIXES),
        suffixes=axis("suffixes", ()),
        names=frozenset(axis("names", tuple(sorted(PLATFORM_NAMESPACES)))),
        additional_prefixes=axis("additionalPrefixes", ()),
        additional_suffixes=axis("additionalSuffixes", ()),
        additional_names=frozenset(axis("additionalNames", ())),
    )


def _string_list_setting(raw: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """A list of strings from the settings file (the chart renders these keys with `toJson`), or a
    comma-separated string from a hand-written file. A LIST IS NEVER SPLIT: an ignore pattern is a
    DN fragment (`ou=TrustedApplications,dc=example,dc=com`) and OpenShift accepts a provider named
    `a,b`; splitting either on commas turned one pattern into three, and `dc=com` then matched every
    person in the directory. A missing or null key is the default; an explicit empty list or empty
    string is "none"."""
    if key not in raw or raw[key] is None:
        return default
    source = raw[key]
    if isinstance(source, list):
        for item in source:
            if not isinstance(item, str):
                raise ConfigError(f"{key}: every entry must be a string, got {item!r}")
        return tuple(item.strip() for item in source if item.strip())
    if isinstance(source, str):
        return tuple(item.strip() for item in source.split(",") if item.strip())
    raise ConfigError(f"{key}: expected a list of strings or a comma-separated string, got {source!r}")


def _login_capture_source_setting(raw: dict) -> str:
    """pod-log | audit-log. Fail SAFE to pod-log: it is the shipped default and needs nothing
    the audit source needs; a typo must not be what widens the read."""
    source = os.environ.get("GSD_LOGIN_CAPTURE_SOURCE")
    if source is None:
        source = raw.get("loginCaptureSource", "pod-log")
    word = str(source).strip().lower()
    if word in ("pod-log", "audit-log"):
        return word
    log.warning("loginCaptureSource=%r is not pod-log/audit-log; using 'pod-log'", source)
    return "pod-log"


def _visibility_setting(raw: dict) -> str:
    """Fail SAFE on anything unrecognised: an unknown value means self, never all.

    The failure direction is the whole point. A typo here — "All", "everyone", "ture" —
    must not silently widen who can read a personnel dataset, so only the exact string
    "all" opts in.
    """
    source = os.environ.get("GSD_USER_ACTIVITY_VISIBILITY")
    if source is None:
        source = raw.get("userActivityVisibility", "self")
    word = str(source).strip().lower()
    if word in ("self", "all"):
        return word
    log.warning("userActivityVisibility=%r is not 'self' or 'all'; using 'self'", source)
    return "self"


def _path_setting(raw: dict, env_name: str, yaml_key: str, default: str) -> str:
    """An absolute URL path, trailing slash stripped. Env wins over the ConfigMap.

    Normalised because the value is CONCATENATED — whoami builds "<prefix>/sign_out" — and a
    trailing slash would produce "//sign_out", which the proxy does not serve. A value that is
    not an absolute path falls back rather than emitting a link that cannot work.
    """
    source = os.environ.get(env_name)
    if source is None:
        source = raw.get(yaml_key, default)
    text = str(source).strip().rstrip("/")
    if not text.startswith("/"):
        log.warning("%s=%r is not an absolute path; using %r", env_name, source, default)
        return default
    return text


def _duration_setting(raw: dict, env_name: str, yaml_key: str, default: int) -> int:
    """A Go duration string ("4h", "90m", "1h30m") as whole seconds. Env wins over the ConfigMap.

    Same grammar the proxy's own flag parser accepts, because the chart renders both from one
    value — if this disagreed with the sidecar the page would count against a different number
    than the proxy enforces.

    A malformed value FALLS BACK with a warning rather than raising, matching _num_setting's
    reasoning and for a stronger version of it: the chart already refuses a malformed duration at
    render time, so a bad value here can only come from a hand-written config or an env override,
    and this number is merely RESTATED to the UI rather than enforced. A dashboard that starts and
    reports a slightly wrong cap beats a dashboard that will not start at all.
    """
    source = os.environ.get(env_name)
    if source is None:
        if yaml_key not in raw:
            return default
        source = raw[yaml_key]
    total = 0.0
    text = str(source).strip()
    units = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
    for value, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)(ns|us|µs|ms|s|m|h)", text):
        total += float(value) * units[unit]
    # A non-empty string that matched nothing — "4 hours", "14400", "PT4H" — is malformed. The
    # rebuild check catches a partial match too, where a stray unit would be silently dropped.
    rebuilt = "".join(v + u for v, u in re.findall(r"([0-9]+(?:\.[0-9]+)?)(ns|us|µs|ms|s|m|h)", text))
    if not text or rebuilt != text:
        log.warning("%s=%r is not a Go duration; using %r seconds", env_name, source, default)
        return default
    return int(total)


def _idle_integer_setting(raw: dict, env_name: str, yaml_key: str, default: int) -> int:
    """One whole-number idle setting, checked as TEXT. `_num_setting(..., int)` would coerce a YAML
    boolean (`int(True) == 1`) or float (`int(1.5) == 1`) into a one-minute window while the same
    value from the environment fell back — one key, two answers (review of C4, both reviewers).
    Both forms now fall back to the default with the reason logged."""
    source = os.environ.get(env_name)
    source_name = env_name
    if source is None:
        if yaml_key not in raw:
            return default
        source = raw[yaml_key]
        source_name = yaml_key
    text = str(source).strip()
    if isinstance(source, bool) or re.fullmatch(r"-?[0-9]+", text) is None:
        log.warning("%s=%r is not a whole number; using %r", source_name, source, default)
        return default
    return int(text)


def _idle_timeout_setting(raw: dict, cookie_expire_seconds: int) -> tuple[bool, int, int]:
    """(enabled, seconds, warning_seconds). Env wins over the ConfigMap; a bad number falls back.

    The chart refuses these shapes at render time; this is the second boundary, for a hand-written
    config. Falling back with a WARNING rather than raising, because a wrong warning length is not
    grounds for an outage — but the fallback is always the SHORTER, safer window, never a longer one.
    The one thing that does raise nothing and only warns: an idle window at or beyond the proxy's
    absolute cap can never fire, so the module is inert and the log says so.
    """
    enabled = _bool_setting(raw, "GSD_SESSION_IDLE_TIMEOUT_ENABLED", "sessionIdleTimeoutEnabled", False)
    minutes = _idle_integer_setting(raw, "GSD_SESSION_IDLE_TIMEOUT_MINUTES", "sessionIdleTimeoutMinutes", 30)
    if minutes < 1:
        log.warning("sessionIdleTimeoutMinutes=%r is below 1; using 30", minutes)
        minutes = 30
    seconds = minutes * 60
    warning = _idle_integer_setting(
        raw, "GSD_SESSION_IDLE_TIMEOUT_WARNING_SECONDS", "sessionIdleTimeoutWarningSeconds", 60
    )
    if not 5 <= warning < seconds:
        fallback = min(60, max(5, seconds // 2))
        log.warning(
            "sessionIdleTimeoutWarningSeconds=%r must be at least 5 and shorter than the idle "
            "window (%ds); using %d", warning, seconds, fallback,
        )
        warning = fallback
    # A cap of 0 or below is no cap at all, not a cap the window exceeds (review of C4).
    if enabled and cookie_expire_seconds > 0 and seconds >= cookie_expire_seconds:
        log.warning(
            "the idle timeout (%ds) is not shorter than the proxy's absolute session cap (%ds), so "
            "it can never fire: the cap ends every session first. Lower sessionIdleTimeoutMinutes "
            "or raise oauthProxy.cookie.expire", seconds, cookie_expire_seconds,
        )
    return enabled, seconds, warning


# What each field of a visibility SubjectAccessReview may contain. RBAC matching is exact and
# lowercase, so a miscased or misspelt field would not error — it would answer allowed=false for
# every viewer and silently demote every administrator. The chart refuses these shapes at render
# time; this guards the same line for a hand-written config file. Keyed by the ConfigMap-key
# SUFFIX, so one rule set serves BOTH thresholds (visibilityAdminSar* and visibilityUsageAdminSar*)
# — the operator meets one convention twice rather than two conventions once.
_SAR_FIELD_PATTERNS = {
    "ApiGroup": re.compile(r"[a-z0-9.\-]*"),
    "Resource": re.compile(r"[a-z0-9\-]+(/[a-z0-9\-]+)?"),
    "Verb": re.compile(r"[a-z]+"),
    "Namespace": re.compile(r"[a-z0-9\-]*"),
}

# The wide tier's default: `list clusterrolebindings.rbac.authorization.k8s.io` — cluster-wide RBAC
# read, which is the floor this repository already argued is honest for what /api returns, and the
# floor require_admin_tier's docstring always claimed to apply. See Settings for the measurement
# showing the change admits exactly the same personas among the stock roles.
_ADMIN_SAR_DEFAULTS = {
    "ApiGroup": "rbac.authorization.k8s.io",
    "Resource": "clusterrolebindings",
    "Verb": "list",
    "Namespace": "",
}

# The Usage tab's HIGHER default. Measured on the reference cluster: NO read check separates
# cluster-admin from cluster-reader, because cluster-reader may read everything — so the default
# asks about a WRITE verb, `update clusterrolebindings`, which cluster-admin holds and
# cluster-reader does not. The dashboard still never writes; a SubjectAccessReview only asks
# whether a subject could. See docs/SPEC_usage_admin_tier.md.
_USAGE_ADMIN_SAR_DEFAULTS = {
    "ApiGroup": "rbac.authorization.k8s.io",
    "Resource": "clusterrolebindings",
    "Verb": "update",
    "Namespace": "",
}


def _sar_setting(raw: dict, key_prefix: str, defaults: dict[str, str], default_label: str
                 ) -> tuple[str, str, str, str, str]:
    """One visibility-threshold SubjectAccessReview, taken whole or not at all.

    Fail SAFE, in the right direction: any unusable field falls back to the ENTIRE default check —
    never to "everyone passes" and never to disabling the control. Whole, because half a custom
    check (the operator's resource under the default verb) is a question nobody chose to ask.

    `key_prefix` is the ConfigMap-key stem (visibilityAdminSar / visibilityUsageAdminSar); one
    parser serves both thresholds so they cannot drift. `default_label` names the fallback check in
    the warning. Returns (api_group, resource, subresource, verb, namespace); a resource/subresource
    spelling is split here so the SAR builder never re-parses.
    """
    fields: dict[str, str] = {}
    for suffix, pattern in _SAR_FIELD_PATTERNS.items():
        key = key_prefix + suffix
        value = raw.get(key)
        if value is None:
            # Absent or nil means "not set", which takes the default — matching the chart, where a
            # commented-out sub-key must not change the question.
            fields[suffix] = defaults[suffix]
            continue
        word = str(value).strip()
        if not pattern.fullmatch(word):
            log.warning(
                "%s=%r is not usable in a SubjectAccessReview; using the default check (%s)",
                key, value, default_label,
            )
            fields = dict(defaults)
            break
        fields[suffix] = word
    resource, _, subresource = fields["Resource"].partition("/")
    return (fields["ApiGroup"], resource, subresource, fields["Verb"], fields["Namespace"])


def _visibility_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """The WIDE-view admin threshold (chart: visibility.adminSar)."""
    return _sar_setting(raw, "visibilityAdminSar", _ADMIN_SAR_DEFAULTS,
                        "list clusterrolebindings.rbac.authorization.k8s.io")


def _usage_visibility_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """The stricter USAGE-tab threshold (chart: visibility.usageAdminSar). Separate default, same
    fail-safe discipline — see _USAGE_ADMIN_SAR_DEFAULTS for why it is a write verb."""
    return _sar_setting(raw, "visibilityUsageAdminSar", _USAGE_ADMIN_SAR_DEFAULTS,
                        "update clusterrolebindings.rbac.authorization.k8s.io")


_CLUSTERCONFIG_VIEW_SAR_DEFAULTS = {
    "ApiGroup": "",
    "Resource": "secrets",
    "Verb": "get",
    "Namespace": "",
}

_CLUSTERCONFIG_MANAGE_SAR_DEFAULTS = dict(_CLUSTERCONFIG_VIEW_SAR_DEFAULTS, Verb="create")


def _clusterconfig_view_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """`clusterconfig:view` (chart: visibility.clusterConfigViewSar) — Argo's `clusters, get`.
    See Settings for the measurement behind the default."""
    return _sar_setting(raw, "visibilityClusterConfigViewSar", _CLUSTERCONFIG_VIEW_SAR_DEFAULTS,
                        "get secrets")


def _clusterconfig_manage_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """`clusterconfig:manage` (chart: visibility.clusterConfigManageSar) — Argo's `clusters,
    create/update/delete`. Its own setting, never derived from the view one: a site may grant the
    two apart, and one parser serving both would let a custom view question silently move manage."""
    return _sar_setting(raw, "visibilityClusterConfigManageSar", _CLUSTERCONFIG_MANAGE_SAR_DEFAULTS,
                        "create secrets")


def _str_setting(raw: dict, env_name: str, yaml_key: str, default: str) -> str:
    """Env wins over the ConfigMap; an absent or null key is the default. Stripped, never None."""
    source = os.environ.get(env_name)
    if source is None:
        source = raw.get(yaml_key)
    return str(default if source is None else source).strip()


def _bool_setting(raw: dict, env_name: str, yaml_key: str, default: bool) -> bool:
    """Env wins over the ConfigMap. Accepts a real boolean or one of the YAML spellings, and NOTHING
    else, from either source.

    ``bool("false")`` is True, so a plain cast turned an explicit disable into an enable — silently,
    and in the direction that grants rather than withholds; the ConfigMap path did exactly that
    until review of #295 (P1-3), and then a number or a list still decided the switch by truthiness
    (`bool([False])` is True — second pass, R2-4). Anything that is not a boolean or a word is the
    default, and the warning names the source it came from. A null is an absent key.
    """
    source, where = os.environ.get(env_name), env_name
    if source is None:
        if raw.get(yaml_key) is None:
            return default
        source, where = raw[yaml_key], yaml_key
    if isinstance(source, bool):
        return source
    if isinstance(source, str):
        word = source.strip().lower()
        if word in ("true", "yes", "on", "1"):
            return True
        if word in ("false", "no", "off", "0"):
            return False
    log.warning("%s=%r is not a boolean; using %r", where, source, default)
    return default


# An identity provider's name as OpenShift accepts it (`oc explain oauth.spec.identityProviders.name`,
# measured 2026-09-05): "a valid path segment: name cannot equal '.' or '..' or contain '/' or '%' or
# ':'" — and nothing stricter: spaces, commas, upper case and underscores are legal (review of C2: a
# whitespace refusal was rejected as not the API's rule; the settings file carries a LIST so a comma
# travels too). It prefixes every `identities[]` entry as `<provider>:<id>` and this dashboard splits
# on the colon.
_PROVIDER_NAME = re.compile(r"[^:/%]+")


def _providers_setting(raw: dict) -> tuple[str, ...]:
    """usersProviders: a LIST of names in the settings file (the chart renders
    config.users.providers as a YAML flow sequence, so every legal name travels intact), or a
    comma-separated string (GSD_USERS_PROVIDERS, or a hand-written file) — in that form a name
    containing a comma cannot be expressed, which is why the file form is a list. STRICT — a
    malformed name is a startup error, because a name that can never match would silently empty
    the Users tab and read as "nobody has logged in"."""
    source: object = os.environ.get("GSD_USERS_PROVIDERS")
    if source is None:
        source = raw.get("usersProviders", "") or ""
    if isinstance(source, list):
        if not all(isinstance(p, str) for p in source):
            raise ConfigError("usersProviders: every entry must be a string (an identity provider's name)")
        names = tuple(p.strip() for p in source if p.strip())
    else:
        names = tuple(p.strip() for p in str(source).split(",") if p.strip())
    for name in names:
        if name in (".", "..") or not _PROVIDER_NAME.fullmatch(name):
            raise ConfigError(
                f"usersProviders: {name!r} is not an identity-provider name (a path segment: not '.' "
                f"or '..', no ':', '/' or '%') — a name that can never match would list nobody"
            )
    return tuple(dict.fromkeys(names))


def _require(raw: dict, key: str, where: str) -> object:
    if key not in raw:
        raise ConfigError(f"{where}: missing required key {key!r}")
    return raw[key]


def _door_url(value: object, yaml_key: str) -> str:
    """An http(s) base URL the KPI page may append a path and query to — the doors out (#157). A
    `javascript:` or `data:` value would be a live script in an href the page renders; refused at
    load, so a bad value is a failed start rather than a link (review of #157, Codex)."""
    from urllib.parse import urlsplit
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ConfigError(f"{yaml_key} must be an http(s) base URL without query or fragment; got {text!r}")
    return text


def _kpi_settings(raw: dict) -> dict:
    """The KPI page's thresholds and doors (values.yaml `kpi`, `grafana`, `console`)."""
    out = {}
    for key, env, yaml_key, default in (
        ("kpi_memory_warn_percent", "GSD_KPI_MEMORY_WARN_PERCENT", "kpiMemoryWarnPercent", 80.0),
        ("kpi_cpu_warn_percent", "GSD_KPI_CPU_WARN_PERCENT", "kpiCpuWarnPercent", 80.0),
        ("kpi_throttled_warn_percent", "GSD_KPI_THROTTLED_WARN_PERCENT", "kpiThrottledWarnPercent", 1.0),
        ("kpi_disk_warn_percent", "GSD_KPI_DISK_WARN_PERCENT", "kpiDiskWarnPercent", 80.0),
    ):
        value = _num_setting(raw, env, yaml_key, default, float)
        if not 0 < value <= 100:
            raise ConfigError(f"{yaml_key} must be a percentage in (0, 100]; got {value!r}")
        out[key] = value
    out["grafana_url"] = _door_url(os.environ.get("GSD_GRAFANA_URL") or raw.get("grafanaUrl", ""), "grafanaUrl")
    out["grafana_dashboard_uid"] = os.environ.get("GSD_GRAFANA_DASHBOARD_UID") or str(raw.get("grafanaDashboardUid", "") or "")
    out["grafana_route_selector"] = _label_selector(
        os.environ.get("GSD_GRAFANA_ROUTE_SELECTOR") or str(raw.get("grafanaRouteSelector", "") or ""), "grafanaRouteSelector")
    out["console_url"] = _door_url(os.environ.get("GSD_CONSOLE_URL") or raw.get("consoleUrl", ""), "consoleUrl")
    return out


def _label_selector(value: str, key: str) -> str:
    """A Kubernetes equality label selector, `k=v[,k=v]`, or empty. Refused at load like the door
    URLs: the value lands verbatim in a list request's query string, so a stray character would
    make discovery a 400 every cycle rather than a config error at start."""
    value = (value or "").strip()
    if not value:
        return ""
    for pair in value.split(","):
        k, eq, v = pair.strip().partition("=")
        if not eq or not re.fullmatch(r"[A-Za-z0-9./_-]+", k) or not re.fullmatch(r"[A-Za-z0-9._-]*", v):
            raise ConfigError(f"{key} must be a label selector of the form key=value[,key=value]; got {value!r}")
    return value


def _cliff_settings(raw: dict) -> dict:
    """config.alerts.groupCountCliff, validated. Refuses rather than clamps: unlike the
    SQLite knobs, a threshold that cannot fire (ratio > 1) or always fires (ratio <= 0) is
    not a degraded-but-running state, it is an alert lying in one direction."""
    enabled = _bool_setting(raw, "GSD_GROUP_COUNT_CLIFF_ENABLED", "groupCountCliffEnabled", True)
    min_members = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_MIN_MEMBERS", "groupCountCliffMinMembers", 10, int)
    ratio = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_DROP_RATIO", "groupCountCliffDropRatio", 0.5, float)
    window = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_WINDOW_HOURS", "groupCountCliffWindowHours", 24.0, float)
    if not 0 < ratio <= 1:
        raise ConfigError(f"groupCountCliffDropRatio must be in (0, 1]; got {ratio!r}")
    if min_members < 1:
        raise ConfigError(f"groupCountCliffMinMembers must be >= 1; got {min_members!r}")
    if window <= 0:
        raise ConfigError(f"groupCountCliffWindowHours must be > 0; got {window!r}")
    # The window is reconstructed from polls, so a window shorter than one poll interval has
    # no observation at its start and a cliff inside it can vanish before the next poll — or
    # before the PrometheusRule's pending period elapses (found in review, PR #72).
    poll = int(raw.get("pollIntervalSeconds", 60))
    if window * 3600 < poll:
        raise ConfigError(
            f"groupCountCliffWindowHours must cover at least one poll interval; got {window!r}h "
            f"with pollIntervalSeconds={poll!r}"
        )
    source = os.environ.get("GSD_GROUP_COUNT_CLIFF_SILENCE")
    if source is None:
        source = raw.get("groupCountCliffSilence", "")
    if isinstance(source, (list, tuple)):
        patterns = [str(p).strip() for p in source]
    else:
        patterns = [p.strip() for p in str(source or "").split(",")]
    return {
        "group_count_cliff_enabled": enabled,
        "group_count_cliff_min_members": min_members,
        "group_count_cliff_drop_ratio": ratio,
        "group_count_cliff_window_hours": window,
        "group_count_cliff_silence": tuple(p for p in patterns if p),
    }


def _is_host_api(url: str, host: ClusterConfig) -> bool:
    """The controller's DNS aliases or the values host's scheme/host/effective port."""
    from urllib.parse import urlsplit

    def endpoint(value):
        parts = urlsplit(value)
        return (parts.scheme, (parts.hostname or "").lower().rstrip("."),
                parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80))

    declared = endpoint(url)
    return declared[1] in {"kubernetes.default.svc", "kubernetes.default.svc.cluster.local",
                           "kubernetes.default"} or declared == endpoint(host.api_url)


def parse_cluster_entries(entries: list, path: str | Path, *, remote_host: ClusterConfig | None = None) -> list[ClusterConfig]:
    """One values-shaped stanza parser; a runtime ConfigMap supplies its already-known host."""
    known = set(VALUES_CLUSTER_KEYS)

    clusters: list[ClusterConfig] = []
    wheres: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        if remote_host is not None:
            # The same parser, with the runtime feed's no-credential / remote-only boundary.
            if "tokenEnv" in entry or "tokenFile" in entry:
                raise ConfigError(f"{where}: a ConfigMap may not carry a credential reference")
            if entry.get("dashboardController") or entry.get("name") == remote_host.name:
                raise ConfigError(f"{where}: the host is declared only in values")
            if _is_host_api(str(entry.get("apiUrl", "")), remote_host):
                raise ConfigError(f"{where}: the host is declared only in values")
            if entry.get("saTokenLookup") is not True:
                raise ConfigError(f"{where}: a ConfigMap needs saTokenLookup: true")
        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        # SPEC_S3 §4 (S3a): the connection mode, read as a WORD like dashboardController — a quoted
        # "yes" must not become a login. A stanza declaring a mode may omit the credential; one
        # declaring neither keeps today's requirement with today's message; declaring both modes, or
        # a mode beside a credential, is two sources of truth and the operator meant one of them.
        modes = []
        for key in CONNECTION_MODE_KEYS:
            if key in entry:
                if not isinstance(entry[key], bool):
                    raise ConfigError(f"{where}: {name!r}: {key} must be true or false, not {entry[key]!r}")
                if entry[key]:
                    modes.append(key)
        if len(modes) > 1:
            raise ConfigError(f"{where}: {name!r} declares both {' and '.join(modes)} — the two connection "
                              "modes are mutually exclusive; declare one")
        mode = modes[0] if modes else None
        if mode and (entry.get("tokenEnv") or entry.get("tokenFile")):
            supplied = " and ".join(k for k in ("tokenEnv", "tokenFile") if entry.get(k))
            raise ConfigError(f"{where}: {name!r} declares {mode} and also {supplied} — two sources of truth "
                              "for one credential; remove one")
        if not mode and not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")
        bootstrap = entry.get(BOOTSTRAP_KEY)
        if bootstrap is not None:
            if not valid_bootstrap_username(bootstrap):
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} must be a username (letters, digits, "
                                  "'.', '_', '@', '-'; no spaces, colons or slashes) — the value is not repeated "
                                  "here, in case something other than a username was written into it")
            if not mode:
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin "
                                  "configures a login that would never happen — declare the mode, or remove the key")

        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        # A word, not truthiness: `bool("false")` is True, so a quoted `enabled: "false"` — what
        # a templating system emits — enabled the cluster, and since D2 the first ENABLED entry
        # is the authorization host (review of D2, second pass, Codex; measured).
        raw_enabled = entry.get("enabled", True)
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str) and raw_enabled.strip() in ("true", "false"):
            enabled = raw_enabled.strip() == "true"
        else:
            raise ConfigError(f"{where}: enabled must be true or false")
        # Strict, like every other cluster key: a typo here ("self_only", "Hidden") must not
        # silently become the default, in either direction.
        # Blank and whitespace-only are "unset" — the chart's guard tolerates them and renders
        # them through, so refusing them here was a pod that crashed after a green upgrade
        # (review of D2, Codex). Every non-empty word stays strict and case-sensitive.
        visibility = entry.get("visibility")
        if visibility is not None:
            visibility = str(visibility).strip() or None
            if visibility is not None and visibility not in CLUSTER_VISIBILITIES:
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not one of "
                    f"{', '.join(CLUSTER_VISIBILITIES)}"
                )
        identity = entry.get("identity")
        if identity is not None:
            identity = str(identity).strip() or None
            if identity is not None and identity not in CLUSTER_IDENTITIES:
                raise ConfigError(
                    f"{where}: identity {identity!r} is not one of {', '.join(CLUSTER_IDENTITIES)}"
                )
        controller = entry.get("dashboardController", False)
        if not isinstance(controller, bool):
            raise ConfigError(f"{where}: dashboardController must be true or false, not {controller!r}")
        if controller and not enabled:
            raise ConfigError(f"{where}: {name!r} is the dashboardController but enabled is false — "
                              "the controller is this pod's own cluster and cannot be disabled")

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=enabled,
                visibility=visibility,
                identity=identity,
                dashboard_controller=controller,
                sa_token_lookup=mode == "saTokenLookup",
                user_self_login=mode == "userSelfLogin",
                ldap_connection_bootstrap=bootstrap,
            )
        )
        wheres.append(where)

    declared = [c.name for c in clusters if c.dashboard_controller]
    if len(declared) > 1:
        raise ConfigError(f"{path}: {len(declared)} clusters declare dashboardController ({', '.join(declared)}) — "
                          "exactly one entry is this pod's own cluster")

    # THE HOST-ONLY VISIBILITY RULES RUN IN A SECOND PASS (review of #251, C1b). They were applied
    # inline against "the first enabled entry", which stopped being the host the moment a LATER entry
    # could declare `dashboardController: true`: measured on that head, `hidden` was accepted on the
    # declared controller — the login cluster, the one thing the rule exists to protect — and refused
    # on a remote. The host is not known until every entry has been read, so the check cannot be.
    host = (next((c for c in clusters if c.enabled and c.dashboard_controller), None)
            or next((c for c in clusters if c.enabled), None))
    host = remote_host or host
    for cluster, where in zip(clusters, wheres):
        if cluster is host:
            how = ("declared by dashboardController" if cluster.dashboard_controller
                   else "the first enabled entry, since none declares dashboardController")
            if cluster.connection_mode is not None:
                # SPEC_S3 §4 rule 4: the controller is this pod's own cluster and authenticates with the
                # mounted ServiceAccount — there is nothing to connect. Checked here, against the cluster
                # that really is the host, so an inferred host is refused the same as a declared one.
                raise ConfigError(
                    f"{where}: {cluster.name!r} is the hosting cluster ({how}) and declares "
                    f"{cluster.connection_mode} — the controller authenticates with the mounted "
                    "ServiceAccount; there is nothing to connect"
                )
            if cluster.visibility in (VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR):
                raise ConfigError(
                    f"{where}: visibility {cluster.visibility!r} is not allowed on the hosting cluster "
                    f"({how}) — it is the cluster the viewer logged in to"
                )
        elif cluster.visibility == VISIBILITY_REMOTE_SAR and cluster.identity == IDENTITY_NONE:
            # Only the EXPLICIT pair (SPEC_D2b §3.2): an omitted identity resolves to same-as-host beside
            # remote-sar, and `identity: none` stated alone resolves to self-only.
            raise ConfigError(
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names the "
                f"reader's OpenShift username on this cluster; set same-as-host or leave identity out"
            )

    return clusters


def load_settings(path: str | Path) -> Settings:
    """Load and validate settings from a YAML file.

    Validation is strict and up-front: a typo in a cluster entry should fail at startup
    with the offending key named, not surface later as a cluster that silently never polls.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {str(path)!r}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    entries = raw.get("clusters") or []
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"{path}: 'clusters' must be a non-empty list")

    clusters = parse_cluster_entries(entries, path)

    admin_sar = _visibility_sar_setting(raw)
    usage_admin_sar = _usage_visibility_sar_setting(raw)
    clusterconfig_view_sar = _clusterconfig_view_sar_setting(raw)
    clusterconfig_manage_sar = _clusterconfig_manage_sar_setting(raw)
    cookie_expire = _duration_setting(raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 14400)
    idle_enabled, idle_seconds, idle_warning = _idle_timeout_setting(raw, cookie_expire)
    if raw.get("reportingUrl") and int(_num_setting(raw, "GSD_REPORTING_SNAPSHOT_INTERVAL_SECONDS", "reportingSnapshotIntervalSeconds", 300, int)) < 60:
        # A VACUUM INTO holds a read transaction for its duration (measured 3.2 s on a 61 MB store);
        # more often than once a minute is a load the poll thread should not carry. The chart refuses
        # the same value at render; this is the second boundary, for a hand-written config.
        raise ConfigError("reportingSnapshotIntervalSeconds must be at least 60")
    if int(raw.get("discoveryIntervalSeconds", 300)) < 1:
        # The discovery thread waits on this alone (Poller._run_discovery); bindingIntervalSeconds has
        # no such guard because the poll loop's max(1.0, ...) paces it (review of #368, Grok C6).
        raise ConfigError("discoveryIntervalSeconds must be at least 1: at 0 the discovery thread's wait returns at once, a busy loop of LISTs against the host API, and the #284 lookup's retry backoff collapses to 0")
    return Settings(
        clusters=clusters,
        poll_interval_seconds=int(raw.get("pollIntervalSeconds", 60)),
        schedule_grace_seconds=int(raw.get("scheduleGraceSeconds", 120)),
        binding_interval_seconds=int(raw.get("bindingIntervalSeconds", 3600)),
        discovery_interval_seconds=int(raw.get("discoveryIntervalSeconds", 300)),
        login_capture_enabled=str(raw.get("loginCaptureEnabled", "false")).lower() == "true",
        login_capture_namespace=raw.get("loginCaptureNamespace") or "openshift-authentication",
        login_capture_htpasswd_providers=tuple(
            p.strip() for p in str(raw.get("loginCaptureHtpasswdProviders", "developer")).split(",")
            if p.strip()
        ),
        login_retention_days=int(raw.get("loginRetentionDays", 400)),
        login_capture_source=_login_capture_source_setting(raw),
        login_capture_audit_node_selector=str(
            raw.get("loginCaptureAuditNodeSelector") or "node-role.kubernetes.io/master="
        ).strip(),
        login_capture_audit_node_names=_string_list_setting(raw, "loginCaptureAuditNodeNames", ()),
        login_capture_audit_providers=_string_list_setting(raw, "loginCaptureAuditProviders", ()),
        login_capture_audit_ignore_identity_patterns=_string_list_setting(
            raw, "loginCaptureAuditIgnoreIdentityPatterns", ("ou=TrustedApplications",)),
        # Stripped, because a DN pasted out of `ldapsearch` output arrives with trailing whitespace
        # often enough to matter, and it is compared for exact equality against a Group's ldap.uid.
        cluster_access_group=str(raw.get("clusterAccessGroup", "") or "").strip(),
        request_timeout_seconds=float(raw.get("requestTimeoutSeconds", 15.0)),
        # GSD_DB_PATH wins over the file so the config can ship as a ConfigMap that does
        # not need to know where the writable volume is mounted.
        leader_election=bool(raw.get("leaderElection", True)),
        leader_lease_name=str(raw.get("leaderLeaseName", "group-sync-dashboard")),
        db_path=os.environ.get("GSD_DB_PATH") or str(raw.get("dbPath", "gsd.db")),
        sqlite_busy_timeout_ms=_num_setting(
            raw, "GSD_SQLITE_BUSY_TIMEOUT_MS", "sqliteBusyTimeoutMs", 5000, int
        ),
        sqlite_reader_busy_timeout_ms=_num_setting(
            raw, "GSD_SQLITE_READER_BUSY_TIMEOUT_MS", "sqliteReaderBusyTimeoutMs", 2000, int
        ),
        sqlite_synchronous=os.environ.get("GSD_SQLITE_SYNCHRONOUS")
        or str(raw.get("sqliteSynchronous", "NORMAL")),
        backup_dir=os.environ.get("GSD_BACKUP_DIR") or str(raw.get("backupDir", "")),
        backup_interval_hours=_num_setting(
            raw, "GSD_BACKUP_INTERVAL_HOURS", "backupIntervalHours", 6.0, float
        ),
        backup_keep=_num_setting(raw, "GSD_BACKUP_KEEP", "backupKeep", 4, int),
        unmanaged_audit_mode=_audit_mode_setting(raw),
        unmanaged_audit_max_per_cycle=_num_setting(
            raw, "GSD_UNMANAGED_AUDIT_MAX_PER_CYCLE", "unmanagedAuditMaxPerCycle", 20, int
        ),
        **_cliff_settings(raw),
        **_kpi_settings(raw),
        sqlite_wal_checkpoint_mb=_num_setting(
            raw, "GSD_SQLITE_WAL_CHECKPOINT_MB", "sqliteWalCheckpointMb", 8.0, float
        ),
        oauth_proxy_enabled=_bool_setting(
            raw, "GSD_OAUTH_PROXY_ENABLED", "oauthProxyEnabled", False
        ),
        oauth_proxy_prefix=_path_setting(
            raw, "GSD_OAUTH_PROXY_PREFIX", "oauthProxyPrefix", "/oauth"
        ),
        session_cookie_expire_seconds=cookie_expire,
        session_idle_timeout_enabled=idle_enabled,
        session_idle_timeout_seconds=idle_seconds,
        session_idle_timeout_warning_seconds=idle_warning,
        session_cookie_refresh_seconds=_duration_setting(
            raw, "GSD_SESSION_COOKIE_REFRESH", "sessionCookieRefresh", 0
        ),
        user_activity_enabled=_bool_setting(
            raw, "GSD_USER_ACTIVITY_ENABLED", "userActivityEnabled", True
        ),
        ui_export_enabled=_bool_setting(raw, "GSD_UI_EXPORT_ENABLED", "uiExportEnabled", True),
        users_providers=_providers_setting(raw),
        identities_read_enabled=_bool_setting(
            raw, "GSD_IDENTITIES_READ_ENABLED", "identitiesReadEnabled", False
        ),
        view_restrictions_enabled=_bool_setting(
            raw, "GSD_ENABLE_VIEW_RESTRICTIONS", "visibilityEnabled", True
        ),
        visibility_admin_sar_api_group=admin_sar[0],
        visibility_admin_sar_resource=admin_sar[1],
        visibility_admin_sar_subresource=admin_sar[2],
        visibility_admin_sar_verb=admin_sar[3],
        visibility_admin_sar_namespace=admin_sar[4],
        visibility_usage_admin_sar_api_group=usage_admin_sar[0],
        visibility_usage_admin_sar_resource=usage_admin_sar[1],
        visibility_usage_admin_sar_subresource=usage_admin_sar[2],
        visibility_usage_admin_sar_verb=usage_admin_sar[3],
        visibility_usage_admin_sar_namespace=usage_admin_sar[4],
        visibility_clusterconfig_view_sar_api_group=clusterconfig_view_sar[0],
        visibility_clusterconfig_view_sar_resource=clusterconfig_view_sar[1],
        visibility_clusterconfig_view_sar_subresource=clusterconfig_view_sar[2],
        visibility_clusterconfig_view_sar_verb=clusterconfig_view_sar[3],
        visibility_clusterconfig_view_sar_namespace=clusterconfig_view_sar[4],
        visibility_clusterconfig_manage_sar_api_group=clusterconfig_manage_sar[0],
        visibility_clusterconfig_manage_sar_resource=clusterconfig_manage_sar[1],
        visibility_clusterconfig_manage_sar_subresource=clusterconfig_manage_sar[2],
        visibility_clusterconfig_manage_sar_verb=clusterconfig_manage_sar[3],
        visibility_clusterconfig_manage_sar_namespace=clusterconfig_manage_sar[4],
        visibility_tier_ttl_seconds=_num_setting(
            raw, "GSD_VISIBILITY_TIER_TTL_SECONDS", "visibilityTierTtlSeconds",
            VISIBILITY_TIER_TTL_DEFAULT, int
        ),
        reporting_url=(os.environ.get("GSD_REPORTING_URL") or str(raw.get("reportingUrl", "") or "")).rstrip("/"),
        reporting_token_file=_path_setting(raw, "GSD_REPORTING_TOKEN_FILE", "reportingTokenFile", "/etc/gsd/report/token"),
        reporting_ca_file=os.environ.get("GSD_REPORTING_CA_FILE") or str(raw.get("reportingCaFile", "") or ""),
        reporting_snapshot_dir=_path_setting(raw, "GSD_REPORTING_SNAPSHOT_DIR", "reportingSnapshotDir", "/data/report"),
        reporting_snapshot_interval_seconds=_num_setting(raw, "GSD_REPORTING_SNAPSHOT_INTERVAL_SECONDS", "reportingSnapshotIntervalSeconds", 300, int),
        reporting_snapshot_keep=_num_setting(raw, "GSD_REPORTING_SNAPSHOT_KEEP", "reportingSnapshotKeep", 2, int),
        reporting_ticket_ttl_seconds=_num_setting(raw, "GSD_REPORTING_TICKET_TTL_SECONDS", "reportingTicketTtlSeconds", 300, int),
        namespaces_read_enabled=_bool_setting(raw, "GSD_NAMESPACES_READ_ENABLED", "namespacesReadEnabled", False),
        namespace_metadata_labels=_string_list_setting(raw, "namespaceMetadataLabels", ()),
        platform_namespaces=_platform_namespaces_setting(raw),   # PLATFORM-CLASSIFICATION (#255, #353)
        user_activity_visibility=_visibility_setting(raw),
        user_activity_flush_seconds=_num_setting(
            raw, "GSD_USER_ACTIVITY_FLUSH_SECONDS", "userActivityFlushSeconds", 60, int
        ),
        user_activity_retention_days=_num_setting(
            raw, "GSD_USER_ACTIVITY_RETENTION_DAYS", "userActivityRetentionDays", 400, int
        ),
        membership_events_retention_days=_num_setting(
            raw, "GSD_MEMBERSHIP_EVENTS_RETENTION_DAYS", "membershipEventsRetentionDays", 0, int
        ),
        sync_events_retention_days=_num_setting(
            raw, "GSD_SYNC_EVENTS_RETENTION_DAYS", "syncEventsRetentionDays", 730, int
        ),
        kyverno_enabled=_bool_setting(raw, "GSD_KYVERNO_ENABLED", "kyvernoEnabled", True),
        cluster_secrets_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_ENABLED", "clusterSecretsEnabled", True),
        cluster_secrets_writes_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_WRITES_ENABLED", "clusterSecretsWritesEnabled", False),
        fleet_account_username=_str_setting(raw, "GSD_FLEET_ACCOUNT_USERNAME", "fleetAccountUsername", ""),
        fleet_password_secret_namespace=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_NAMESPACE", "fleetPasswordSecretNamespace", ""),
        fleet_password_secret_name=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_NAME", "fleetPasswordSecretName", "gsd-fleet-account"),
        fleet_password_secret_key=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_KEY", "fleetPasswordSecretKey", "password"),
        sa_token_lookup_namespace=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_NAMESPACE", "saTokenLookupSourceNamespace", "group-sync-operator"),
        sa_token_lookup_service_account=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SERVICE_ACCOUNT", "saTokenLookupSourceServiceAccount", "group-sync-dashboard-cluster-poller"),
        sa_token_lookup_secret_name=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SECRET_NAME", "saTokenLookupTokenSecretName", ""),
        replica_count=_num_setting(raw, "GSD_REPLICA_COUNT", "replicaCount", 1, int),
        kyverno_metrics_url=str(os.environ.get("GSD_KYVERNO_METRICS_URL") or raw.get("kyvernoMetricsUrl") or "").strip(),
        kyverno_events_retention_days=_num_setting(
            raw, "GSD_KYVERNO_EVENTS_RETENTION_DAYS", "kyvernoEventsRetentionDays", 90, int
        ),
    )


def _registry():
    from .clusterconfig.registry import ClusterRegistry   # local: clusterconfig imports ClusterConfig from here
    return ClusterRegistry()
