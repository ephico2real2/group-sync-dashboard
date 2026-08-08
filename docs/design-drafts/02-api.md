# Lens 2 — the API and config: session durations, the logout URL, `/signed-out`

Extends `docs/DESIGN_oauth_session_and_logout.md` (verified against the oauth-proxy source; its
findings are taken as given). This lens owns the FastAPI surface and `config.py`. The chart flags,
the cookie-secret length guard and the `accessTokenMaxAgeSeconds` comment are lens 1; the page JS,
the countdown widget and the gating of the 30-second auto-refresh are lens 3. Cross-lens contracts
this design depends on are stated explicitly in §7.

Every snippet below is complete and anchored. The parser snippet was executed against 11 good and
10 bad inputs before being written down (`30m→1800`, `1h30m→5400`, `1.5h→5400`, `90s→90`, `""→0`,
`"0"→0`, `"0s"→0`; rejected: `half an hour`, `30`, `30 m`, `-5m`, `+5m`, `300ms`, `5x30m`, `m30`,
`30mm`, `1h 30m`).

---

## 0. The two constraints everything here answers to

**The session deadline is unobservable.** The cookie is HttpOnly and the proxy forwards no
session-age header, so neither this app nor the browser can read the true expiry. Anything the API
says about the deadline is therefore either (a) a configured fact it can restate truthfully, or
(b) a guess dressed as a fact. This design exposes only (a): the configured durations, which are
true by construction because the ConfigMap renders them from the *same* Helm values that render the
proxy's `-cookie-expire`/`-cookie-refresh` flags. One value, two consumers, no drift possible.

**Every proxied request slides the session.** The proxy re-stamps the cookie on any request whose
session is older than `cookie-refresh`. There is no way to exempt an endpoint: a path in
`skipAuthRegex` bypasses the proxy entirely (unauthenticated, no identity, no data), and every other
path re-stamps. "Authenticated but not session-extending" does not exist in this proxy. So idleness
can only be solved where the requests originate — the browser (lens 3) — and this lens's job is to
hand the browser the numbers it needs and to refuse to add any server-side mechanism that would
pretend otherwise.

---

## 1. `/api/whoami` — carries `logout_url` and the session shape

The existing refusal is preserved verbatim in behaviour and extended in reasoning: when the proxy is
disabled, `X-Forwarded-User` is caller-supplied, so `authenticated` stays false — and `logout_url`
and `session` follow it to `null`, because the page must never offer to end a session that does not
exist, nor render a countdown for an idle timeout nothing enforces. Local development and an
`oauthProxy.enabled=false` install therefore render no logout control and no warning, for free.

`logout_url` is composed from `Settings.oauth_proxy_prefix`, never hardcoded, so a future
`--proxy-prefix` override cannot strand the link (research doc, Finding 1). It points at the PROXY's
sign-out path; where the user lands afterwards is the proxy's `-logout-url` business (the chart's
optional SSO override in lens 1 is deliberately invisible to this endpoint — no coupling).

**File: `local-development/gsd/api.py` — replace the whole `whoami` function.**
Anchor: the `@app.get("/api/whoami")` decorator, immediately after the `healthz` handler.

```python
    @app.get("/api/whoami")
    def whoami(request: Request) -> dict:
        """Who the proxy says this request is. Reflected, never stored by this endpoint.

        `authenticated` is false when the proxy is disabled even if a username is present,
        because in that mode the caller supplied it themselves. `logout_url` and `session`
        are gated on the same judgement, for the same reason: without the proxy there is no
        session to end and no idle timeout anyone enforces, so offering either would be the
        page claiming a security control that does not exist.

        `session` carries the CONFIGURED durations, never a deadline. The session cookie is
        HttpOnly and the proxy forwards no session-age header, so the true expiry is not
        observable from here; these numbers are trustworthy only because the ConfigMap
        renders them from the same chart values as the proxy's own flags. The browser owns
        the countdown model built on them — see static/index.html.

        NEVER POLL THIS ON A TIMER. Requesting it through the proxy re-stamps the session
        cookie like any other request, so a page calling it periodically would hold every
        session open forever — the exact defect the durations exist to fix. It is called on
        human actions only: page load, and the "stay signed in" button.
        """
        user = request.headers.get(USER_HEADER)
        authenticated = bool(user) and settings.oauth_proxy_enabled
        return {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": authenticated,
            # Composed, not hardcoded: tracks a --proxy-prefix override through
            # Settings.oauth_proxy_prefix so the link and the proxy cannot drift apart.
            "logout_url": f"{settings.oauth_proxy_prefix}/sign_out" if authenticated else None,
            "session": (
                {
                    "cookie_expire_seconds": settings.session_cookie_expire_seconds,
                    "cookie_refresh_seconds": settings.session_cookie_refresh_seconds,
                }
                if authenticated
                else None
            ),
        }
```

Response, proxy enabled: `{"user": "alice", "email": "a@x.com", "authenticated": true,
"logout_url": "/oauth/sign_out", "session": {"cookie_expire_seconds": 1800,
"cookie_refresh_seconds": 300}}`. Proxy disabled: `{"user": null, "email": null,
"authenticated": false, "logout_url": null, "session": null}`.

