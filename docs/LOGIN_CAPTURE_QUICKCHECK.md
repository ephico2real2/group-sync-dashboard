# Quick check: is login capture actually working?

Five commands that prove the whole path end to end — turn the verbosity up, cause a login, and read
that login back **using the dashboard's own ServiceAccount token**, which is the only identity that
matters. Every command and every output below was run on a live CRC cluster on 2026-08-07; nothing here
is illustrative.

Use this after enabling `authLogLevel` / `loginCapture`, or when the dashboard shows no login activity
and you need to find out which link in the chain is missing.

## 0. Credentials (CRC only)

```bash
crc console --credentials
```

```
To login as a regular user, run 'oc login -u developer -p developer https://api.crc.testing:6443'.
To login as an admin, run 'oc login -u kubeadmin -p <redacted> https://api.crc.testing:6443'
```

## 1. Turn the verbosity up

The oauth-server only names the person logging in at `Debug`. **At the default it does not write the
line at all**, so a login that happens while the level is `Normal` is invisible *forever* — no later
capture can recover it.

```bash
helm upgrade group-sync-dashboard charts/group-sync-dashboard -n group-sync-dashboard \
  -f my-values.yaml \
  --set authLogLevel.manage=true --set authLogLevel.enabled=true
```

`loginCapture.enabled` is on by default since chart 0.14.0, so the module half needs no flag unless
your values file turned it off.

> **Pass your whole value set.** `helm upgrade` with only `--set authLogLevel.*` discards every other
> user-supplied value. Measured: it silently reverted `oauthProxy.apiTokenAccess.enabled` on this
> release and broke API token access three commands later, with nothing connecting cause to symptom.
> Re-pass `-f`, or use `--reuse-values`, then confirm with `helm get values`.

> ⚠️ **This rolls the OAuth server.** On a single-replica cluster that is a login outage, not a rolling
> update — `authentication` reports `OAuthServerDeploymentAvailable: no oauth-openshift pods available
> on any node` while it happens. Check the blast radius first:
> `oc get deploy oauth-openshift -n openshift-authentication -o jsonpath='{.spec.replicas}{"\n"}'`

The Job reports what it did:

```bash
oc logs -n group-sync-dashboard -l app.kubernetes.io/component=auth-loglevel --tail=20
```

```
requested logLevel: Debug
current logLevel:   Normal

⚠️  oauth-openshift runs ONE replica: this roll is a LOGIN OUTAGE, not a rolling
    update. In-flight logins fail and new ones are refused until the replacement
    pod is Ready. Same on the way back off — both directions are a logLevel change.

patching authentications.operator.openshift.io/cluster -> Debug
authentication.operator.openshift.io/cluster patched
waiting up to 180s for --v=4 to be live
rollout complete: --v=4 live, 1/1 available and updated

✅ OAuth server logLevel is now Debug
```

## 2. Confirm the level reached the operand, not just the CR

**Check both.** The CR field is what you asked for; `--v=` is what is actually running. They differ for
about thirty seconds after the patch, and during that window the log lines still do not exist.

```bash
oc get authentications.operator.openshift.io cluster -o jsonpath='{.spec.logLevel}{"\n"}'
oc get deploy oauth-openshift -n openshift-authentication \
  -o jsonpath='{.spec.template.spec.containers[0].args}' | grep -o '\-\-v=[0-9]'
```

```
Debug
--v=4
```

`Normal` is `--v=2`, `Debug` is `--v=4`. If the CR says `Debug` and the template still says `--v=2`, the
operator has not reconciled yet — wait, do not re-patch.

## 3. Cause a login

An **isolated `KUBECONFIG`**, so this does not clobber your own admin session:

```bash
KC=$(mktemp); touch "$KC"
KUBECONFIG=$KC oc login https://api.crc.testing:6443 \
  -u developer -p developer --insecure-skip-tls-verify=true
KUBECONFIG=$KC oc whoami
rm -f "$KC"
```

```
Login successful.
developer
```

> Do not pipe `oc login` into `head` or `grep`. It writes the kubeconfig *after* printing, so a closed
> pipe kills it and the login appears to fail while actually having succeeded partially.

