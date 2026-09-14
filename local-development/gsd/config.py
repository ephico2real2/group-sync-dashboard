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

import logging
import os
import re
import ssl
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
# Whether the host's username means the same person on this cluster. A claim about the two
# clusters' identity providers, which this chart cannot check — so it is stated, never assumed.
IDENTITY_SAME_AS_HOST = "same-as-host"
IDENTITY_NONE = "none"
CLUSTER_IDENTITIES = (IDENTITY_SAME_AS_HOST, IDENTITY_NONE)


class ConfigError(Exception):
    """Raised for a malformed or unusable cluster configuration."""


_ca_cache: dict[str, ssl.SSLContext] = {}
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
    148-certificate bundle each time is pure waste. Two details matter:

    * the cache is keyed on the ENV VALUE, not global, so changing the configured paths
      takes effect rather than being masked by a stale entry;
    * a null result is NOT cached. The injected ConfigMap is populated asynchronously, so
      it can legitimately be absent for the first moments of a pod's life; caching that
      absence would mean never picking it up without a restart.
    """
    raw = os.environ.get("GSD_TRUSTED_CA_FILE", "")
    if not raw:
        return None

    cached = _ca_cache.get(raw)
    if cached is not None:
        return cached

    paths = [p for p in (part.strip() for part in raw.split(":")) if p and Path(p).is_file()]
    if not paths:
        return None  # deliberately uncached — see above

    context = ssl.create_default_context()
    for path in paths:
        try:
            context.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError) as exc:
            raise ConfigError(f"cannot load trusted CA bundle {path!r}: {exc}") from exc

    with _ca_cache_lock:
        _ca_cache[raw] = context
    log.info("loaded %d trusted CA bundle(s): %s", len(paths), ", ".join(paths))
    return context


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
    # (its viewer IS a host identity), every other cluster is self-only/none. Resolved there and
    # not here so a hand-built Settings and a chart-rendered one agree on what a second cluster
    # serves by default — the direction that matters is that it never widens.
    visibility: str | None = None
    identity: str | None = None

    def resolve_token(self) -> str:
        """Read the token at the moment it is needed.

        Deliberately re-read rather than cached: a mounted Secret is updated in place when
        the token is rotated, and a long-lived process that cached the value at startup
        would keep presenting the stale one until restarted (PLAN §13 Q1).
        """
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


@dataclass(frozen=True)
class Settings:
    """Process-wide settings."""

    clusters: list[ClusterConfig] = field(default_factory=list)
    poll_interval_seconds: int = 60
    """PLAN §6: 60s, far finer than the fastest schedule seen in practice."""

    schedule_grace_seconds: int = 120
    """Slack added before a CR is called late.

    A sync does not land exactly on its cron minute — 3-14s of scheduler latency was
    measured on CRC — and our own poll adds up to ``poll_interval_seconds`` on top. Without
    this grace, the age of a healthy CR briefly exceeds one interval near the end of every
    cycle and the state flaps to ``late`` on each pass. See state.py.
    """

    binding_interval_seconds: int = 300

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

    def cluster(self, name: str) -> ClusterConfig | None:
        for c in self.clusters:
            if c.name == name:
                return c
        return None

    def host_cluster(self) -> ClusterConfig | None:
        """The cluster the oauth-proxy authenticates against: the FIRST enabled entry, which is
        the one the chart writes for the pod's own cluster (values.yaml `clusters[0]`)."""
        return next((c for c in self.clusters if c.enabled), None)

    def cluster_policy(self, name: str) -> tuple[str, str]:
        """(visibility, identity) for one cluster id, defaults resolved.

        A cluster the store still holds but the config no longer names — removed from values
        after it was polled — resolves to inherit/same-as-host: today's behaviour for its
        stale rows, and not wider than it. Deleting the rows is a data decision, not a tier one.
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
        return (cluster.visibility or VISIBILITY_SELF_ONLY,
                cluster.identity or IDENTITY_NONE)


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


def _bool_setting(raw: dict, env_name: str, yaml_key: str, default: bool) -> bool:
    """Env wins over the ConfigMap. Accepts the YAML spellings, not Python truthiness.

    ``bool("false")`` is True, so a plain cast would turn every explicit disable in an env
    var into an enable — silently, and in the direction that grants rather than withholds.
    """
    source = os.environ.get(env_name)
    if source is None:
        return bool(raw.get(yaml_key, default))
    word = source.strip().lower()
    if word in ("true", "yes", "on", "1"):
        return True
    if word in ("false", "no", "off", "0"):
        return False
    log.warning("%s=%r is not a boolean; using %r", env_name, source, default)
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

    known = {
        "name",
        "apiUrl",
        "tokenEnv",
        "tokenFile",
        "caBundleFile",
        "insecureSkipVerify",
        "enabled",
        "visibility",
        "identity",
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
    host_name: str | None = None
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        if not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")

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
        is_host = enabled and host_name is None
        if is_host:
            host_name = name
            if visibility in (VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR):
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not allowed on the hosting cluster "
                    f"(the first enabled entry) — it is the cluster the viewer logged in to"
                )
        elif visibility == VISIBILITY_REMOTE_SAR and (identity or IDENTITY_NONE) != IDENTITY_SAME_AS_HOST:
            raise ConfigError(
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names "
                f"the host's username on this cluster, which only means something if the two "
                f"clusters share an identity provider"
            )

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
            )
        )

    admin_sar = _visibility_sar_setting(raw)
    usage_admin_sar = _usage_visibility_sar_setting(raw)
    cookie_expire = _duration_setting(raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 14400)
    idle_enabled, idle_seconds, idle_warning = _idle_timeout_setting(raw, cookie_expire)
    if raw.get("reportingUrl") and int(_num_setting(raw, "GSD_REPORTING_SNAPSHOT_INTERVAL_SECONDS", "reportingSnapshotIntervalSeconds", 300, int)) < 60:
        # A VACUUM INTO holds a read transaction for its duration (measured 3.2 s on a 61 MB store);
        # more often than once a minute is a load the poll thread should not carry. The chart refuses
        # the same value at render; this is the second boundary, for a hand-written config.
        raise ConfigError("reportingSnapshotIntervalSeconds must be at least 60")
    return Settings(
        clusters=clusters,
        poll_interval_seconds=int(raw.get("pollIntervalSeconds", 60)),
        schedule_grace_seconds=int(raw.get("scheduleGraceSeconds", 120)),
        binding_interval_seconds=int(raw.get("bindingIntervalSeconds", 300)),
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
    )
