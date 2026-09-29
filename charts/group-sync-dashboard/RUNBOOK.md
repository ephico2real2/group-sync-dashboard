# Runbook — a remote cluster's connection is broken: Refresh, then Rejoin

The dashboard polls each remote cluster with a token it keeps in a Secret, `gsd-cluster-<name>`. When that token
stops working, this runbook finds out why and repairs it. Why it works this way is in
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file. This page is only the steps.

Refresh and Rejoin are on the Cluster Configurations tab. They need two things: you pass the dashboard's
cluster-admin tier (`visibility.clusterAdminSar`), and the release sets `clusterConfig.secrets.writes.enabled: true`.
Without that switch the tab has no Refresh and no Rejoin, and section 5 is the path. Commands run from a workstation
with `oc` and `jq`, logged in to the dashboard's cluster, with a second kubeconfig context logged in to the remote
cluster as yourself. Set these once:

~~~sh
NS=group-sync-dashboard; REL=group-sync-dashboard   # the release namespace and fullname (oc get deploy -n $NS)
C=shared-qa                                         # the cluster, by the name on its card
REMOTE=shared-qa-me                                 # your kubeconfig context on that cluster (oc config get-contexts)
~~~

## 1. Decide whether the connection is actually broken

On the Cluster Configurations tab, find the cluster's card and press **Refresh**. It probes the cluster with the
token the dashboard already holds. It never logs in and changes nothing. The same answer is in the pod's log:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-(unreachable|refreshed) .*cluster=$C " | tail -3
~~~

The word under the card's `connection` row, or `outcome=` in the line, says what to do next:

| outcome | what it means | next |
|---|---|---|
| `connected` (`ok` in the log) | the stored token works | nothing is broken; the card turns green at the next poll |
| `auth_failed` | the remote refused the stored token: expired, revoked, or wrong | section 2, then 3 |
| `pending` | no token was ever fetched: a `saTokenLookup` cluster whose lookup has not written its Secret | section 3 |
| `forbidden` | the token works, but the remote's RBAC does not let it read | section 4 |
| `unreachable` | the network, DNS, or the API server | section 4 |
| `cert-verify-failed` | the dashboard does not trust the remote's certificate | section 4 |
| `not-probed` | a `userSelfLogin` cluster: its credential is a session, which the card's credential row shows | not Rejoin; see `CLUSTER_CREDENTIALS.md` |

## 2. Confirm the token on the remote before you rejoin

A token that still works on the remote means the problem is elsewhere, and Rejoin will not fix it. Present the stored
token to the remote, through your remote context:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d | jq -r .bearerToken \
  | xargs -I{} oc --context="$REMOTE" whoami --token={}
~~~

- `system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller`: the token works. Go to section 4.
- `error: You must be logged in to the server (Unauthorized)`: the token is refused. Rejoin fixes this.

Then check the two things Rejoin needs on the remote:

~~~sh
oc --context="$REMOTE" auth can-i update clusterrolebindings.rbac.authorization.k8s.io
oc --context="$REMOTE" get secret -n group-sync-operator group-sync-dashboard-cluster-poller-token \
  -o jsonpath='{.type}{"  invalid-since="}{.metadata.labels.kubernetes\.io/legacy-token-invalid-since}{"\n"}'
~~~

- `yes`: you are a cluster administrator there, so Rejoin will accept you. `no`: ask someone who is.
- `kubernetes.io/service-account-token  invalid-since=` with nothing after the `=`: the token Secret is there and
  alive. `NotFound`, or a date after `invalid-since=`, is section 4.

## 3. Rejoin from the UI

**Who may do it.** Someone who passes the dashboard's cluster-admin tier **and** is a cluster administrator of the
remote. The dashboard asks the remote, with your own login, whether you may `update clusterrolebindings` there. If
it says no, nothing is read or written. Use **your own** account: the dashboard refuses the fleet account's name.

**What to do.** On the card, once Refresh answers `auth_failed` or `pending`, press **Rejoin…**. Type your username
and password for that cluster, and press **Rejoin**.

