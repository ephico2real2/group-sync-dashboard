# Remote cluster access — who decides a reader's tier

| | |
|---|---|
| Status | **Proposed.** D1, D2 and D4 directed by the operator; D3, D5 and D6 open (§7) |
| Date | 2026-09-23 |
| Scope | the per-cluster visibility policy (`clusters[].visibility`, `clusters[].identity`) for every cluster the dashboard polls that is not its host |
| Relates to | `docs/ACCESS_CONTROL.md` §11 (per-cluster authorisation, D2 of the 2026-09 programme), #307, #322 (the cluster-admin tier), #316 (Rejoin) |

## 1. Summary

On the lab, `kubeadmin` is `cluster-admin` and sees everything on the host cluster, `dashboard`. On `shared-rnd` and
`shared-qa` it sees only its own rows. Both remotes resolve to `visibility=self-only identity=none` (the pod's
`cluster-resolved` log line), so **nobody is asked** whether a reader may see them wide.

The remote could answer that question itself. The token the dashboard already holds for `shared-rnd` can ask
`shared-rnd`'s own RBAC, and it answers correctly for every reader measured (§5). The dashboard cannot use that
answer for these two clusters because `remote-sar`, the policy that asks the remote, is refused for any cluster
declared through a Secret, and both are (§6).

This document defines the two policies that grant a wide view on a remote, `inherit` and `remote-sar`, shows how
each decides, and records the decisions that make `remote-sar` available for every way a cluster is joined.

## 2. The three answers the dashboard can give today

The sign-in is always on the host, through the oauth-proxy. What differs is **which API is asked** whether the
reader may see a cluster's data wide. The question is the one `visibility.adminSar` asks: *may this person
`list clusterrolebindings`?*