Seconds as integers, not the `"30m"` strings: the one consumer is JavaScript arithmetic
(`deadline = t + expire*1000`), and shipping a string would force a second Go-duration parser to
exist in the page — two parsers of one format is how they diverge.

---

## 2. The config keys, and how a duration travels

Three new keys thread chart → ConfigMap → `Settings`, exactly the `oauthProxyEnabled` route:

| chart value (lens 1) | ConfigMap key | env override | Settings field | default |
|---|---|---|---|---|
| `oauthProxy.proxyPrefix` | `oauthProxyPrefix` | `GSD_OAUTH_PROXY_PREFIX` | `oauth_proxy_prefix` | `/oauth` |
| `oauthProxy.cookie.expire` | `sessionCookieExpire` | `GSD_SESSION_COOKIE_EXPIRE` | `session_cookie_expire_seconds` | `30m` → 1800 |
| `oauthProxy.cookie.refresh` | `sessionCookieRefresh` | `GSD_SESSION_COOKIE_REFRESH` | `session_cookie_refresh_seconds` | `5m` → 300 |

**What the app receives.** The ConfigMap carries the *same Go-duration string* the sidecar flag
receives — `"30m"`, `"1h30m"` — and the app parses it into integer seconds at startup. One spelling,
one Helm value, two consumers; an operator who tunes `oauthProxy.cookie.expire` has, by that single
act, retuned both the proxy and the countdown. The alternative (the chart pre-computing seconds into
the ConfigMap) would also work, but would make a hand-written ConfigMap — which this app explicitly
supports for local development — carry a different format from the values file it mimics.

**Malformed values fail startup, loudly.** This is a deliberate departure from `_num_setting`'s
fall-back-and-log, and the departure is the point: those tune SQLite locking, where running on a
default beats not running; these describe the session the proxy is actually enforcing, and a
silently substituted default would make `/api/whoami` *confidently wrong about a security control* —
the countdown would model a session shape nobody configured. There is also no safety cost to being
strict: the same malformed string crashes the proxy sidecar's own flag parsing, so the pod was never
going to serve traffic — failing the app too makes both containers tell one story. The env-override
path (`GSD_SESSION_COOKIE_EXPIRE`) is the case the proxy cannot catch, and is validated identically.

### 2.1 `config.py` — imports

**File: `local-development/gsd/config.py`.** Anchor: the import block under the module docstring.
Post-change block (one line added, `import re`):

```python
from __future__ import annotations

import logging
import os
import re
import ssl
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml
```

### 2.2 `config.py` — the parser and the two setting helpers

Anchor: insert immediately after the `_bool_setting` function, before `_require`.

```python
# The unit table of Go's time.ParseDuration, which is the grammar of the proxy's
# -cookie-expire and -cookie-refresh flags. Matching it exactly — including sub-second
# units nobody should use here — keeps one invariant: any duration string the sidecar's
# flag parser accepts, this parser accepts, so the pod cannot half-start over format.
# "ms" is listed before "m" because the regex alternation is first-match.
_GO_DURATION_SECONDS = {
    "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
}
_GO_DURATION_TOKEN = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)")


def _parse_proxy_duration(value: object, name: str) -> int:
    """Whole seconds from a Go time.ParseDuration string — the proxy flags' own format.

    The ConfigMap threads the SAME '30m' the sidecar flag receives, so one spelling
    serves both consumers and the two cannot drift. Empty and '0' mean disabled, which
    is what they mean to the proxy ('0 to disable' — its own flag help).

    Malformed values RAISE rather than fall back — deliberately unlike _num_setting.
    Those tune SQLite locking, where running on a default beats not running; these
    describe the session the proxy actually enforces, and a silently substituted
    default would make /api/whoami confidently wrong about a security control. Sign
    prefixes are rejected on purpose: Go accepts '-5m', but a negative session length
    here can only be a mistake worth stopping at install, not modelling.
    """
    word = str(value).strip()
    if word in ("", "0"):
        return 0
    pos, total = 0, 0.0
    for match in _GO_DURATION_TOKEN.finditer(word):
        if match.start() != pos:
            break
        total += float(match.group(1)) * _GO_DURATION_SECONDS[match.group(2)]
        pos = match.end()
    if pos != len(word):
        raise ConfigError(
            f"{name}: {value!r} is not a duration like '30m', '90s' or '1h30m' "
            "(Go time.ParseDuration syntax — the same grammar the oauth-proxy's "
            "-cookie-expire/-cookie-refresh flags parse)"
        )
    if 0 < total < 1:
        raise ConfigError(
            f"{name}: {value!r} is under one second, which a session cookie cannot "
            "express — it can only be a typo for a larger unit"
        )
    return int(round(total))


def _duration_setting(raw: dict, env_name: str, yaml_key: str, default_seconds: int) -> int:
    """Env wins over the ConfigMap, mirroring _bool_setting; parse failures raise.

    The error names whichever source actually carried the bad value, because the fix
    lives where the value was written — an env var points at the Deployment, a yaml
    key at the ConfigMap or values file.
    """
    source = os.environ.get(env_name)
    if source is not None:
        return _parse_proxy_duration(source, env_name)
    if yaml_key not in raw:
        return default_seconds
    return _parse_proxy_duration(raw[yaml_key], yaml_key)


def _proxy_prefix_setting(raw: dict) -> str:
    """The proxy's route prefix, normalised so building paths from it is concatenation.

    Strict, because /api/whoami composes the logout link from this: a malformed prefix
    produces a link that 404s INTO the dashboard — the SPA swallows the path and the
    user believes they signed out when nothing happened. Trailing slashes are stripped
    rather than rejected since '/oauth/' states the same intent as '/oauth'.
    """
    source = os.environ.get("GSD_OAUTH_PROXY_PREFIX")
    if source is None:
        source = raw.get("oauthProxyPrefix", "/oauth")
    word = str(source).strip().rstrip("/")
    if not word.startswith("/") or len(word) < 2:
        raise ConfigError(
            f"oauthProxyPrefix: {source!r} must be an absolute path like '/oauth' "
            "— it is the base of the proxy's own routes (sign_in, sign_out, callback)"
        )
    return word
```