**Do all four cases, not just a success.** Three of the five parsing rules below cannot be seen from a
successful login alone, and two failure causes turn out to be indistinguishable — which you only
discover by producing both:

```bash
login() { KC=$(mktemp); touch "$KC"
  KUBECONFIG=$KC oc login "$API" -u "$1" -p "$2" --insecure-skip-tls-verify=true; rm -f "$KC"; }

login john.doe   'Ldap123!'        # LDAP, correct password
login jane.smith 'WRONG-PASS'      # LDAP, wrong password
login bob.wilson 'GateTest123!'    # a real user NOT in the login-gate group
login nosuchuser 'whatever'        # a username that does not exist
login developer  'developer'       # HTPasswd, correct password
```

```
LDAP good password  (john.doe)   → ✅ success
LDAP BAD password   (jane.smith) → ❌ Login failed (401 Unauthorized)
LDAP gate-DENIED    (bob.wilson) → ❌ Login failed (401 Unauthorized)
unknown user        (nosuchuser) → ❌ Login failed (401 Unauthorized)
```

**All three failures are the same 401 to the client.** The difference — where there is one — exists only
in the pod log.

## 4. Read it back as the dashboard's ServiceAccount

This is the step that proves the grant, not the cluster. Use the **SA token**, not your admin token —
otherwise you have only proved that a cluster-admin can read logs.

```bash
TOK=$(oc create token group-sync-dashboard -n group-sync-dashboard --duration=10m)
API=$(oc whoami --show-server)
```

Confirm whose token it is:

```bash
python3 -c "
import base64,json,os
p=os.environ['TOK'].split('.')[1]; p+='='*(-len(p)%4)
print(json.loads(base64.urlsafe_b64decode(p))['sub'])"
```

```
system:serviceaccount:group-sync-dashboard:group-sync-dashboard
```

**Step 1 — list the pods.** Discovery is not optional: pod names are generated, production runs 2–3
replicas, and every roll replaces them.

```bash
curl -sk -H "Authorization: Bearer $TOK" \
  "$API/api/v1/namespaces/openshift-authentication/pods" \
| python3 -c "
import json,sys
for i in json.load(sys.stdin)['items']:
    print(i['metadata']['name'], i['status']['phase'])"
```

```
oauth-openshift-66444df7fc-qhzp9 Running
```

**Step 2 — read each pod's log.** `timestamps=true` gives a kubelet RFC3339 prefix, which is why no
klog parsing is needed: the klog stamp (`I0807 16:02:13`) carries no year and no timezone.

```bash
curl -sk -H "Authorization: Bearer $TOK" \
  "$API/api/v1/namespaces/openshift-authentication/pods/<pod>/log?tailLines=800&timestamps=true" \
| grep 'for login'
```

```
2026-08-07T16:02:13.376017501Z I0807 16:02:13.375952  1 basicauth.go:51]
  Login with provider "developer" succeeded for login "developer"
```

That is the capture target: **timestamp, provider, username** — read with the namespaced grant and
nothing more.

There is no Deployment log subresource, so there is no "combined logs" shortcut here:

```bash
oc get --raw "/apis/apps/v1/namespaces/openshift-authentication/deployments/oauth-openshift/log"
```

```
Error from server (NotFound): the server could not find the requested resource
```

`oc logs deploy/oauth-openshift` only *looks* combined — the client resolves the Deployment to its
ReplicaSet to its Pods and reads each one. Hence both verbs, `pods:list` and `pods/log:get`.

## 5. Turn it back off when you are done

```bash
helm upgrade group-sync-dashboard charts/group-sync-dashboard -n group-sync-dashboard \
  -f my-values.yaml \
  --set authLogLevel.manage=true --set authLogLevel.enabled=false
```

**Keep `manage=true` for this step.** `manage=false` removes the revert Job along with everything else,
so going straight there while `Debug` is live strands the cluster in `Debug` with nothing left to put it
back. Stop managing it only *after* the level has converged.

```
requested logLevel: Normal
current logLevel:   Debug
patching authentications.operator.openshift.io/cluster -> Normal
waiting up to 180s for --v=2 to be live
rollout complete: --v=2 live, 1/1 available and updated

✅ OAuth server logLevel is now Normal
```

