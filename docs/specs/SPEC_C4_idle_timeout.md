# SPEC C4 — Idle timeout with countdown

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | C — product |
| Release | R5 — Sessions and login source |
| Version on release | app 0.16.0, chart 0.17.0 |
| Issue | [#65](https://github.com/ephico2real2/group-sync-dashboard/issues/65) |
| Status | specified |
| Source | design agent output `a836ef1bc0058551a`; two messages; the first ended inside a ```sh fence and the second began with two fence lines (a closer and a stray duplicate), so one duplicate fence line was dropped |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- First feature of R5: app 0.16.0, chart 0.17.0; the body's version numbers are superseded.

## Batch preamble (verbatim from the design)

# Design: four modules for the OCP Access Tracking Dashboard

Every claim below is grounded in a file read in this session, cited as `path#anchor`. Nothing was written or edited.

## 0. Cross-cutting decisions

### 0.1 The switches and their defaults (operator amendment applied)

| Module | Chart value | ConfigMap key → `Settings` field | Default | Why that default |
|---|---|---|---|---|
| C1 CSV/JSON export | `ui.export.enabled` | `uiExportEnabled` → `ui_export_enabled` | **true** | Client-side, makes no request, needs no grant, exports only rows the server already served this reader. Off keeps files off the page for a platform team that wants that. |
| C4 Idle timeout | `session.idleTimeout.{enabled,minutes,warningSeconds}` | `sessionIdleTimeout{Enabled,Minutes,WarningSeconds}` → `session_idle_timeout_{enabled,seconds,warning_seconds}` | **false** / 30 / 60 | A session policy the platform team chooses; it signs people out. Chart refuses it without the proxy (no session to end) and when it can never fire (idle ≥ `oauthProxy.cookie.expire`). |
| C2a Provider allow-list | `config.users.providers` | `usersProviders` → `users_providers` | **`[]`** (= all) | A value that is simply empty; nothing changes until a name is listed. |
| C2b Exact first login | `rbac.identities` | `identitiesReadEnabled` → `identities_read_enabled` | **false** | Extra RBAC (`get,list identities.user.openshift.io`), which the chart's `rbac.yaml` does not grant today. |
| C3 Namespace report (HTML core) | `features.namespaceReport.enabled` | `namespaceReportEnabled` → `namespace_report_enabled` | **false** | A new administrator-tier surface and a new tab section; a policy choice. Refused without `rbac.bindings`. |
| C3 Absence attestation | `rbac.namespaces` | `namespacesReadEnabled` → `namespaces_read_enabled` | **false** | Extra RBAC (`get,list namespaces`, core group). |
| C3 PDF module | `features.namespaceReport.pdf.{enabled,image.*,variant,resources}` | `namespaceReportPdfUrl` → `namespace_report_pdf_url` | **false** | A second image (WeasyPrint and its C libraries) as a sidecar. Refused without `features.namespaceReport.enabled`. |

Pure-UI flags reach the page the way `timezone` does: `gsd/api.py#version` gains a `features` object read by `index.html` at boot (`data.version`). Session-shaped config reaches the page the way `cookie_expire_seconds` does: inside `session` on `/api/whoami` (`gsd/api.py#whoami`), present only when `authenticated`.

### 0.2 PR order and versions

Current: app `0.11.0` (`local-development/pyproject.toml`, `gsd/__init__.py`), chart `0.10.0` (`Chart.yaml`). Every PR touches `charts/`, so every PR bumps the chart (`.github/workflows/ci.yml` "Chart changes bump the chart version") and moves the app triple together (`tests/test_chart_versions.py`).

| PR | Module | App | Chart | Why this order |
|---|---|---|---|---|
| 1 | C1 export | 0.12.0 | 0.11.0 | Introduces `downloadBlob`, the `features` block on `/api/version`, and the row-selection helpers C3 reuses. |
| 2 | C4 idle timeout | 0.13.0 | 0.12.0 | Independent; touches `whoami` and the poll loop only. |
| 3 | C2 providers + identities | 0.14.0 | 0.13.0 | Migration 8. |
| 4 | C3 namespace report + PDF module | 0.15.0 | 0.14.0 | Migration 9; reuses PR1's helpers; second image `group-sync-dashboard-report:0.15.0`. |

Each PR: bump `pyproject.toml` `version`, `gsd/__init__.py` `__version__`, `Chart.yaml` `version` + `appVersion` + a history comment, a `docs/CHANGELOG.md` section, chart README rows.

### 0.3 Conventions every PR follows

- Config keys parse through `gsd/config.py#_bool_setting` / `_num_setting` (env wins over ConfigMap), strict where a wrong value is a security consequence, fallback-with-warning where it is not — the discipline `_duration_setting`'s docstring states.
- Chart helpers are nil-safe (`default dict` on every hop, never `dig` — `_helpers.tpl#gsd.cookieExpire` explains why) and refuse bad shapes at render time.
- New endpoints: GET, docstring whose first line stands alone (R1), every `Query` described (R2), `total`/`truncated` beside any `limit` (R3), `@consistent` for more than one store call (R5) — `docs/api-contract.md`, enforced by `tests/test_api_contract.py`. Every new path is added to `local-development/API.md` (`test_every_endpoint_appears_in_api_md`).
- Visibility: nothing is exported or reported except what `viewer_scope`/`require_admin_tier` served. C1 exports from `data` (what arrived on the wire for this reader); C3's endpoints sit behind `require_admin_tier` exactly like `/bindings/findings`.
- UI: one file, no build step; colours only via `app.css` tokens (`tests/test_accessibility.py`), sizes only via `--text-*` (`tests/test_type_scale.py`), every control a real `<button>`/`<a>`/`<input>`, ids on anything focus must survive the 60 s repaint (`index.html#function renderFilters` restore-by-id), Playwright tests following `tests/test_ui.py`'s fixtures.

---


## Design (verbatim)

## C4 — Idle timeout with countdown

### Goal and the switch

After `minutes` of no pointer/keyboard/visibility activity, a `role="dialog"` countdown gives the reader `warningSeconds` to continue; at zero the page blanks itself and sends the browser to the proxy's `sign_out`, which clears the session cookie (`docs/DESIGN_session_and_signout.md` §"A dead proxy cookie demands credentials here"). Switch: `session.idleTimeout.enabled` (default **false**), `minutes` (30), `warningSeconds` (60), served inside `session.idle_timeout` on `/api/whoami`.

### The three lessons, applied (`docs/DESIGN_session_and_signout.md` §"Deliberately not implemented")

1. **Own configuration keys.** Never derived from the cookie pair; three keys of their own, rendered beside `sessionCookieExpire` and validated at render (`gsd.idleTimeout*` helpers) and at load (`gsd/config.py#_idle_timeout_setting`).
2. **Enforcement is a server event, not a client timer — so what "enforced" means here.** The app cannot end a proxy session (`gsd/api.py#whoami`: the cookie is HttpOnly, no session-age header). Enforcement is therefore: the page navigates the browser to `logout_url` (the proxy's own `sign_out`, `gsd/api.py#whoami`), and *the proxy* clears the cookie — measured to demand credentials on re-entry. The page does not declare its own session dead on a timer; its "session has ended" panel still comes only from a request that came back as an auth redirect (`index.html#async function api`). What the timer does on its own is remove data from the screen and leave. If the navigation never happens (laptop lid closed, tab discarded), the proxy's absolute cap `-cookie-expire` (`templates/deployment.yaml#-cookie-expire`) still ends the session at 4 h — the guarantee that does not depend on this module. **No `localStorage`, nothing persisted**: all idle state is in-memory, per tab; cross-tab activity travels over a `BroadcastChannel` (ephemeral, per origin), so an idle tab cannot sign out a colleague working in another tab, and a re-login cannot inherit a stale origin — the trap the lesson names.
3. **The poll suspends.** `index.html#const POLL_INTERVAL_MS` ticks through a new `autoRefresh()` that returns while the idle state is not `active` (warning up or expired); the visibility catch-up goes through the same gate. With the shipped absolute cap a request does not slide the session, but a fronting proxy that does slide would otherwise be kept alive by a tab nobody is reading — and a page announcing its own end while re-stamping the cookie is the contradiction lesson 3 names. "Stay signed in" resumes with one interaction-marked `refresh()`, the re-proof `gsd/api.py#whoami` documents, rather than polling whoami.

### Files

#### `local-development/gsd/config.py` — edits

OLD:
```python
    session_cookie_refresh_seconds: int = 0

    user_activity_enabled: bool = True
```
(after the C1 edit this reads with the `ui_export_enabled` block between; apply this edit to the line `session_cookie_refresh_seconds: int = 0` only.)

Insert after `session_cookie_refresh_seconds: int = 0`:
```python

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
```

Insert after `_duration_setting` (before `_SAR_FIELD_PATTERNS`):
```python


def _idle_timeout_setting(raw: dict, cookie_expire_seconds: int) -> tuple[bool, int, int]:
    """(enabled, seconds, warning_seconds). Env wins over the ConfigMap; a bad number falls back.

    The chart refuses these shapes at render time; this is the second boundary, for a hand-written
    config. Falling back with a WARNING rather than raising, because a wrong warning length is not
    grounds for an outage — but the fallback is always the SHORTER, safer window, never a longer one.
    The one thing that does raise nothing and only warns: an idle window at or beyond the proxy's
    absolute cap can never fire, so the module is inert and the log says so.
    """
    enabled = _bool_setting(raw, "GSD_SESSION_IDLE_TIMEOUT_ENABLED", "sessionIdleTimeoutEnabled", False)
    minutes = _num_setting(raw, "GSD_SESSION_IDLE_TIMEOUT_MINUTES", "sessionIdleTimeoutMinutes", 30, int)
    if minutes < 1:
        log.warning("sessionIdleTimeoutMinutes=%r is below 1; using 30", minutes)
        minutes = 30
    seconds = minutes * 60
    warning = _num_setting(
        raw, "GSD_SESSION_IDLE_TIMEOUT_WARNING_SECONDS", "sessionIdleTimeoutWarningSeconds", 60, int
    )
    if not 5 <= warning < seconds:
        fallback = min(60, max(5, seconds // 2))
        log.warning(
            "sessionIdleTimeoutWarningSeconds=%r must be at least 5 and shorter than the idle "
            "window (%ds); using %d", warning, seconds, fallback,
        )
        warning = fallback
    if enabled and seconds >= cookie_expire_seconds:
        log.warning(
            "the idle timeout (%ds) is not shorter than the proxy's absolute session cap (%ds), so "
            "it can never fire: the cap ends every session first. Lower sessionIdleTimeoutMinutes "
            "or raise oauthProxy.cookie.expire", seconds, cookie_expire_seconds,
        )
    return enabled, seconds, warning
```

OLD:
```python
    admin_sar = _visibility_sar_setting(raw)
    usage_admin_sar = _usage_visibility_sar_setting(raw)
    return Settings(
```
NEW:
```python
    admin_sar = _visibility_sar_setting(raw)
    usage_admin_sar = _usage_visibility_sar_setting(raw)
    cookie_expire = _duration_setting(raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 14400)
    idle_enabled, idle_seconds, idle_warning = _idle_timeout_setting(raw, cookie_expire)
    return Settings(
```
OLD:
```python
        session_cookie_expire_seconds=_duration_setting(
            raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 14400
        ),
```
NEW:
```python
        session_cookie_expire_seconds=cookie_expire,
        session_idle_timeout_enabled=idle_enabled,
        session_idle_timeout_seconds=idle_seconds,
        session_idle_timeout_warning_seconds=idle_warning,
```

#### `local-development/gsd/api.py` — edit (`whoami`)

OLD:
```python
            "session": (
                {
                    "cookie_expire_seconds": settings.session_cookie_expire_seconds,
                    "cookie_refresh_seconds": settings.session_cookie_refresh_seconds,
                }
                if authenticated
                else None
            ),
```
NEW:
```python
            "session": (
                {
                    "cookie_expire_seconds": settings.session_cookie_expire_seconds,
                    "cookie_refresh_seconds": settings.session_cookie_refresh_seconds,
                    # The idle-timeout MODEL's inputs, restated like the cap above and enforced
                    # here just as little: the page counts, and at zero sends the browser to
                    # logout_url. Present in both states so an operator can read the module's
                    # state off the wire; the page acts only on `enabled: true`.
                    "idle_timeout": (
                        {
                            "enabled": True,
                            "seconds": settings.session_idle_timeout_seconds,
                            "warning_seconds": settings.session_idle_timeout_warning_seconds,
                        }
                        if settings.session_idle_timeout_enabled
                        else {"enabled": False}
                    ),
                }
                if authenticated
                else None
            ),
```
Also extend the docstring paragraph beginning `` `session` carries the CONFIGURED durations `` with one sentence: ``Its `idle_timeout` is the same kind of thing — inputs to a model the browser runs, never a deadline the server knows.``

#### `charts/group-sync-dashboard/values.yaml` — add after the `ui:` block

```yaml
# ---------------------------------------------------------------------------
# Session idle timeout
# ---------------------------------------------------------------------------
# OFF by default: it signs people out, which is a policy the platform team chooses. When on, the
# page shows a countdown after `minutes` without pointer, keyboard or tab-visibility activity, and
# at zero sends the browser to the proxy's sign_out — the proxy clears the cookie, and re-entry
# demands credentials (measured; docs/DESIGN_session_and_signout.md). Its OWN keys: the cookie does
# not slide, so nothing here is derived from `oauthProxy.cookie.expire`, and that cap remains the
# guarantee for a tab that never reaches sign_out (a closed laptop). Activity in one tab of the
# same browser defers the timeout in every other tab of it, so an idle tab cannot sign out a
# colleague mid-task; nothing is persisted, so a re-login starts a fresh clock. While the countdown
# is on screen the page's own 60 s poll is suspended, so an unattended tab does not keep a session
# alive with its own requests.
#
# Refused at render: enabled without oauthProxy.enabled (no session to end), and an idle window at
# or beyond oauthProxy.cookie.expire (it could never fire).
session:
  idleTimeout:
    enabled: false
    # Whole minutes of inactivity before the countdown starts. At least 1.
    minutes: 30
    # How long the countdown runs. At least 5, and shorter than the idle window.
    warningSeconds: 60

```

#### `charts/group-sync-dashboard/templates/_helpers.tpl` — append

```
# ── Idle timeout ──────────────────────────────────────────────────────────────────────
# Nil-safe like the cookie helpers: commenting out the sub-keys leaves `session:` or
# `idleTimeout:` present-but-nil, which a bare field access panics on. Each value is validated
# where it is resolved, so a values file that could never work fails at `helm template` with the
# rule named, rather than reaching the app's fallback and describing a countdown it is not running.
{{- define "gsd.idleTimeout" -}}
{{- ((.Values.session | default dict).idleTimeout) | default dict -}}
{{- end -}}

{{- define "gsd.idleTimeoutEnabled" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- if eq (toString ($t.enabled | default false)) "true" -}}true{{- else -}}false{{- end -}}
{{- end -}}

{{- define "gsd.idleTimeoutMinutes" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- $m := toString ($t.minutes | default 30) -}}
{{- if not (regexMatch "^[1-9][0-9]*$" $m) -}}
{{- fail (printf "session.idleTimeout.minutes %q is not a whole number of minutes >= 1." $m) -}}
{{- end -}}
{{- $m -}}
{{- end -}}

{{- define "gsd.idleTimeoutWarningSeconds" -}}
{{- $t := include "gsd.idleTimeout" . | fromYaml -}}
{{- $w := toString ($t.warningSeconds | default 60) -}}
{{- if not (regexMatch "^[0-9]+$" $w) -}}
{{- fail (printf "session.idleTimeout.warningSeconds %q is not a whole number of seconds." $w) -}}
{{- end -}}
{{- $m := include "gsd.idleTimeoutMinutes" . | int -}}
{{- if or (lt (int $w) 5) (ge (int $w) (mul $m 60)) -}}
{{- fail (printf "session.idleTimeout.warningSeconds %s must be at least 5 and shorter than the idle window (%d minutes = %d seconds): a countdown longer than the window it warns about is a contradiction the page cannot render." $w $m (mul $m 60)) -}}
{{- end -}}
{{- $w -}}
{{- end -}}
```
(`include … | fromYaml` returns a map; a nil intermediate yields an empty map, which is what the `default` chain needs. A `dict` cannot be returned from `include` directly, hence the round-trip.)

#### `charts/group-sync-dashboard/templates/configmap.yaml` — edit

OLD:
```yaml
    oauthProxyPrefix: {{ .Values.oauthProxy.proxyPrefix | quote }}
    sessionCookieExpire: {{ include "gsd.cookieExpire" . | quote }}
    {{- end }}
```
NEW:
```yaml
    oauthProxyPrefix: {{ .Values.oauthProxy.proxyPrefix | quote }}
    sessionCookieExpire: {{ include "gsd.cookieExpire" . | quote }}
    # The idle timeout's OWN keys (values.yaml `session.idleTimeout`), never derived from the
    # cookie cap, and inside this block because with no proxy there is no session to time out.
    sessionIdleTimeoutEnabled: {{ include "gsd.idleTimeoutEnabled" . }}
    sessionIdleTimeoutMinutes: {{ include "gsd.idleTimeoutMinutes" . }}
    sessionIdleTimeoutWarningSeconds: {{ include "gsd.idleTimeoutWarningSeconds" . }}
    {{- end }}
```

#### `charts/group-sync-dashboard/templates/deployment.yaml` — edit (guards)

OLD:
```
{{- if and (eq (include "gsd.visibilityEnabled" .) "true") (not .Values.oauthProxy.enabled) }}
```
NEW (insert before it):
```
{{- if and (eq (include "gsd.idleTimeoutEnabled" .) "true") (not .Values.oauthProxy.enabled) }}
{{- fail "session.idleTimeout.enabled=true requires oauthProxy.enabled=true. The idle timeout ends a proxy session by sending the browser to the proxy's sign_out; with no proxy there is no session to end and the countdown would be theatre." }}
{{- end }}
{{- if and (eq (include "gsd.idleTimeoutEnabled" .) "true") .Values.oauthProxy.enabled }}
{{- $idle := mul (include "gsd.idleTimeoutMinutes" . | int) 60 }}
{{- $cap := include "gsd.durationSeconds" (include "gsd.cookieExpire" .) }}
{{- if and (ne $cap "-1") (ge $idle (int $cap)) }}
{{- fail (printf "session.idleTimeout.minutes (%d minutes) is not shorter than oauthProxy.cookie.expire (%s = %s seconds), so the idle timeout could never fire: the absolute cap ends every session first. Lower the minutes or raise the cap." (include "gsd.idleTimeoutMinutes" . | int) (include "gsd.cookieExpire" .) $cap) }}
{{- end }}
{{- end }}
{{- if and (eq (include "gsd.visibilityEnabled" .) "true") (not .Values.oauthProxy.enabled) }}
```

#### `local-development/gsd/static/index.html` — edits

Markup. OLD:
```html
<div class="wrap">
  <header class="top">
```
NEW:
```html
<div class="wrap" id="wrap">
  <header class="top">
```
OLD:
```html
  <div class="filters" id="filters"></div>
  <main id="main"></main>
</div>

<script>
```
NEW:
```html
  <div class="filters" id="filters"></div>
  <main id="main"></main>
</div>

<!-- The idle-timeout countdown (docs/DESIGN_session_and_signout.md, "Idle timeout"). Static
     markup outside #main and #filters, so no repaint ever replaces it; hidden until the idle
     model says otherwise, and inert-ing #wrap while open is the focus trap. -->
<div id="idle-modal" class="idle-backdrop" hidden>
  <div class="idle-dialog" role="dialog" aria-modal="true" aria-labelledby="idle-title"
       aria-describedby="idle-desc">
    <h2 id="idle-title">Still there?</h2>
    <p id="idle-desc">Nothing has been touched for a while. So that the access data on this screen
      is not left unattended, this session signs out in
      <strong><span id="idle-countdown">–</span> seconds</strong> unless you continue.
      Press Escape or Enter to stay signed in.</p>
    <p class="sr-only" id="idle-live" aria-live="polite"></p>
    <div class="idle-actions">
      <button type="button" id="idle-stay">Stay signed in</button>
      <a id="idle-signout" class="btn" href="#">Sign out now</a>
    </div>
  </div>
</div>

<script>
```

JS: insert before `/* The session cap this page quotes when it ends.` (i.e. before `let sessionCapNote = "";`):
```js
/* ── Idle timeout: a MODEL the page runs, enforced by the proxy ────────────────────────────
   docs/DESIGN_session_and_signout.md, "Idle timeout". The page cannot observe its session, so
   this counts ACTIVITY — pointer, keyboard, the tab becoming visible — from configured inputs
   that /api/whoami restates. At zero it removes the data from the screen and sends the browser
   to the proxy's sign_out; the PROXY ends the session by clearing its cookie. Nothing here is
   persisted: localStorage outlives a session, so an origin recorded there is routinely older
   than the login it would be counting from (the trap the design records). Tabs of one browser
   share activity over a BroadcastChannel, which is ephemeral, so an idle tab cannot sign out a
   colleague working in another. */
const idle = {
  enabled: false, seconds: 0, warningSeconds: 0, logoutUrl: null,
  lastActivityAt: Date.now(), state: "active", tick: null, channel: null,
  lastBroadcastAt: 0, restoreFocus: null, announced: null,
};
const IDLE_TICK_MS = 1000;
const IDLE_BROADCAST_MIN_MS = 5000;

function idleSuspended() {
  return idle.enabled && idle.state !== "active";
}

/* Activity from THIS tab's listeners or from another tab. While the warning is on screen, local
   activity outside the dialog is ignored — #wrap is inert, so it cannot reach anything anyway, and
   a mouse nudge must not dismiss a dialog the reader has not read. Another tab's activity does
   dismiss it: the person is demonstrably present. */
function idleNoteActivity(fromOtherTab) {
  if (!idle.enabled || idle.state === "expired") return;
  if (idle.state === "warning") {
    if (fromOtherTab) idleStay(false);
    return;
  }
  idle.lastActivityAt = Date.now();
  if (!fromOtherTab) idleBroadcast();
}

function idleBroadcast() {
  if (!idle.channel || Date.now() - idle.lastBroadcastAt < IDLE_BROADCAST_MIN_MS) return;
  idle.lastBroadcastAt = Date.now();
  try { idle.channel.postMessage({ activity: true }); } catch (e) { /* channel closed */ }
}

function startIdleWatch(config, logoutUrl) {
  idle.enabled = true;
  idle.seconds = config.seconds;
  idle.warningSeconds = config.warning_seconds;
  idle.logoutUrl = logoutUrl;
  idle.lastActivityAt = Date.now();
  $("idle-signout").href = logoutUrl;
  const onActivity = () => idleNoteActivity(false);
  for (const ev of ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"]) {
    document.addEventListener(ev, onActivity, { passive: true });
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) idleNoteActivity(false); });
  if (typeof BroadcastChannel === "function") {
    idle.channel = new BroadcastChannel("gsd-idle-activity");
    // The receiver stamps its OWN clock: a sender's timestamp is another tab's clock, and the
    // fact that matters is "someone was active just now", not when they say it was.
    idle.channel.onmessage = () => idleNoteActivity(true);
  }
  wireIdleDialog();
  idle.tick = setInterval(idleTick, IDLE_TICK_MS);
}

function idleTick() {
  if (idle.state === "expired") return;
  const idleFor = (Date.now() - idle.lastActivityAt) / 1000;
  if (idleFor >= idle.seconds) { idleExpire(); return; }
  if (idleFor < idle.seconds - idle.warningSeconds) return;
  if (idle.state !== "warning") idleWarn();
  const left = Math.max(0, Math.ceil(idle.seconds - idleFor));
  $("idle-countdown").textContent = String(left);
  // Announce twice, not every second: a live region that ticks is unusable with a screen reader.
  if ((left === 30 || left === 10) && idle.announced !== left) {
    idle.announced = left;
    $("idle-live").textContent = `${left} seconds until sign-out. Press Escape or Enter to stay signed in.`;
  }
}

function idleWarn() {
  idle.state = "warning";
  idle.announced = null;
  idle.restoreFocus = document.activeElement;
  $("idle-modal").hidden = false;
  // inert: the background is neither focusable nor read by assistive technology while the
  // dialog is up — the focus trap, done by the platform rather than by a keydown shim.
  $("wrap").inert = true;
  $("idle-stay").focus();
}

/* "Stay signed in": the countdown ends, the clock restarts, and — when the reader chose it — one
   interaction-marked refresh re-proves the session the way whoami's docstring prescribes, instead
   of polling whoami. Another tab's activity resets the clock without the extra request. */
function idleStay(reproveSession) {
  idle.state = "active";
  idle.lastActivityAt = Date.now();
  $("idle-modal").hidden = true;
  $("wrap").inert = false;
  $("idle-live").textContent = "";
  const back = idle.restoreFocus;
  idle.restoreFocus = null;
  if (back && typeof back.focus === "function" && document.contains(back)) {
    try { back.focus({ preventScroll: true }); } catch (e) { /* not focusable any more */ }
  }
  if (reproveSession) { idleBroadcast(); refresh(); }
}

/* Zero. The page removes what is on screen FIRST, so a slow or blocked navigation leaves no
   access data behind, then leaves for the proxy's sign_out. It never calls showSessionEnded():
   that panel is reserved for a request that PROVED the session gone. */
function idleExpire() {
  idle.state = "expired";
  clearInterval(idle.tick);
  $("idle-modal").hidden = true;
  $("wrap").inert = false;
  $("logout").hidden = true;
  $("filters").innerHTML = "";
  $("main").innerHTML = `<section class="card">
    <h2>Signed out after inactivity</h2>
    <div class="empty-note">Nothing was touched for ${Math.round(idle.seconds / 60)} minutes, so this
      dashboard is signing you out. Nothing you read before this point was affected.</div>
    <p><a class="btn" href="/">Sign in again</a></p>
  </section>`;
  if (idle.logoutUrl) location.assign(idle.logoutUrl);
}

/* Escape stays (a dialog's Escape closes it); Enter activates the focused control, which is
   "Stay signed in" on open; Tab cycles between the two controls as a backstop to inert. */
function wireIdleDialog() {
  $("idle-stay").onclick = () => idleStay(true);
  $("idle-signout").onclick = () => { idle.state = "expired"; clearInterval(idle.tick); };
  $("idle-modal").onkeydown = (e) => {
    if (e.key === "Escape") { e.preventDefault(); idleStay(true); return; }
    if (e.key !== "Tab") return;
    const items = [$("idle-stay"), $("idle-signout")];
    const i = items.indexOf(document.activeElement);
    e.preventDefault();
    items[(i + (e.shiftKey ? -1 : 1) + items.length) % items.length].focus();
  };
}

```

OLD (in `initSession`):
```js
    if (who && who.logout_url) {
      const link = $("logout");
      link.href = who.logout_url;
      link.hidden = false;
      link.title = who.user ? `Sign out ${who.user}` : "Sign out";
    }
```
NEW:
```js
    if (who && who.logout_url) {
      const link = $("logout");
      link.href = who.logout_url;
      link.hidden = false;
      link.title = who.user ? `Sign out ${who.user}` : "Sign out";
      // The idle model starts only with a session to end AND the module on. Read once, here:
      // its inputs are deployment configuration, and whoami is deliberately never polled.
      const it = who.session && who.session.idle_timeout;
      if (it && it.enabled === true) startIdleWatch(it, who.logout_url);
    }
```

OLD:
```js
const POLL_INTERVAL_MS = 60000;
setInterval(() => {
  if (document.hidden) return;
  refresh({ auto: true });
}, POLL_INTERVAL_MS);
```
NEW:
```js
const POLL_INTERVAL_MS = 60000;
/* The one gate every automatic refresh passes: a hidden tab has no reader, and a tab whose idle
   countdown is on screen (or has expired) must not keep a session alive with its own requests —
   lesson 3 of docs/DESIGN_session_and_signout.md. Resumes with "Stay signed in". */
function autoRefresh() {
  if (document.hidden) return;
  if (idleSuspended()) return;
  refresh({ auto: true });
}
setInterval(autoRefresh, POLL_INTERVAL_MS);
```
OLD:
```js
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  if (Date.now() - lastRefreshStartedAt < POLL_INTERVAL_MS) return;
  refresh({ auto: true });
});
```
NEW:
```js
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  if (Date.now() - lastRefreshStartedAt < POLL_INTERVAL_MS) return;
  autoRefresh();
});
```

#### `local-development/gsd/static/app.css` — append

```css
/* ---- Idle timeout (docs/DESIGN_session_and_signout.md) --------------------------------
   A dialog over a page-toned wash. Tokens only. Under forced-colors the wash is stripped by the
   platform, so the dialog keeps a real border in the system text colour — the one channel that
   survives there. */
.idle-backdrop {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--page) 72%, transparent);
}
.idle-backdrop[hidden] { display: none; }
.idle-dialog {
  background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-left: 4px solid var(--status-warning);
  border-radius: 10px; padding: 18px 20px; max-width: 460px; margin: 16px;
  box-shadow: var(--elev-1);
}
.idle-dialog h2 { margin-bottom: 8px; }
.idle-dialog p { margin: 0 0 12px; font-size: var(--text-base); color: var(--text-secondary); }
.idle-dialog strong { color: var(--text-primary); font-variant-numeric: tabular-nums; }
.idle-actions { display: flex; gap: 10px; flex-wrap: wrap; }
@media (forced-colors: active) {
  .idle-dialog { border: 2px solid CanvasText; }
}
```

### Tests

#### `local-development/tests/test_session_api.py` — edits

OLD:
```python
            assert body["session"] == {
                "cookie_expire_seconds": 14400,
                "cookie_refresh_seconds": 0,
            }

    def test_the_dead_session_exit_follows_the_configured_prefix(self, tmp_path):
```
NEW:
```python
            assert body["session"] == {
                "cookie_expire_seconds": 14400,
                "cookie_refresh_seconds": 0,
                "idle_timeout": {"enabled": False},
            }

    def test_the_idle_timeout_is_restated_when_on_and_never_a_deadline(self, tmp_path):
        """Inputs to the page's model, like the cap: seconds and the warning, no expiry instant."""
        with _client(tmp_path, oauth_proxy_enabled=True, session_idle_timeout_enabled=True,
                     session_idle_timeout_seconds=900, session_idle_timeout_warning_seconds=45) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"]["idle_timeout"] == {
                "enabled": True, "seconds": 900, "warning_seconds": 45}
            assert body["logout_url"] == "/oauth/sign_out", "the URL the countdown ends at"

    def test_the_dead_session_exit_follows_the_configured_prefix(self, tmp_path):
```
OLD:
```python
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
            }
```
NEW:
```python
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
                "idle_timeout": {"enabled": False},
            }
```

#### `local-development/tests/test_config.py` — append

```python
class TestIdleTimeout:
    """Its own keys, never the cookie pair; a bad number falls back to the SHORTER window."""

    def test_off_by_default_with_the_documented_numbers(self, tmp_path, monkeypatch):
        for var in ("GSD_SESSION_IDLE_TIMEOUT_ENABLED", "GSD_SESSION_IDLE_TIMEOUT_MINUTES",
                    "GSD_SESSION_IDLE_TIMEOUT_WARNING_SECONDS"):
            monkeypatch.delenv(var, raising=False)
        s = load_settings(write(tmp_path, BASE))
        assert (s.session_idle_timeout_enabled, s.session_idle_timeout_seconds,
                s.session_idle_timeout_warning_seconds) == (False, 1800, 60)

    def test_the_configmap_keys_are_read_in_minutes_and_served_in_seconds(self, tmp_path):
        cfg = BASE + ("sessionIdleTimeoutEnabled: true\nsessionIdleTimeoutMinutes: 15\n"
                      "sessionIdleTimeoutWarningSeconds: 90\n")
        s = load_settings(write(tmp_path, cfg))
        assert (s.session_idle_timeout_enabled, s.session_idle_timeout_seconds,
                s.session_idle_timeout_warning_seconds) == (True, 900, 90)

    def test_a_warning_longer_than_the_window_falls_back_to_a_shorter_one(self, tmp_path, caplog):
        cfg = BASE + "sessionIdleTimeoutMinutes: 1\nsessionIdleTimeoutWarningSeconds: 120\n"
        s = load_settings(write(tmp_path, cfg))
        assert s.session_idle_timeout_seconds == 60 and s.session_idle_timeout_warning_seconds == 30
        assert "must be at least 5 and shorter" in caplog.text

    def test_zero_minutes_falls_back_to_thirty(self, tmp_path):
        s = load_settings(write(tmp_path, BASE + "sessionIdleTimeoutMinutes: 0\n"))
        assert s.session_idle_timeout_seconds == 1800

    def test_an_idle_window_past_the_cap_is_inert_and_logged(self, tmp_path, caplog):
        cfg = BASE + ("oauthProxyEnabled: true\nsessionCookieExpire: 10m\n"
                      "sessionIdleTimeoutEnabled: true\nsessionIdleTimeoutMinutes: 30\n")
        load_settings(write(tmp_path, cfg))
        assert "can never fire" in caplog.text
```

#### `local-development/tests/test_chart_strategy.py` — append

```python
class TestIdleTimeoutThreading:
    """The three idle keys reach the ConfigMap only with the proxy on, and impossible values are
    refused at render rather than left for the app to fall back from."""

    def test_off_by_default_and_the_keys_still_render_beside_the_cap(self):
        ok, out = render()
        assert ok, out
        cfg = _config_data(out)
        assert cfg["sessionIdleTimeoutEnabled"] is False
        assert cfg["sessionIdleTimeoutMinutes"] == 30 and cfg["sessionIdleTimeoutWarningSeconds"] == 60

    def test_the_configured_numbers_thread_through(self):
        ok, out = render(session__idleTimeout__enabled="true", session__idleTimeout__minutes="20",
                         session__idleTimeout__warningSeconds="30")
        assert ok, out
        cfg = _config_data(out)
        assert (cfg["sessionIdleTimeoutEnabled"], cfg["sessionIdleTimeoutMinutes"],
                cfg["sessionIdleTimeoutWarningSeconds"]) == (True, 20, 30)

    def test_absent_with_the_proxy_off(self):
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false")
        assert ok, out
        assert "sessionIdleTimeoutEnabled" not in _config_data(out)

    def test_enabled_without_the_proxy_is_refused(self):
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false",
                         session__idleTimeout__enabled="true")
        assert not ok and "no session to end" in out

    def test_a_window_past_the_cap_is_refused(self):
        ok, out = render(session__idleTimeout__enabled="true", session__idleTimeout__minutes="240")
        assert not ok and "could never fire" in out

    def test_a_warning_longer_than_the_window_is_refused(self):
        ok, out = render(session__idleTimeout__minutes="1", session__idleTimeout__warningSeconds="60")
        assert not ok and "shorter than the idle window" in out
```

#### `local-development/tests/test_ui.py` — append

```python
@pytest.fixture(scope="module")
def idle_server(tmp_path_factory):
    """Proxy on, idle timeout ON at 600 s with a 60 s warning, restrictions off so the seeded wide
    page renders for any name. Real seconds are never waited for: page.clock drives the model."""
    db = str(tmp_path_factory.mktemp("gsd-idle") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db, oauth_proxy_enabled=True, view_restrictions_enabled=False,
        session_idle_timeout_enabled=True, session_idle_timeout_seconds=600,
        session_idle_timeout_warning_seconds=60,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


def _open_idle(page, base):
    """A clocked page: Date.now and every timer are the test's to advance."""
    page.clock.install()
    page.set_extra_http_headers({"X-Forwarded-User": "alice"})
    page.goto(base)
    page.wait_for_selector(".hero .value", timeout=10_000)
    page.wait_for_function("() => idle.enabled === true", timeout=10_000)
    return page


class TestIdleTimeout:
    """The countdown dialog and what it enforces (docs/DESIGN_session_and_signout.md)."""

    def test_the_module_off_starts_no_model(self, browser, proxied_server):
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        p = ctx.new_page()
        try:
            p.goto(proxied_server)
            p.wait_for_selector("#main .card", timeout=10_000)
            p.wait_for_function("() => sessionCapNote !== ''")
            assert p.evaluate("() => idle.enabled") is False
            assert p.locator("#idle-modal").is_hidden()
        finally:
            ctx.close()

    def test_the_dialog_opens_at_the_warning_moment_traps_focus_and_counts(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(539_000)
        assert p.locator("#idle-modal").is_hidden()
        p.clock.run_for(2_000)
        assert p.locator("#idle-modal").is_visible()
        dlg = p.locator("#idle-modal [role='dialog']")
        assert dlg.get_attribute("aria-modal") == "true"
        assert dlg.get_attribute("aria-labelledby") == "idle-title"
        assert p.evaluate("() => document.activeElement.id") == "idle-stay"
        assert p.evaluate("() => document.getElementById('wrap').inert") is True
        left = int(p.locator("#idle-countdown").inner_text())
        assert 55 <= left <= 59, left
        p.clock.run_for(10_000)
        assert int(p.locator("#idle-countdown").inner_text()) == left - 10

    def test_escape_keeps_the_session_and_restores_focus(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.focus("button[data-nav='groups']")
        p.clock.run_for(545_000)
        assert p.locator("#idle-modal").is_visible()
        p.keyboard.press("Escape")
        assert p.locator("#idle-modal").is_hidden()
        assert p.evaluate("() => idle.state") == "active"
        assert p.evaluate("() => document.getElementById('wrap').inert") is False
        assert p.evaluate("() => document.activeElement.dataset.nav") == "groups"
        p.clock.run_for(300_000)
        assert p.locator("#idle-modal").is_hidden(), "the clock restarted"

    def test_enter_on_the_default_button_keeps_the_session(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        p.keyboard.press("Enter")
        assert p.locator("#idle-modal").is_hidden()

    def test_tab_cycles_inside_the_dialog(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        p.keyboard.press("Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-signout"
        p.keyboard.press("Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-stay"
        p.keyboard.press("Shift+Tab")
        assert p.evaluate("() => document.activeElement.id") == "idle-signout"

    def test_the_poll_is_suspended_while_the_warning_is_up_and_resumes_after_stay(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                   " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        p.clock.run_for(545_000)
        p.evaluate("() => autoRefresh()")
        assert p.evaluate("() => window.__calls") == 0, "the poll ran under the countdown"
        p.keyboard.press("Escape")
        p.wait_for_function("() => window.__calls > 0", timeout=10_000)  # the re-proof refresh
        before = p.evaluate("() => window.__calls")
        p.evaluate("() => autoRefresh()")
        p.wait_for_function(f"() => window.__calls > {before}", timeout=10_000)

    def test_expiry_blanks_the_page_and_navigates_to_the_proxys_sign_out(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.route("**/oauth/sign_out", lambda route: route.fulfill(
            status=200, content_type="text/html", body="<html><body>stub sign_out</body></html>"))
        p.clock.run_for(601_000)
        p.wait_for_url("**/oauth/sign_out", timeout=10_000)

    def test_activity_in_another_tab_defers_this_tabs_timeout(self, browser, idle_server):
        ctx = browser.new_context(extra_http_headers={"X-Forwarded-User": "alice"})
        a, b = ctx.new_page(), ctx.new_page()
        try:
            a.clock.install()
            a.goto(idle_server)
            a.wait_for_function("() => idle.enabled === true", timeout=10_000)
            b.goto(idle_server)
            b.wait_for_function("() => idle.enabled === true", timeout=10_000)
            a.clock.run_for(400_000)
            b.keyboard.press("ArrowDown")           # activity in the OTHER tab
            a.wait_for_function("() => Date.now() - idle.lastActivityAt < 1000", timeout=5_000)
            a.clock.run_for(300_000)                 # 300 s since the other tab's activity
            assert a.locator("#idle-modal").is_hidden()
            a.clock.run_for(300_000)                 # now 600 s: it fires
            assert a.locator("#idle-modal").is_visible() or "sign_out" in a.url
        finally:
            ctx.close()

    def test_nothing_is_persisted_across_a_reload(self, page, idle_server):
        """The localStorage trap: an origin recorded there outlives the session and fires early."""
        p = _open_idle(page, idle_server)
        p.clock.run_for(545_000)
        assert p.evaluate("() => localStorage.length") == 0
        p.reload()
        p.wait_for_function("() => idle.enabled === true", timeout=10_000)
        assert p.evaluate("() => idle.state") == "active"
        assert p.locator("#idle-modal").is_hidden()

    def test_forced_colors_keeps_a_visible_border(self, page, idle_server):
        p = _open_idle(page, idle_server)
        p.emulate_media(forced_colors="active")
        p.clock.run_for(545_000)
        width = p.evaluate("() => getComputedStyle(document.querySelector('.idle-dialog')).borderTopWidth")
        assert width == "2px", width
```

### Docs, changelog, chart

- `docs/DESIGN_session_and_signout.md`: the "What ships" table gains a row `| idle timeout (module, off by default) | the page's idle model → the proxy's sign_out | session.idleTimeout.{minutes,warningSeconds} |`; §"Deliberately not implemented" is rewritten: the first paragraph becomes "**A page-enforced idle timeout with a countdown** — now built as an off-by-default module (0.13.0), applying the three lessons that were recorded here for exactly this:" followed by the three lessons each annotated with how it was met (own keys; enforcement = navigation to the proxy's `sign_out`, the page's ended-panel still only from an auth redirect, no `localStorage`, `BroadcastChannel` across tabs; `autoRefresh()` gate). The two measurements that made the first design fragile stay verbatim.
- `docs/CHANGELOG.md`:
  ```
  ## Application 0.13.0 — chart 0.12.0 — <date>

  - **Idle timeout with a countdown, as an off-by-default module.** After `session.idleTimeout.minutes`
    of no pointer, keyboard or tab-visibility activity a `role=dialog` countdown opens (focus trapped
    with `inert`, Escape or Enter to stay, forced-colors border), and at zero the page removes its data
    and sends the browser to the proxy's `sign_out`, which clears the cookie. Enforced by the proxy,
    modelled by the page: nothing is persisted, activity in one tab defers every tab of that browser,
    and the 60 s poll is suspended while the countdown is up so an unattended tab cannot keep a
    session alive. The absolute cap stays the guarantee for a tab that never gets there. `/api/whoami`
    `session` gains `idle_timeout`. (design `DESIGN_session_and_signout.md`)
  - **Chart 0.12.0:** `session.idleTimeout.{enabled,minutes,warningSeconds}`; refused without the proxy,
    and refused when the window is not shorter than `oauthProxy.cookie.expire`.
  ```
- Chart README, "Authentication" table, three rows: `session.idleTimeout.enabled` (`false`, "signs people out after inactivity; the page counts, the proxy's `sign_out` ends the session; refused without the proxy"), `.minutes` (`30`, "must be shorter than `oauthProxy.cookie.expire` or the render is refused"), `.warningSeconds` (`60`, "at least 5 and shorter than the window").
- `Chart.yaml`: `version: 0.12.0`, `appVersion: "0.13.0"`, comment `# CHART 0.12.0 (<date>), MINOR: appVersion moves to application 0.13.0; three new values under session.idleTimeout render into the ConfigMap when the proxy is on, and two new render guards. Rendered objects otherwise unchanged.`

### Verification

```
./.venv/bin/python -m pytest tests/test_session_api.py tests/test_config.py -q -k "Idle or Whoami"
./.venv/bin/python -m pytest tests/test_ui.py -q -k "IdleTimeout"         # ~10 s wall clock: the clock is faked
./.venv/bin/python -m pytest tests/test_chart_strategy.py -q -k IdleTimeout
helm template t charts/group-sync-dashboard --set ingress.host=t --set session.idleTimeout.enabled=true --set session.idleTimeout.minutes=240   # -> Error: could never fire
```

### Risks and how they are closed

- An idle tab signs out a colleague mid-task in another tab → `BroadcastChannel` activity sharing (tested); no persistence, so a re-login cannot inherit a stale origin.
- Countdown fires while the reader is reading without touching anything → the dialog itself is the recovery (Escape/Enter), and the poll keeps the table current until the warning, not before.
- Laptop closed, navigation never happens → the proxy's absolute cap still ends the session; the values comment says so.
- Timer throttling in a hidden tab → the tick is late, never early; expiry lands within a minute of the deadline and the data has already been blanked before navigation.
- A chatty live region → announced at 30 and 10 only.

---


## Batch closing sections (verbatim)

## Questions only the operator can answer

1. **Exports and audit** — accept "not recorded" (chosen), or extend `dashboard_user_activity` with an export count per day (a schema change and a synthetic interaction-marked request per export)?
2. **Namespace report classification marking** — the provenance block prints "Handling: internal — access review evidence"; is there an organisational marking to print instead (a value `features.namespaceReport.marking`)?
3. **PDF module base** — the hardened family is assumed to satisfy WeasyPrint's library closure via the builder's `dnf`; if the Hummingbird runtime refuses any of those libraries at first build, is a UBI9-based report image acceptable for that one container?
4. **Question E's alternative** — should a follow-up design `-pass-access-token` for project members' own-namespace reports, given the session design's measured refusal of that flag?

## Critical files for implementation

- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/static/index.html`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/api.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/config.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/deployment.yaml`