### 2.3 `config.py` — the `Settings` fields

Anchor: the existing comment block beginning `# Whether the oauth-proxy sidecar is in front of us`
and the `oauth_proxy_enabled` field. Post-change block, from that comment through
`user_activity_enabled` (which is unchanged and included only to fix the position):

```python
    # Whether the oauth-proxy sidecar is in front of us. The app cannot detect this for
    # itself, and it must not infer it from the presence of X-Forwarded-User — that header
    # is exactly what an unauthenticated caller would supply. Reported by the chart from
    # its own oauthProxy.enabled; false means no identity is trustworthy.
    oauth_proxy_enabled: bool = False
    # ── THE SESSION AS CONFIGURED, NOT AS OBSERVED ─────────────────────────────────────────────────
    # The proxy's route prefix and cookie lifetimes, restated from the chart so /api/whoami can hand
    # them to the UI. RESTATED is the load-bearing word: the session cookie is HttpOnly and the proxy
    # forwards no session-age header, so the real deadline cannot be observed by anyone — only the
    # configured shape can be reported, and it is trustworthy solely because the ConfigMap renders
    # these from the SAME chart values that render the sidecar's -cookie-expire/-cookie-refresh.
    oauth_proxy_prefix: str = "/oauth"
    # Seconds, parsed at startup from the Go-duration spelling the proxy flags use ("30m"), so the
    # chart states each duration exactly once. Defaults mirror the chart's. refresh == 0 means the
    # proxy never re-stamps the cookie: the session is then an absolute cap from login rather than a
    # sliding idle window, and the UI must model it that way (it cannot see the login time).
    session_cookie_expire_seconds: int = 1800
    session_cookie_refresh_seconds: int = 300
    user_activity_enabled: bool = True
```

### 2.4 `config.py` — `load_settings`, whole post-change function

Two insertions: the validated duration pair before `return Settings(`, and three kwargs after
`oauth_proxy_enabled=...`. Everything else is verbatim today's function.

```python
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
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
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

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=bool(entry.get("enabled", True)),
            )
        )

    # Parsed BEFORE the Settings call so the pair can be validated against each other.
    # expire must be positive — the proxy always has a cookie lifetime, so 0 here could
    # only misdescribe it. refresh >= expire is refused because a cookie is only ever
    # re-stamped by a request arriving more than `refresh` after the last stamp, so that
    # combination means no session can ever slide and the "sliding window" the values
    # comment promises is fiction; upstream oauth2_proxy refuses the same pair at its own
    # startup, and matching that keeps the app and the sidecar rejecting the same configs.
    session_expire = _duration_setting(
        raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 1800
    )
    session_refresh = _duration_setting(
        raw, "GSD_SESSION_COOKIE_REFRESH", "sessionCookieRefresh", 300
    )
    if session_expire <= 0:
        raise ConfigError(
            "sessionCookieExpire: must be a positive duration like '30m' — the proxy "
            "always enforces a cookie lifetime, so zero could only misdescribe it"
        )
    if session_refresh >= session_expire:
        raise ConfigError(
            f"sessionCookieRefresh ({session_refresh}s) must be 0 (disabled) or shorter "
            f"than sessionCookieExpire ({session_expire}s); a session can only slide if "
            "the proxy re-stamps the cookie before it dies"
        )

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
        sqlite_wal_checkpoint_mb=_num_setting(
            raw, "GSD_SQLITE_WAL_CHECKPOINT_MB", "sqliteWalCheckpointMb", 8.0, float
        ),
        oauth_proxy_enabled=_bool_setting(
            raw, "GSD_OAUTH_PROXY_ENABLED", "oauthProxyEnabled", False
        ),
        oauth_proxy_prefix=_proxy_prefix_setting(raw),
        session_cookie_expire_seconds=session_expire,
        session_cookie_refresh_seconds=session_refresh,
        user_activity_enabled=_bool_setting(
            raw, "GSD_USER_ACTIVITY_ENABLED", "userActivityEnabled", True
        ),
        user_activity_visibility=_visibility_setting(raw),
        user_activity_flush_seconds=_num_setting(
            raw, "GSD_USER_ACTIVITY_FLUSH_SECONDS", "userActivityFlushSeconds", 60, int
        ),
        user_activity_retention_days=_num_setting(
            raw, "GSD_USER_ACTIVITY_RETENTION_DAYS", "userActivityRetentionDays", 400, int
        ),
    )
```