`helm uninstall` needs no care — a pre-delete Job reverts first. `helm rollback` **does not run hooks
at all**, so rolling back past an enable leaves the level where it was; do step 5 by hand.

---

## Reading the lines correctly

Measured on 2026-08-07 across **four deliberate cases** on one cluster with two identity providers
(`developer` = HTPasswd, `ldap-local` = LDAP). This is the ground truth a parser has to be built on, and
one login is not enough to see it — three of the five rules below are invisible if you only test a
successful LDAP login.

### What to capture: every username that appears

These logs are already user-scoped — the oauth-server writes a line per *login attempt*, naming the
account that attempted it. There is nothing to filter *in*: the enhancement is to capture and process
**any** user that appears, successful or not, rather than matching against a list of people the
dashboard already knows about.

That matters for the thing this exists to see. A username that appears here and is in **no** synced
group is more interesting than one that is: it is either somebody whose access was removed but who is
still trying, or an account nobody is governing. An allowlist built from group membership would filter
out exactly those.

Only two kinds of line are *not* a person: a success whose provider is the HTPasswd one (`developer`,
`kubeadmin` — break-glass, see Rule 3), and the internal bootstrap identity. Everything else is an
attempt by a named account and gets recorded.

### One login attempt writes SEVERAL lines, across two files

| case | lines written, in order |
|---|---|
| **LDAP success** (`john.doe`, correct password) | `basicauth.go:48` failed for provider `"developer"` → `ldap.go:131` searching → `ldap.go:148` found dn= → `basicauth.go:51` **succeeded** for `"ldap-local"` |
| **LDAP bad password** (`jane.smith`) | `basicauth.go:48` failed `"developer"` → `ldap.go:131` searching → `ldap.go:148` found dn= → `ldap.go:152` **error binding password … LDAP Result Code 49 "Invalid Credentials"** → `basicauth.go:48` failed `"ldap-local"` |
| **LDAP gate-denied** (`bob.wilson` — a real user, not in the login-gate group) | `basicauth.go:48` failed `"developer"` → `ldap.go:131` searching → `ldap.go:139` **no entries matching** → `basicauth.go:48` failed `"ldap-local"` |
| **unknown user** (`nosuchuser`) | `basicauth.go:48` failed `"developer"` → `ldap.go:131` searching → `ldap.go:139` **no entries matching** → `basicauth.go:48` failed `"ldap-local"` |
| **HTPasswd success** (`developer`) | `basicauth.go:51` **succeeded** for `"developer"` — and **nothing else** |

### Rule 1 — a `failed` line is not a failed login

Every provider tried *before* the matching one logs a failure. A **successful** LDAP login therefore
contains `Login with provider "developer" failed for login "john.doe"`. Counting `failed` lines counts
provider-order noise:

```
16:15:27.435 basicauth.go:48] Login with provider "developer" failed for login "john.doe"
16:15:27.535 basicauth.go:51] Login with provider "ldap-local" succeeded for login "john.doe"
```

**The outcome of an attempt is a property of the whole group of lines for that username, not of any one
line.** Group by `login "<user>"` within a short window (the four cases above spanned ~30 ms each) and
the attempt succeeded if *any* provider succeeded.

### Rule 2 — an HTPasswd login writes no failure line at all

`developer` matches the first provider, so there is no preceding failure. Whether the noise exists is
**provider-order dependent**, which means a parser cannot assume a fixed shape per attempt.

### Rule 3 — the provider name separates real users from break-glass accounts

`provider "ldap-local"` is a directory identity; `provider "developer"` on a *success* is HTPasswd —
`developer`, `kubeadmin`. Neither belongs in a governance view, and this is the field that excludes them.

### Rule 4 — a wrong password IS distinguishable; a denial IS NOT

Only the bad-password path writes a reason, and it carries an LDAP result code:

```
ldap.go:152] error binding password for "uid=jane.smith,ou=People,dc=ephico2real,dc=com":
             LDAP Result Code 49 "Invalid Credentials"
```

