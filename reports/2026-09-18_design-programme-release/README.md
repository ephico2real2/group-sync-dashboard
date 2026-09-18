# The design programme's release walk — CRC, 2026-09-18

Every open PR of the design programme merged to main, built, deployed to CRC and walked. The nine
screenshots here are the deployed pages at that commit, not a local harness.

**Outcome:** all nine tabs render; the version stamp in each reads `v0.24.0 · 66fe106061`, the commit
the pods were verified to be running.

| Fact | Value |
|---|---|
| Cluster | CRC, `crc-local` (with `mock` as the second cluster) |
| Commit | `66fe1060616acb29b2f08dda223229f5baceee69` |
| Image tag | `0.24.0-66fe106061`, verified in-pod by `release-crc.sh` |
| Signed in as | kubeadmin, the wide tier |
| Theme / scale | dark, device scale 2 |

## What the pictures show, against what merged

| Screenshot | The PR it evidences | What to look for |
|---|---|---|
| `screenshots/00-home.png` | #186 (#158) | Home is the **first tab and the landing page**. It answers in a sentence — "You have cluster-wide cluster-admin on crc-local" — then What changed, Cluster-wide, the 13 namespaces reached, the 14 direct grants, and the groups section stating that no group grants here |
| `screenshots/01-overview.png` | #180 (#172) | The **fleet view**: the cluster selector on "all clusters", a tile per cluster, and the alert pager with its severity chips. An absent cluster on Overview is a position, not a missing default |
| `screenshots/06-namespace-audit.png` | #181 (#167) | Namespaces as entities: 110 listed, the mnemonic and app-environment label columns, the find box that matches name **or** label value, via-groups and direct-grants counts, and every row a door to its namespace page |
| all nine | #179 (#152, #166) | Appearance and Colours in the static header of every page, and the tab bar carrying Home through Reports |
| `screenshots/02-groups.png`, `03-users.png` | #183 (#174) | The Find box beside the cluster selector, on every page that has no list box of its own |

## How to repeat it

```sh
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) KUBECONFIG=<the cluster's kubeconfig> \
  local-development/.venv/bin/python local-development/capture-screenshots.py \
    --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin --out <dir> --scale 2
```

The password comes from the environment only, never an argument: argv is readable by every process on
the host.