### 2.5 `configmap.yaml` — the three data keys

**File: `charts/group-sync-dashboard/templates/configmap.yaml`.** Anchor: the existing
`oauthProxyEnabled` line and the comment above it. Post-change block, from that comment through the
new keys (the `unmanagedAuditMode` line that follows is unchanged):

```yaml
    # The app cannot see its own sidecar, and must not infer authentication from the
    # presence of X-Forwarded-User — that header is precisely what an unauthenticated
    # caller would set. So the chart states it, and the app records identity only when
    # this is true.
    oauthProxyEnabled: {{ .Values.oauthProxy.enabled }}
    # The proxy's route prefix and session shape, restated for /api/whoami. Rendered from
    # the SAME values that build the sidecar's flags in deployment.yaml — that identity is
    # the whole trust argument, because the session cookie is HttpOnly and the durations
    # the UI counts down against can never be observed, only restated from the one place
    # that also set them. The durations stay in the proxy's own Go spelling ("30m") and the
    # app parses them at startup, so an operator states each value exactly once.
    # Quoted unconditionally: a disabled refresh is the empty string, which unquoted would
    # render a bare nothing that YAML reads as null.
    oauthProxyPrefix: {{ .Values.oauthProxy.proxyPrefix | quote }}
    sessionCookieExpire: {{ .Values.oauthProxy.cookie.expire | quote }}
    sessionCookieRefresh: {{ .Values.oauthProxy.cookie.refresh | quote }}
```

(Comments use `#` and describe the expressions in words — no template syntax inside them, since
Helm evaluates `{{ }}` even in YAML comments.)

---

## 3. What the API can — and cannot — truthfully tell the UI

**It exposes durations, not a deadline.** Defence of that choice:

- A deadline requires knowing when the proxy last stamped the cookie. The proxy does not say, the
  cookie cannot be read, and the app never sees the stamp. Any deadline the app computed would be a
  second client of the same blind spots, presented with server authority it has not earned.
- The *browser* is the party that makes the requests that cause stamps, so it is the only party
  that can bound the deadline at all. It knows, on its own clock, the time `t` of the last request
  it sent through the proxy. From the research doc's verified arithmetic (cookie dies at
  `last_save + expire`; a request at `t` finds `last_save ∈ [t − refresh, t]`):

      true deadline ∈ [t + expire − refresh,  t + expire]

  The UI counts down to the LOWER bound. That is the whole drift story, and it has a direction:
  **the model errs early, never late**, by at most `cookie-refresh` (5 minutes on the default
  30-minute window). Wrong-too-early costs an early warning whose "stay signed in" click resolves
  it with one request; wrong-too-late — the silent logout mid-read — is impossible while the page's
  clock runs, because the lower bound is conservative by construction.
- The two residual wrong-late paths, named so lens 3 handles them: (1) a suspended laptop, where
  no clock runs — the deadline must be stored as wall-clock time and recomputed on wake, never
  ticked down by a timer; (2) multiple tabs, where each tab's own `t` is stale relative to the
  sibling that requested more recently — stale in the EARLY direction (the cookie is shared and
  slid by either), so still safe, merely more eager to warn. In every case the backstop is the
  same: an expired session manifests as the proxy answering a fetch with its own sign-in response
  (a redirect/HTML instead of JSON) — the app never sees that request, so no API change can improve
  the signal, and the UI must treat non-JSON as session-over.

**Why the app does not track per-user last-seen itself — and why reusing `activity.py` would be a
category error, not a shortcut.** `gsd/activity.py` exists and records interactions, but every one
of its deliberate design choices is wrong for a session model:

1. **Granularity**: it aggregates per-user-per-UTC-day and buffers up to `flushSeconds` (60s) in
   memory. A countdown needs per-request, sub-second, now.
2. **Identity**: it keys on the user; the session cookie is per *browser*. One user in two browsers
   is two independent sessions and one activity row.
3. **Definition of activity**: it counts only `X-GSD-Interaction`-marked requests — deliberately,
   because counting every request measured tab-open time, not use (722 recorded for ~12 real
   clicks). The proxy re-stamps on *any* proxied request. The two definitions diverge by design,
   and forcing them together would un-fix that measured defect.
4. **Topology**: every replica serves reads (leader election gates only the poller), so an
   in-memory last-seen diverges per replica behind the Service.
5. And after fixing all four, the result would *still* be a model — the proxy's save times remain
   unobservable — just a worse-placed one. The browser's model is strictly better informed.

So `activity.py` is untouched, and the deadline model lives where the information lives.

---

## 4. `/signed-out` — the landing page

