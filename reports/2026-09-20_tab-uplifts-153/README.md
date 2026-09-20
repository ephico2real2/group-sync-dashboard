# The trailing tabs at the bar on CRC — the walk behind #153

Deployed head `06ef60e` (`feat/153-tab-uplifts`, through the Argo Application; `running : 06ef60e6a6 —
verified in-pod`), walked with `walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then
375×740. Every line below is the script's own output.

| #153 claim | measured |
|---|---|
| the Groups KPIs are the cluster's whole-set counts | `groups  : KPIs [['Groups on this cluster', '62', ''], ['Empty', '0', ''], ['Unattributed', '0', '']] \| rows 62` — `/api/clusters says [62, 0, 0]` |
| they stay put under the state filter | `state=empty → KPIs [['Groups on this cluster', '62', ''], …] \| rows 0` |
| a group name is a button the keyboard drills with | `Enter on app-ocp-rbac-abcd-ns-superuser → view.group app-ocp-rbac-abcd-ns-superuser` |
| the Users problem tiles carry the rail when they hold anyone | `['Logged in, no synced group', '53', 'rail'], ['Synced, never logged in', '2', 'rail']` (the two others: no rail) |
| the provider is a chip | `provider chips on the first row ['ldap-local']` |
| the review tile's rail | `bindings: … ['Need review', '6', 'rail'] …` |
| the Usage footnote in three | `usage   : lead words ['Times', 'An interaction', 'Not logins.']` |
| 375 px, every tab | `groups / users / bindings / usage no-x-overflow True` |
| no uncaught error | `errors  : []` |

Captures: `01-groups-kpis.png`, `02-group-drill-by-keyboard.png`, `03-users-rails-chips.png`,
`04-bindings-review-rail.png`, `05-usage-footnote.png`, `06-375-groups.png`, `06-375-users.png`.