**What it does.** One login to the remote as you, and one question to the remote about you. One read of
`group-sync-operator/group-sync-dashboard-cluster-poller-token`. The login is signed out, and the token is written to
`gsd-cluster-<name>` here. Your password is used for that one login and is not stored. The Secret records your
username as `rejoin-account`.

**How to confirm it worked.** The card's `Rejoin:` line reads `rejoined`, and **Refresh** then reads `connected`.
The Secret carries the Rejoin's provenance:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o json \
  | jq '.metadata.annotations | with_entries(select(.key | startswith("groupsync-dashboard.io/")))'
~~~

~~~json
{
  "groupsync-dashboard.io/rejoin-account": "alice",
  "groupsync-dashboard.io/rejoined-at": "2026-09-27T14:05:40Z",
  "groupsync-dashboard.io/rejoined-by": "alice",
  "groupsync-dashboard.io/source-namespace": "group-sync-operator",
  "groupsync-dashboard.io/source-service-account": "group-sync-dashboard-cluster-poller",
  "groupsync-dashboard.io/token-source": "rejoin"
}
~~~

`rejoined-by` is who pressed Rejoin, as the dashboard knows them. `rejoin-account` is the account the remote signed
in. A Secret the tab or the lookup created also keeps its `managed-by`. The pod's log has the remote's answer and the
outcome:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-rejoin(ed|-review|-failed) .*cluster=$C "
~~~

Your login is in the remote's audit log under your name. When login capture reads that cluster, the Logins tab lists
it as a `cli` login there; `kubeadmin`'s logins are never listed.

## 4. When Rejoin is not the answer

A new token fixes only a refused token. For everything else, Rejoin either refuses or repeats the failure:

| what you see | why Rejoin does not help | what fixes it |
|---|---|---|
| `forbidden` on Refresh | the token works; the remote's RBAC is missing | bind the poller ServiceAccount to the dashboard's reader ClusterRole on the remote |
| `unreachable` on Refresh | nothing answered | the cluster's API URL, DNS, a NetworkPolicy or a proxy, from this pod |
| `cert-verify-failed` on Refresh | the trust is wrong | the cluster's CA (`tlsClientConfig.caData`) or the chart's `trustedCA` |
| `sa-token-secret-missing` from Rejoin | the remote has no token Secret to read | create it there: a `kubernetes.io/service-account-token` Secret named `group-sync-dashboard-cluster-poller-token`, annotated `kubernetes.io/service-account.name: group-sync-dashboard-cluster-poller` |
| `sa-token-invalidated` from Rejoin | the remote's legacy-token cleaner killed that token | delete and recreate that Secret on the remote |
| `not-cluster-admin` from Rejoin | the remote says you may not `update clusterrolebindings` there | ask a cluster administrator of the remote |
| `login-failed` from Rejoin, saying the password was not sent | the dashboard could not reach the remote's login | the checks for `unreachable`; the trust must cover the OAuth route too |

## 5. The manual fallback, when the UI is not available

The two-cluster path. It needs someone who is cluster-admin on **both** clusters, with two sessions open.

~~~sh
# on the REMOTE cluster: a token for the poller ServiceAccount (it expires after --duration)
oc --context="$REMOTE" create token group-sync-dashboard-cluster-poller -n group-sync-operator --duration=20m

# on the DASHBOARD's cluster: the whole config, not only the token, because a merge replaces the config value.
# Keep the tlsClientConfig the Secret has now: oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d
oc patch secret gsd-cluster-$C -n $NS --type=merge \
  -p '{"stringData":{"config":"{\"bearerToken\":\"<token>\",\"tlsClientConfig\":{\"insecure\":false}}"}}'
~~~

A token from `oc create token` expires. To store the long-lived token that Rejoin stores, read `.data.token` of
`group-sync-operator/group-sync-dashboard-cluster-poller-token` on the remote instead, and base64-decode it.

A Secret written by `oc` rides the discovery cadence: it takes effect within `discoveryIntervalSeconds` (300 seconds
by default), not in seconds as a write from the tab does. It carries no provenance either: nothing on it says who
wrote it or where the token came from.

## 6. What not to do

