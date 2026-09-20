# The report forms on CRC — the walk behind #149 R7

Deployed head `7fa4a6e` (`feat/149-forms`, through the Argo Application; `running : 7fa4a6e2c4 — verified
in-pod`), walked with `forms_walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then 375×740;
`mnemonic_check.py` downloads the pack the walk generated and reads what the mnemonic resolved to. Every
line below is the scripts' own output. The first run's pack certified only the picked group: the snapshot
it read (07:54:05Z) was taken 27 s after the pod started, before the poller's first capture of the
exact-group label; the next snapshot carried it and the second run shows the resolution.

| R7 claim | measured |
|---|---|
| discovered lookups from the snapshot | `lookups: 61 users | 62 groups | mnemonics ['alpha', 'beta', 'demo', …]` |
| no cluster field; required markers; the switch | `cluster field: 0 | required marks: 3 | switch: On` |
| type-ahead narrows the menu | `'alpha' → ['app-ocp-rbac-alpha-cluster-admin', 'app-ocp-rbac-alpha-cluster-audit', …]` |
| chips, the Subject count | `subject : 1 selected | chips: ['app-ocp-rbac-alpha-cluster-admin', 'alpha']` |
| the POST carries the new parameters | `{"groups": ["app-ocp-rbac-alpha-cluster-admin"], "group_mnemonic": ["alpha"], "campaign": …}` |
| the run | `Run 20260920T080125.338303Z-ed61 — done · sha256 2be91a9f…` |
| **a mnemonic resolves to the exact group the namespace pins, not a name prefix** | the pack's sections: `Group: app-ocp-rbac-alpha-cluster-admin`, **`Group: bda-rbac-trino-alpha-users`** (from `oud-poc-trino`'s `company.net/oud-group`, mnemonic `alpha`); `Scope: groups: app-ocp-rbac-alpha-cluster-admin; mnemonics: alpha` |
| group_by segmented control under Advanced | `['mnemonic*', 'app-environment', 'oud-group']` |
| 375 px | `form top/viewport/no-x-overflow [12, 740, True]` |
| no uncaught error | `errors : []` |

Captures: `01-access-certification-shell.png`, `02-chips-added.png`, `03-generated.png`,
`04-namespace-access-advanced.png`, `05-375-users.png`.