Served exactly like `index.html`: a static file (`gsd/static/signed-out.html`) returned by a small
route with the same `Cache-Control`. Not a template — there is nothing to interpolate, and the page
must not personalise itself: it renders for an **unauthenticated** caller at the exact moment the
cookie was cleared, so any header it read would be caller-supplied. Not a bare `StaticFiles` mount —
the route lets it live at a clean top-level path (the proxy's `-logout-url` target and the
`skipAuthRegex` entry) and carry the no-cache header, which a stale post-redeploy copy would need
(a cached page misdescribing what logout does is the same defect class as the stale SPA shell that
`index()`'s comment records).

CSP discipline: no `<style>` block, no inline assets — it links `/static/app.css` and
`/static/favicon.svg` like `index.html`, which is what makes the cross-lens requirement in §7
(admit those two assets in `skipAuthRegex`) load-bearing rather than cosmetic.

### 4.1 `api.py` — `SKIP_AUTH_PATHS`, whole post-change constant

Anchor: the module-level constant under `STATIC_DIR`.

```python
# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded. /signed-out is the proxy's
# -logout-url landing page: it exists precisely for the moment the session cookie has just
# been cleared, so it is unauthenticated by design rather than by oversight.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/signed-out"})
```

### 4.2 `api.py` — the middleware, whole post-change function

Only the path list in the docstring and the "These three" comment change — the enumeration would
otherwise be factually stale. Anchor: `@app.middleware("http")`.

```python
    @app.middleware("http")
    async def record_dashboard_use(request, call_next):
        """Note who made this request, before serving it.

        Only requests the client marked as a human action are counted. The page polls
        itself every 30s and each poll is several API calls, so counting requests measured
        how long a tab had been open rather than whether anyone used the dashboard — one
        real session read 722. See activity.INTERACTION_HEADER.

        The unauthenticated paths (/healthz, /readyz, /metrics, /signed-out —
        oauthProxy.skipAuthRegex) need no special case: they carry neither header.
        """
        # Excluded EXPLICITLY, not by assuming they arrive header-less. These paths
        # bypass the proxy entirely (oauthProxy.skipAuthRegex), so whether they carry an
        # identity header is decided by the caller — which is exactly the input we must not
        # let decide whether we record.
        if request.url.path not in SKIP_AUTH_PATHS and request.headers.get(INTERACTION_HEADER):
            try:
                activity.record(
                    request.headers.get(USER_HEADER), request.headers.get(EMAIL_HEADER)
                )
            except Exception:  # noqa: BLE001
                # Logged with a trace rather than swallowed, but never propagated: failing
                # to note who read a page is not a reason to fail the page.
                log.exception("could not record dashboard use; serving the request anyway")
        return await call_next(request)
```

### 4.3 `api.py` — the route

Anchor: immediately after the `index()` function, before the `if os.path.isdir(STATIC_DIR):` mount.
Stays IN the OpenAPI schema, like `/`; it is classed as infrastructure by the contract test's
explicit list (§6.4), which is that test's documented mechanism for "not an API endpoint a reader
consumes".

```python
    @app.get("/signed-out")
    def signed_out() -> FileResponse:
        # The proxy's -logout-url target, listed in oauthProxy.skipAuthRegex. It renders at
        # the exact moment the session cookie has just been cleared, so it reads no headers
        # and claims nothing about who signed out — anything it said would be
        # caller-supplied. Same Cache-Control reasoning as index(): a stale cached copy
        # after a redeploy would misdescribe what logout actually does, and what this page
        # says logout does NOT do (end the cluster session) is its entire purpose.
        return FileResponse(
            os.path.join(STATIC_DIR, "signed-out.html"),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )
```

### 4.4 The static file — serving contract, and a reference implementation

Lens 3 owns the final markup (themes, type scale, the honest copy). If lens 3 supplies
`signed-out.html`, apply theirs; the contract it must satisfy for this lens's route and tests is:
exists at `local-development/gsd/static/signed-out.html`; no `<style>` block, no scripts required,
no external assets beyond `/static/app.css` and `/static/favicon.svg`; reads no identity; states
plainly that the CLUSTER session is separate and still active (research doc, Finding 2 — the page
must not overclaim). Reference implementation meeting that contract:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
  <title>Signed out — OCP Access Control Dashboard</title>
<link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="signed-out">
<div class="wrap">
  <main id="main">
    <h1>Signed out of the dashboard</h1>
    <p>Your dashboard session has ended.</p>
    <!-- The claim below is the point of this page existing: the proxy clears its own
         cookie and does NOT revoke the OpenShift token or end the OAuth server's session,
         so signing in again may not ask for a password. Saying less would imply a full
         sign-out that did not happen. -->
    <p>Your cluster login is separate and is still active, so signing in again may not ask
       for your password. To end it too, sign out of the OpenShift web console or run
       <code>oc logout</code>.</p>
    <p><a href="/">Sign in again</a></p>
  </main>
</div>
</body>
</html>
```

---

## 5. Keepalive, and what is excluded from the idle model

**No new endpoint.** "Stay signed in" is one user-driven `GET /api/whoami` carrying
`X-GSD-Interaction: 1`. Three reasons, in order of weight:

1. The app has no session to extend — the PROXY extends the cookie, on any proxied request. A
   dedicated `/api/keepalive` would document a capability the app does not have, and every
   authenticated GET is already a keepalive.
2. `whoami`'s response doubles as the truth-probe: JSON with `authenticated: true` confirms the
   session survived; the proxy's sign-in response (non-JSON) instead of it means the session was
   already gone, and the UI switches to its signed-out state rather than pretending the click
   worked. The click both extends and verifies, atomically, in one request.
3. The interaction header is honest here: a human clicked a button. It records as real use, which
   it is — the same standard `activity.py` applies everywhere else.

**Nothing is excluded server-side, because nothing can be.** The full classification, so the
boundary is explicit:

| request | driver | through the proxy? | slides the session? | may run on a timer? |
|---|---|---|---|---|
| data fetches from a click / manual Refresh | human | yes | yes | n/a |
| the 30s auto-refresh (`setInterval`) | timer | yes | **yes — the defect** | only while the user is demonstrably present; gated by lens 3, never by this API |
| "stay signed in" → `GET /api/whoami` + interaction header | human | yes | yes — the purpose | never |
| `whoami` probe when the user returns to a hidden/woken tab | human (a visibilitychange is a user act — they are looking at the tab) | yes | yes, acceptably | never |
| kubelet probes, Prometheus scrapes | infra | no (`skipAuthRegex`) | no | already timed, already harmless |
| `/signed-out` and its two assets | human, post-logout | no (`skipAuthRegex`) | no | n/a |

The trap, stated as a rule: **a path is either proxied (authenticated, session-sliding) or skipped
(unauthenticated, identity-free)** — the proxy offers no third state. Moving the auto-refresh's
endpoints into `skipAuthRegex` to stop them sliding the session would serve group and RBAC data
unauthenticated; adding a server-side "doesn't count" flag would change nothing the proxy does.
The 30-second timer is therefore lens 3's to gate at the source (no request leaves an idle page),
and this lens deliberately adds no API that would blur that: the only automatic requests this
design leaves in the system are the ones that never touch the cookie at all.

---

## 6. Tests

Run from `local-development/` so `gsd` resolves to the worktree:
`…/.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
(baseline 1058 passed, 1 skipped). Every test below fails before the change (new fields absent,
`AttributeError` on new Settings fields, `/signed-out` → 404, malformed durations silently ignored)
and passes after.

### 6.1 `tests/test_config.py` — two new classes

Anchor: append after `TestBothCASources`.

```python
class TestProxyPrefix:
    """The proxy's route prefix, from which /api/whoami composes the logout link. Composed
    rather than hardcoded so a --proxy-prefix override cannot strand the link (a wrong one
    404s INTO the dashboard, which reads as a logout that silently did nothing)."""

    def test_default_is_oauth(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        assert load_settings(write(tmp_path, BASE)).oauth_proxy_prefix == "/oauth"

    def test_configmap_value_is_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        cfg = BASE + "oauthProxyPrefix: /gate\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/gate"

    def test_env_wins_over_the_configmap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_OAUTH_PROXY_PREFIX", "/env-gate")
        cfg = BASE + "oauthProxyPrefix: /file-gate\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/env-gate"

    def test_a_trailing_slash_is_normalised_away(self, tmp_path, monkeypatch):
        """'/oauth/' states the same intent as '/oauth'; the composed sign_out path must
        not end up with a double slash either way."""
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        cfg = BASE + "oauthProxyPrefix: /oauth/\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/oauth"

    def test_a_relative_prefix_fails_at_startup(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        with pytest.raises(ConfigError, match="oauthProxyPrefix"):
            load_settings(write(tmp_path, BASE + "oauthProxyPrefix: oauth\n"))


class TestSessionDurationSettings:
    """The chart carries Go-duration strings ('30m') — one spelling serving both the proxy
    flag and this setting, so the two cannot drift. Malformed values fail startup rather
    than falling back: a silently substituted default would make /api/whoami confidently
    wrong about the security control the proxy is actually enforcing, and the same string
    would crash the sidecar's own flag parsing anyway — failing here keeps the pod's two
    containers telling one story."""

    def _clean(self, monkeypatch):
        monkeypatch.delenv("GSD_SESSION_COOKIE_EXPIRE", raising=False)
        monkeypatch.delenv("GSD_SESSION_COOKIE_REFRESH", raising=False)

    def test_defaults_mirror_the_chart(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        s = load_settings(write(tmp_path, BASE))
        assert s.session_cookie_expire_seconds == 1800
        assert s.session_cookie_refresh_seconds == 300

    def test_go_duration_spellings_parse_to_seconds(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "1h30m"\nsessionCookieRefresh: "90s"\n'
        s = load_settings(write(tmp_path, cfg))
        assert s.session_cookie_expire_seconds == 5400
        assert s.session_cookie_refresh_seconds == 90

    def test_fractional_units_parse_like_go(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "1.5h"\n'
        assert load_settings(write(tmp_path, cfg)).session_cookie_expire_seconds == 5400

    def test_empty_or_zero_refresh_means_disabled(self, tmp_path, monkeypatch):
        """The chart renders '' when refresh is off; '0' is the proxy's own disable
        spelling. Both must arrive as 0, which tells the UI the window is absolute."""
        self._clean(monkeypatch)
        for spelling in ('""', '"0"', '"0s"'):
            cfg = BASE + f"sessionCookieRefresh: {spelling}\n"
            assert load_settings(write(tmp_path, cfg)).session_cookie_refresh_seconds == 0

    def test_a_malformed_duration_fails_at_startup_naming_the_key(self, tmp_path, monkeypatch):
        """Loud, not lenient — the one place a fallback would silently disable the idle
        warning while the proxy enforces something else entirely."""
        self._clean(monkeypatch)
        for bad in ("half an hour", "30", "30 m", "-5m", "300ms", "0"):
            cfg = BASE + f'sessionCookieExpire: "{bad}"\n'
            with pytest.raises(ConfigError, match="sessionCookieExpire"):
                load_settings(write(tmp_path, cfg))

    def test_refresh_must_be_shorter_than_expire(self, tmp_path, monkeypatch):
        """refresh >= expire means the proxy can never re-stamp a cookie before it dies, so
        no session slides and the values comment's promise is fiction. Upstream oauth2_proxy
        refuses the identical combination at its own startup."""
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "30m"\nsessionCookieRefresh: "30m"\n'
        with pytest.raises(ConfigError, match="sessionCookieRefresh"):
            load_settings(write(tmp_path, cfg))

    def test_env_override_wins_and_is_validated_too(self, tmp_path, monkeypatch):
        """The env path is the one the proxy's own flag parsing can never catch."""
        self._clean(monkeypatch)
        monkeypatch.setenv("GSD_SESSION_COOKIE_EXPIRE", "10m")
        cfg = BASE + 'sessionCookieExpire: "45m"\n'
        assert load_settings(write(tmp_path, cfg)).session_cookie_expire_seconds == 600
        monkeypatch.setenv("GSD_SESSION_COOKIE_EXPIRE", "nonsense")
        with pytest.raises(ConfigError, match="GSD_SESSION_COOKIE_EXPIRE"):
            load_settings(write(tmp_path, cfg))
```

### 6.2 New file: `tests/test_session_api.py`

```python
"""The session surface: what /api/whoami tells the UI about ending or keeping a session,
and the unauthenticated /signed-out landing page.

The constraint behind all of it: the session cookie is HttpOnly and the proxy forwards no
session-age header, so no one — not the app, not the browser — can observe the real
deadline. whoami therefore reports the CONFIGURED durations and nothing it cannot know; the
browser builds its countdown model on those, and these tests pin that contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings
from gsd.store import Store


def _client(tmp_path, **settings_kw):
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "gsd.db"), **settings_kw), run_poller=False)
    )


class TestWhoamiSession:
    def test_logout_and_session_are_offered_behind_the_proxy(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["authenticated"] is True
            assert body["logout_url"] == "/oauth/sign_out"
            assert body["session"] == {
                "cookie_expire_seconds": 1800,
                "cookie_refresh_seconds": 300,
            }

    def test_logout_url_follows_the_configured_prefix(self, tmp_path):
        """The proxy's routes hang off --proxy-prefix, so the link is composed from config
        rather than hardcoded — a hardcoded /oauth would 404 into the dashboard the moment
        the prefix changed, which reads as a logout that silently did nothing."""
        with _client(tmp_path, oauth_proxy_enabled=True, oauth_proxy_prefix="/gate") as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["logout_url"] == "/gate/sign_out"

    def test_the_configured_durations_are_the_ones_reported(self, tmp_path):
        """whoami restates config; it must not normalise, clamp or invent."""
        with _client(tmp_path, oauth_proxy_enabled=True,
                     session_cookie_expire_seconds=600,
                     session_cookie_refresh_seconds=60) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
            }

    def test_nothing_is_offered_when_the_proxy_is_off(self, tmp_path):
        """No proxy means no session exists to end and no idle timeout anyone enforces.
        A logout link or a countdown here would claim a control that is not there — and the
        identity beside them would be caller-supplied anyway."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None

    def test_nothing_is_offered_to_an_anonymous_request(self, tmp_path):
        """Proxy on but no identity header — there is no session to describe, so none is."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami").json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None


class TestSignedOutPage:
    def test_served_with_no_headers_at_all(self, tmp_path):
        """The proxy's -logout-url target: reached at the exact moment the session cookie
        was cleared, so it must depend on nothing the proxy would have added."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            r = c.get("/signed-out")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/html")

    def test_served_even_with_the_proxy_off(self, tmp_path):
        """Unreachable in that mode in practice, but it must not 500 on a mode check."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            assert c.get("/signed-out").status_code == 200

    def test_never_cached(self, tmp_path):
        """Same reasoning as index(): a stale copy after a redeploy would misdescribe what
        logout does — and what it does NOT do is this page's entire message."""
        with _client(tmp_path) as c:
            assert "no-cache" in c.get("/signed-out").headers["cache-control"]

    def test_does_not_overclaim_a_cluster_signout(self, tmp_path):
        """Ending the proxy session does not end the cluster session (the proxy's SignOut
        clears its own cookie and revokes nothing). A governance dashboard implying
        otherwise is worse than no logout button."""
        with _client(tmp_path) as c:
            assert "cluster" in c.get("/signed-out").text.lower()

    def test_records_no_activity_even_with_forged_headers(self, tmp_path):
        """It is reachable unauthenticated, so its headers are caller-supplied by
        definition — the same trust boundary as /healthz, enforced by SKIP_AUTH_PATHS."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            c.get("/signed-out", headers={"X-Forwarded-User": "impostor",
                                          "X-GSD-Interaction": "1"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []
```

### 6.3 `tests/test_activity.py` — two existing tests updated

Both assert whoami's exact shape, so they fail the moment the new fields land; that exactness is
worth keeping (it is what catches an accidental extra field), so they are updated rather than
loosened. Whole post-change functions; anchors are their current definitions in
`TestTrustBoundary`.

```python
    def test_identity_is_ignored_when_the_proxy_is_off(self, tmp_path):
        """Without the proxy the app binds 0.0.0.0 with no authentication, so anything in
        X-Forwarded-User is caller-supplied. Recording it would fabricate an audit trail."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body == {"user": None, "email": None, "authenticated": False,
                            "logout_url": None, "session": None}
            # Refused, not merely empty. This used to return an empty list, which is the
            # same answer a legitimately-unused dashboard gives — so it could not be told
            # apart from "there is nothing to see". 403 says why.
            assert c.get("/api/dashboard/activity").status_code == 403
```

```python
    def test_identity_is_honoured_when_the_proxy_is_on(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get(
                "/api/whoami",
                headers={"X-Forwarded-User": "alice", "X-Forwarded-Email": "a@x.com"},
            ).json()
            assert body == {
                "user": "alice", "email": "a@x.com", "authenticated": True,
                "logout_url": "/oauth/sign_out",
                "session": {"cookie_expire_seconds": 1800, "cookie_refresh_seconds": 300},
            }
```

### 6.4 `tests/test_api_contract.py` — one constant

`/signed-out` is infrastructure like `/`, not an API endpoint a reader consumes; the test's own
comment says additions here are a visible decision, which this is. Whole post-change block; anchor:
the `INFRASTRUCTURE` constant.

```python
# Not every path is an endpoint a reader consumes: the SPA shell, the three unauthenticated
# probe paths, and the logout landing page are infrastructure. They are listed rather than
# pattern-matched so that adding one is a visible decision.
INFRASTRUCTURE = {"/", "/healthz", "/readyz", "/metrics", "/signed-out"}
```

---

## 7. Cross-lens contracts (stated so the arbiter can check alignment)

This lens **requires from lens 1 (chart)**:

1. `values.yaml`: `oauthProxy.proxyPrefix: "/oauth"` and `oauthProxy.cookie: {expire: "30m",
   refresh: "5m"}` (the operator's chosen defaults). Names must match §2.5's ConfigMap lines.
2. `deployment.yaml`: the sidecar renders `-proxy-prefix`, `-cookie-expire`, `-cookie-refresh`
   (omitted when refresh is empty) and `-logout-url` **from those same values** — the identity of
   source is the entire trust argument for what whoami reports.
3. `skipAuthRegex` default becomes
   `^/(healthz|readyz|metrics|signed-out|static/(app\.css|favicon\.svg))$`. `/signed-out` because
   it is the logout landing page; the two named assets because the page links them and, behind the
   proxy, its subresource requests would otherwise bounce to the sign-in response and the page
   renders unstyled. Exactly those two — nothing else under `/static/` (the vendored API-docs JS
   stays authenticated); both are pure presentation and carry no data.
4. The cookie-secret length guard (16/24/32 bytes when refresh is on) and the
   `accessTokenMaxAgeSeconds` values-comment are lens 1's findings-fixes; nothing app-side is
   needed for either — the durations threaded here are the same values those guards vet.

This lens **provides to lens 3 (UI)**:

- `whoami.session.{cookie_expire_seconds,cookie_refresh_seconds}` and `whoami.logout_url`,
  present iff `authenticated`.
- The model contract of §3: countdown to `t_last_proxied_request + expire − refresh` on the
  browser's clock; store the deadline as wall-clock, recompute on wake; treat any non-JSON answer
  to a data fetch as session-over; "stay signed in" = one interaction-marked `GET /api/whoami`;
  no timer may fetch a proxied path unconditionally.
- `/signed-out` served as §4; lens 3's markup supersedes §4.4's reference file if both exist.

---

## 8. If the lab test refutes `cookie-refresh` (the go/no-go risk)

The research doc's open risk: `ValidateSessionState` sends the token as a query parameter and the
API server may 401 it, turning every refresh into a forced logout. If the lab confirms that:

**Unchanged in this lens — i.e., none of this work is wasted:** the config keys, the Go-duration
parser, the prefix setting, the whoami shape, `/signed-out`, `SKIP_AUTH_PATHS`, and every test in
§6 except one assertion line. The design is refresh-agnostic by construction: `refresh` is data,
not a branch.

**Changes, all mechanical and named now:**

1. Lens 1 flips the chart default to `refresh: ""` (flag omitted). The ConfigMap then renders
   `sessionCookieRefresh: ""`, which §2.2 already parses to `0` — no code change.
2. The `Settings` dataclass default `session_cookie_refresh_seconds: int = 300` flips to `0`, and
   the one `== 300` assertion in `test_defaults_mirror_the_chart` (§6.1) plus the two whoami
   shape assertions carrying `"cookie_refresh_seconds": 300` (§6.2 first test, §6.3 second test)
   flip with it. Three test lines, one dataclass line.
3. The MEANING of `cookie_refresh_seconds: 0` is already specified (§2.3, §3): the window is
   absolute from login, whose time the browser cannot know — so lens 3's model degrades from
   "countdown to a bounded deadline" to "best-effort warning from page-load time as an upper
   bound, plus robust detection of the dead session via the non-JSON backstop". That degradation
   lives entirely in lens 3's model code; the API contract (`durations, truthfully restated`)
   holds in both worlds, which is precisely why the API exposes durations and not a deadline.