- **Do not press Rejoin again and again.** Once your password is sent, the answer is final. The pod that sent it
  does not send a refused password again while it is the same password. A restarted pod, or another replica behind
  the Route, does not know that and can send it once more, so check before you press again. A locked directory
  account answers LDAP code 19, which OpenShift turns into an **HTTP 500, not a 401**, so trying again only locks it
  further. After a 500, check the account with your directory's administrators first. That pod holds the password
  back until it restarts, even once the account is fixed; a new password works at once.
- **Do not type the fleet account's password into Rejoin.** The dashboard refuses the fleet account's name, and a
  lockout of that account stops every cluster.
- **If the dialog says the answer did not arrive, or the pod restarted during a Rejoin, do not rejoin blindly.**
  Press Refresh first: the Rejoin may have finished. Then list your password logins on the remote and delete any the
  dashboard did not sign out. A token's name is not a secret and cannot log anyone in.

~~~sh
oc --context="$REMOTE" get useroauthaccesstokens --field-selector=clientName=openshift-challenging-client \
  --sort-by=.metadata.creationTimestamp
oc --context="$REMOTE" delete useroauthaccesstokens <name>
~~~

## 7. The fleet account is held back: clear its entry by hand

A `saTokenLookup` cluster whose lookup reads `login-refused` or `login-failed`, a `userSelfLogin` cluster reading
`self-login-suspended`, or a `fleet-ping-failed … gave_up=true` line all mean the same thing: the directory answered the
fleet account's password with a failure, and the dashboard will not send that password again. The answer is recorded on
the account's Lease in this namespace, and the finding and the line name it. A 401 is a wrong password: rotate the
fleet password Secret, and the new password is tried by itself. Clear the entry by hand only when the password is right
and the answer was about something else: a sick target's 500, or an account the directory has since unlocked.

~~~sh
LEASE=gsd-fleet-...   # the Lease the finding or the line names
oc get leases.coordination.k8s.io "$LEASE" -n $NS -o jsonpath='{.metadata.annotations.groupsync-dashboard\.io/refused}{"\n"}'
oc annotate leases.coordination.k8s.io "$LEASE" -n $NS groupsync-dashboard.io/refused-
oc rollout restart deployment.apps/$REL -n $NS      # the running pod keeps its own copy of the refusal until it restarts
~~~

**After a `crc start`, or a Lease deleted by hand.** `crc start` deletes every Lease on the cluster. The dashboard keeps
each fleet Lease's entry and its daily ping's instants beside its database, in `/data/fleet-gate.json`
(`/data/<pod>/fleet-gate.json` above one replica), and puts a deleted Lease back from it within one discovery interval,
saying so once. Run one replica for the +0 guarantee: independent per-pod copies may be stale, so the replica that
recreates the Lease can still allow another bind or ping (SPEC_S4f §3.9):

~~~sh
oc logs -n $NS deployment.apps/$REL -c dashboard --since=15m | grep fleet-lease-absent
~~~

So deleting the Lease does not clear its entry; removing the annotation does. One order undoes a clear: the entry
removed, then a `crc start` before any dashboard pod had read the Lease again — a running pod reads it once per
discovery interval (300 s by default), and `crc start` restarts the pod without that read. The copy still held the
entry and puts it back, and the line says `kept=true refused=<code>`. Wait until `oc get leases.coordination.k8s.io
"$LEASE" -n $NS` finds the Lease again, then remove the entry and restart the pod with `oc rollout restart`, as above. With
`persistence.enabled: false` the copy lives only as long as the pod: a new pod whose Lease was deleted says
`kept=false`, and a password the entry held back may be sent once more.

**If an absent Lease's copy cannot be read, or a reservation cannot be kept**, nothing binds and the attempting path
reports `fleet-state-unavailable` naming the file. Other saves log the failure while the Lease remains authoritative;
a path already gated need not attempt a reservation or publish another finding. Free space on the data volume. Saving
a present Lease also parses the existing file. Move an unreadable file aside only after checking that every fleet
Lease exists:

~~~sh
oc get leases.coordination.k8s.io -n $NS -l groupsync-dashboard.io/lease-type=fleet-account
oc exec -n $NS deployment.apps/$REL -c dashboard -- mv /data/fleet-gate.json /data/fleet-gate.json.unreadable
~~~