![Three policies compared: inherit asks the host API, remote-sar asks the remote API with the joining ServiceAccount's token, self-only asks nobody](diagrams/remote-cluster-access/policies-who-decides.light.png#gh-light-mode-only)
![Three policies compared: inherit asks the host API, remote-sar asks the remote API with the joining ServiceAccount's token, self-only asks nobody](diagrams/remote-cluster-access/policies-who-decides.dark.png#gh-dark-mode-only)

*Figure 1. Only the middle row differs. `inherit` never contacts the remote about the reader; `remote-sar` asks the
remote with the credential the dashboard already holds for it; `self-only` asks nobody.*

```text
            inherit                     remote-sar                    self-only
   reader signed in on the host   reader signed in on the host   reader signed in on the host
              |                            |                             |
        dashboard pod                dashboard pod                 dashboard pod
              | SubjectAccessReview        | SubjectAccessReview         :  (no call)
              v                            v                             v
   HOST API — dashboard's own SA  REMOTE API — joining SA token   the answer is fixed
   host groups                    the reader's remote groups
              |                            |                             |
   the host answer, applied to    the remote's own answer        "self" for every reader
   the remote's rows              about the reader
```

## 3. The two models, defined

| | `inherit` + `same-as-host` | `remote-sar` + `same-as-host` |
|---|---|---|
| **Who is asked** | the **host** API, by the dashboard's own ServiceAccount | the **remote** API, with the token that joined the cluster |
| **The question** | may the reader `list clusterrolebindings` on the host? | may the reader's username `list clusterrolebindings` on that remote? |
| **The reader's groups** | read from the host's Group objects | read from the remote's Group objects (`local-development/gsd/kube.py#ClusterClient.fetch_groups_of_user`) |
| **identity** | **no effect on the tier.** Under `inherit` identity is not consulted: the host's decision applies, and self rows are keyed by the host username. `same-as-host` only documents intent. | **load-bearing.** The host username is sent to the remote, so it must name the same person there. The chart refuses `remote-sar` without `same-as-host`. |
| **Remote RBAC needed** | none; a read-only token is enough | the joining ServiceAccount needs `create subjectaccessreviews` and `list groups` on the remote |
| **Correct when** | one team administers the fleet, so host admin = remote admin by policy | clusters share one identity provider (a directory), so one `uid` is one person |
| **Risk** | a host admin sees a remote's bindings and people wide with no standing on that remote: a policy decision, made per cluster | htpasswd users and `kube:admin` are per-cluster people, so the same name on two clusters is two accounts (`docs/ACCESS_CONTROL.md` §11) |

`self-only` (nobody is wide) and `hidden` (polled, never served) are unchanged by this document.

## 4. How `remote-sar` decides

![remote-sar decision flow: a cached verdict or a SubjectAccessReview on the remote; allowed gives the wide view, denied gives self, a 403 or an unreachable remote gives self](diagrams/remote-cluster-access/remote-sar-decision-flow.light.png#gh-light-mode-only)
![remote-sar decision flow: a cached verdict or a SubjectAccessReview on the remote; allowed gives the wide view, denied gives self, a 403 or an unreachable remote gives self](diagrams/remote-cluster-access/remote-sar-decision-flow.dark.png#gh-dark-mode-only)

*Figure 2. Every path except "allowed" narrows, which is the fail-closed direction. The two failure outcomes must
be named to the reader, because neither says anything about the reader's access.*

```text
 reader opens the remote
   -> verdict cached within visibility.tierTtlSeconds?  -- yes --> reuse it
   -> no: read the reader's groups on the REMOTE
   -> POST SubjectAccessReview on the REMOTE, with the joining ServiceAccount's token
        allowed              -> wide view on this cluster          (cached per reader and cluster)
        denied               -> the reader's own rows              (cached: a real answer)
        403 (may not ask)    -> self for everyone, plus a finding  (not cached)
        unreachable / junk   -> self, not cached; counted by GroupSyncDashboardVisibilityChecksFailing
```

| Outcome | Reader sees | Cached | What the page must say |
|---|---|---|---|
| allowed | the wide view on this cluster | yes, per (reader, cluster) | *this cluster says you may see everything* |
| denied | own rows | yes: a real answer | *this cluster says: your own rows* |
| 403: the joining ServiceAccount may not create the review | own rows, for every reader | no | *this cluster cannot check access: grant `create subjectaccessreviews` to the ServiceAccount that joined it* |
| unreachable or unparseable | own rows | no | *this cluster could not be asked just now* |

## 5. Measured on the lab, 2026-09-23

The remote's own answer, asked with the token the dashboard holds for `shared-rnd` (a `SubjectAccessReview` for
`list clusterrolebindings`, naming the user and the user's groups on that cluster):

| Reader | Answer | Why |
|---|---|---|
| `kubeadmin` | **allowed** | ClusterRoleBinding `kubeadmin` → `cluster-admin` |
| `jane.smith` | **allowed** | the auditor-tier binding (`group-sync-dashboard-ra-…`, #312) |
| `asmith` | denied | no admin or auditor standing |
| `tmp-contractor-9931` | denied | no admin or auditor standing |

What the joining ServiceAccounts may do on the remote (`oc auth can-i … --as=system:serviceaccount:…`):

| Joining ServiceAccount | create subjectaccessreviews | list groups | get users | list clusterrolebindings |
|---|---|---|---|---|
| `group-sync-dashboard-cluster-poller` (`shared-rnd`) | yes | yes | yes | yes |
| `shared-qa-poller` (`shared-qa`) | yes | yes | yes | yes |

Both are bound to the ClusterRole `group-sync-dashboard-cluster-poller`, which carries those verbs.

**Why the lab's behaviour changed.** Until 2026-09-22, `shared-rnd` was a hand-made Secret with `visibility: inherit`
and `identity: same-as-host` (`docs/examples/cluster-secret-shared-rnd.redacted.yaml`). #307 replaced it with a
`saTokenLookup` stanza in `environments/crc.yaml` that deliberately declares no visibility, so it took the default,
`self-only`, and the host's cluster-admin stopped being wide there. `shared-qa` is a hand-made Secret from #310's
testing with no visibility key, so it has always been `self-only`. The lab's `kubeadmin` is an **htpasswd** user
(identity `developer:kubeadmin`), not the built-in `kube:admin`.

The commands, re-runnable against the lab with a kubeadmin session:

```sh
# the policy each cluster resolved to
oc logs -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard | grep cluster-resolved

# what the joining ServiceAccount may do on the remote
oc auth can-i create subjectaccessreviews.authorization.k8s.io \
  --as=system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller

# the remote's own answer, with the token the dashboard holds (read from gsd-cluster-shared-rnd)
curl -sk -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -X POST \
  https://api.crc.testing:6443/apis/authorization.k8s.io/v1/subjectaccessreviews \
  -d '{"apiVersion":"authorization.k8s.io/v1","kind":"SubjectAccessReview","spec":{"user":"kubeadmin","groups":[],
       "resourceAttributes":{"group":"rbac.authorization.k8s.io","resource":"clusterrolebindings","verb":"list"}}}'
```

## 6. What is supported today

| How the cluster was joined | `inherit` | `remote-sar` | `self-only` | `hidden` |
|---|---|---|---|---|
| a `clusters:` stanza in values, with a bearer token | yes | yes | yes | yes |
| a Secret created on the Cluster Configurations tab | yes | **refused** | yes | yes |
| `saTokenLookup` (the lookup writes a Secret) | yes | **refused** | yes | yes |

**Why refused.** The per-cluster `TierResolver` that asks a remote (`local-development/gsd/kube.py#TierResolver`) is
built **once, at start-up**, from the values list (`local-development/gsd/api.py#remote_resolvers`). A cluster
declared through a Secret appears **at runtime**, from discovery, and never gets one. The Secret parser refuses
`remote-sar` for that reason (`local-development/gsd/clusterconfig/parser.py`: *"remote-sar for a Secret-sourced
cluster is S2"*), and the chart refuses it beside `saTokenLookup`
(`charts/group-sync-dashboard/templates/_helpers.tpl`: *"remote-sar is not yet accepted from a Secret (SPEC_S1)"*).
The way clusters are now joined is exactly the way that cannot ask the remote.

## 7. Decisions

| | Decision | Options | Status |
|---|---|---|---|
| **D1** | Support `remote-sar` for every way a cluster is joined | build the remote resolver when discovery finds the cluster, rebuild it when the Secret's credential changes, drop it when the cluster is retired; accept `remote-sar` from a Secret and from a `saTokenLookup` stanza | **Directed** by the operator: *"we need to have both supported and clearly defined"* |
| **D2** | The default for a newly joined remote | `self-only` (today) or `remote-sar` | **Directed**: `remote-sar`. The operator: *"we should be looking up user's permission on the remote host to determine their access … unless the service account that joined the remote cluster doesn't have the right permissions"* |
| **D3** | What "the same person" means under `remote-sar` | (a) every username; (b) directory identities only, with the break-glass providers (`loginCapture.htpasswdProviders`) never mapped across clusters | **Open.** (b) is correct for real estates, but it narrows the lab's htpasswd `kubeadmin` on `shared-rnd`; an LDAP admin would be wide. (a) matches the lab's expectation. |
| **D4** | When the joining ServiceAccount may not ask | silent self, or self with a named finding | **Directed** (fall back to self). Recommended: name it, on the Cluster Configurations tab and under the cluster selector, with the grant that fixes it |
| **D5** | Say which rule decided the reader's view of a cluster | one line under the cluster selector: *the host decides* · *this cluster says you may see everything* · *this cluster says: your own rows* · *this cluster cannot check access* · *this cluster is self-only* | **Open**, recommended. The missing reason is why the lab's narrowing looked like a defect. |
| **D6** | The lab until D1 ships | `inherit` + `same-as-host` on `shared-rnd` restores the behaviour before #307 and is literally true there (same cluster, same identity provider); `remote-sar` once D1 lands. `shared-qa`: the same, or remove it if it was only #310's test cluster | **Open** |

## 8. Consequences of D1 and D2

- **Code:** a `TierResolver` per `remote-sar` cluster owned by the discovery registry instead of built once in
  `create_app`; keyed by cluster and rebuilt when the cluster's credential or trust changes; the parser and the chart
  stop refusing `remote-sar` for Secret-declared clusters; a finding code for the 403 of D4.
- **Default:** a new remote with no `visibility` resolves to `remote-sar`, which needs an `identity`. The default
  identity follows D3.
- **RBAC:** none added by this chart. The joining ServiceAccount on each remote needs `create subjectaccessreviews`
  and `list groups`; the ClusterRole the operator chart already binds to it carries both (§5). A remote that lacks
  them degrades to D4's finding, never to a wider view.
- **Tests:** a Secret-declared `remote-sar` cluster asks the remote; a credential change rebuilds its resolver; a
  403 yields self and the finding; an `inherit` cluster never contacts the remote about the reader.

## 9. How this composes with the cluster-admin tier (#322)

Passing `clusterAdminSar` grants every tier **the host decides**, and per-cluster policies still apply (the operator,
2026-09-23). Under this design: on `inherit` clusters a host cluster-admin is wide; on `remote-sar` clusters the
remote's own answer about the reader stands, because being admin on the host is not proof on another cluster; on
`self-only` and `hidden` clusters nothing changes.

## Diagram sources

The figures are rendered from `docs/diagrams/remote-cluster-access/source.html`, one hand-authored page (inline
SVG, light and dark palettes), at twice the pixel density: open it in a browser, set `data-theme` on the root element
to `light` or `dark`, and screenshot each `.fig-scroll` element. The pictures depict the decision points in §3 and
§4, and the text twins beside them carry the same points. If either section changes, change the picture, its twin
and the page together.