But **gate-denied and unknown-user are byte-identical.** Both produce only `ldap.go:139] no entries
matching (<filter>)`, because the identity provider's filter includes the group gate — so a real person
refused by policy and a username that does not exist are the same event as far as the log is concerned:

```
bob.wilson   ldap.go:139] no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,...))(uid=bob.wilson))
nosuchuser   ldap.go:139] no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,...))(uid=nosuchuser))
```

This does **not** limit what to capture — it limits how precisely one failure can be *labelled*.
Distinguishing the two would need a second LDAP search without the gate clause, which is a directory read
the dashboard does not have and should not acquire, so they share one bucket: **"rejected — user not
found or not permitted"**. Both are still captured, against the username that was attempted.

So the outcomes a parser can honestly report are:

| outcome | how it is identified |
|---|---|
| success | `basicauth.go:51 … succeeded` for any provider |
| wrong password | `ldap.go:152` with `LDAP Result Code 49` |
| rejected — not found **or** not permitted | `ldap.go:139 … no entries matching`, and no success for that user in the window |

### Rule 5 — the `ldap.go` lines carry the directory's shape

`ldap.go:131/139/148` embed the **full bind filter** and `ldap.go:148/152` the **user's full DN**. That is
more sensitive than the username alone: the filter discloses the gate group's DN and the directory
layout. Anything parsed out of these lines should store the username and the outcome, **not** the raw
line, and the raw line must never reach a log the dashboard itself writes.

### Timestamps

Two stamps per line, and only one is usable: the kubelet's RFC3339 prefix (`2026-08-07T16:15:27.435Z`,
present because of `?timestamps=true`) and klog's own (`I0807 16:15:27.435262`), which carries **no year
and no timezone**. Use the kubelet prefix. It is UTC and it is what makes cluster-wide correlation valid
when the nodes are NTP-synced (`chrony` via MachineConfig).

## Checking the grants directly

```bash
SA=system:serviceaccount:group-sync-dashboard:group-sync-dashboard
oc auth can-i list pods -n openshift-authentication --as=$SA              # yes
oc auth can-i get pods --subresource=log -n openshift-authentication --as=$SA   # yes
oc auth can-i get pods --subresource=log -n kube-system --as=$SA          # no
oc auth can-i patch authentications.operator.openshift.io/cluster --as=$SA     # no
```

> **`oc auth can-i get pods/log` returns `no` even when the grant is correct.** It parses `pods/log` as
> a resource *name*. Use `--subresource=log`. This false negative nearly got a working grant "fixed"
> during development.

The write lives on a different identity, and stays there:

```bash
JSA=system:serviceaccount:group-sync-dashboard:group-sync-dashboard-auth-loglevel
oc auth can-i patch authentications.operator.openshift.io/cluster --as=$JSA    # yes
oc auth can-i get deploy/oauth-openshift -n openshift-authentication --as=$JSA # yes
oc auth can-i get deploy -n kube-system --as=$JSA                        # no
oc auth can-i get pods --subresource=log -n openshift-authentication --as=$JSA # no
```

## If you see nothing

In the order worth checking:

| symptom | cause |
|---|---|
| no `succeeded for login` lines at all | `logLevel` is `Normal`, or `--v=` is still `2` — the line was never written, and past logins cannot be recovered |
| lines exist, dashboard shows nothing | the read grant: `loginCapture.enabled` false, or the Role is in the wrong namespace |
| `403` reading `pods/log` | the RoleBinding names the wrong ServiceAccount, or the wrong namespace on the subject |
| a login you just made is missing | it landed during the oauth roll — the pod serving it was replaced, and **logs die with the pod** |
| the level flipped back on its own | somebody ran `helm upgrade` without `-f`, reverting `authLogLevel.enabled` to the chart default |

**Logs die with the pod, and this is the limitation to state out loud rather than design around.** A
capture that reads pod logs can only see what the *current* pods still hold. Every oauth roll — every
cluster upgrade, every node drain, every one of these level toggles — starts the window again. A
continuous reader accumulates its own durable record going forward, but the record before capture was
enabled does not exist and cannot be reconstructed.
