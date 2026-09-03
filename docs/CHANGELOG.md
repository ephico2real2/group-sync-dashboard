# Changelog

What each release changed, newest first. Two artefacts, two version lines (`docs/RELEASING.md`):
the application (`pyproject.toml`, deployed as `quay.io/ephico2real/group-sync-dashboard:<version>`)
and the chart (`Chart.yaml`, published to the Helm repository). A chart release that only moves
`appVersion` is listed under the application release it carries. The reasoning behind each change
lives next to the code and in the design and review records linked here.

## Application 0.10.1 — chart 0.9.2 — 2026-09-04

- **Access granted:** a group name is a drill only where a group page can answer. Built-in
  virtual groups never have a Group object and unresolved bindings name groups that never existed,
  so those names drilled to a 404 that blamed a deletion which never happened. They render as plain
  text now; dangling and granted groups keep the drill. (#49)

## Application 0.10.0 — chart 0.9.1 — 2026-09-03

- **Access granted opens on what was granted.** The faults (dangling, unresolved, unmanaged) stay on
  top because nothing on the cluster reports them; the Granted section follows; the built-in
  majority stays one filter away. It used to open on the faults alone. (#48)
- **Every row says who it reaches.** `member_count` — the named Group's own count — and
  `logged_in_count` — members with a `User` that has an identity, the 0.9.0 definition of a login.
  Both null when no Group object exists, so 0 means the group exists and grants nobody today, and is
  highlighted. Opt-in on the store query and pre-grouped, so the metrics scrape, the poller and
  `/api/clusters` pay nothing for it; `/api/clusters` also stops materialising every binding row to
  count them. (#48)
- **Filter and sort.** A type-to-match box like the Groups and Users tabs, over group, role,
  namespace and binding name, narrowing every section with the cluster-wide counts untouched; sortable
  column headers on the shared table; truncation disclosed when the page is cut. (#48)
- **A narrowed reader sees their own grants.** The findings endpoint still refuses them; the tab reads
  their own `/users/{name}` and shows the bindings that reach them through their groups, with the
  group named. The tab re-decides its tier from the whoami that just arrived, so a tier change
  mid-session paints the right view on the next cycle. (#48; review record
  `REVIEW_access_granted_reach.md`)

## Application 0.9.0 — chart 0.9.0 — 2026-09-03

- **The Users tab counts the people who have logged in.** Rows are OpenShift `User` objects, which
  the cluster creates at first login and never before; group membership is an attribute of a row
  and may be zero. Synced members who have never logged in are one line, by count, with the names a
  click away. Per row: first login, identity provider(s), last captured login, display name.
  Headline KPIs, chips by membership and provider, a banner naming `rbac.users` when the read is
  refused, and the age of the last successful read. `/users` pages properly (`total`, `offset`) and
  carries `logged_in_total` beside `total` so a manual account with no identity is listed but not
  counted as a login. Schema migration 7 rebuilds `ocp_user`. (#47; design
  `DESIGN_users_tab_logins.md`, review record `REVIEW_users_tab_logins.md`)
- **Fix:** `Store.login_without_access` was defined twice and only the undocumented copy ran; an
  AST guard test now fails the build on any repeated method name in the package. (#46)
- **Chart 0.9.0:** `appVersion` moves; the `rbac.users` grant is now the Users tab's source rather
  than a decoration of it, so turning it off costs that tab's rows (the tab says so by name) instead
  of display names. No template output changes.

## Chart 0.8.0 — application 0.8.1 — 2026-09-03

- **A Route the router names, by default.** `route.enabled` (default true) emits an OpenShift Route
  with `spec.subdomain: <fullname>`, so the hostname is `<fullname>.<apps domain>` — the release name,
  never the namespace — with no cluster lookup at render time. The ServiceAccount's OAuth callback
  becomes a reference to that Route by name. That is what lets ArgoCD, Flux and any `helm template`
  renderer deploy the chart with no per-cluster value: the Ingress path's apps-domain lookup could
  never succeed there and the render was refused. `ingress.enabled` (default false) keeps the
  Ingress for plain Kubernetes, unchanged. A host set deliberately (`route.host`, or a carried-over
  `ingress.host`) is used as given. (#45; design `DESIGN_route_exposure.md`, review record
  `REVIEW_route_exposure.md`)
- **`argocd.enabled` defaults to true.** It adds `argocd.argoproj.io/sync-options` annotations and
  nothing else, which Kubernetes ignores outside Argo, so an Application needs no chart value at
  all. (#45)
- On upgrade from 0.7.1 the Ingress and its generated Route are replaced by the chart's Route on the
  same hostname; sessions, data and RBAC are untouched. Measured on the reference cluster.
