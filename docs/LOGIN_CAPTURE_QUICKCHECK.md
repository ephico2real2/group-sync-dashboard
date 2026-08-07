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
  --set authLogLevel.manage=true --set authLogLevel.enabled=true \
  --set loginCapture.enabled=true
```

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
  --set authLogLevel.manage=true --set authLogLevel.enabled=false \
  --set loginCapture.enabled=true
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

Two things measured on both authentication paths, which a parser has to respect.

**The provider name is the discriminator.**

| login | line |
|---|---|
| LDAP user | `Login with provider "ldap-local" succeeded for login "john.doe"` |
| htpasswd / break-glass | `Login with provider "developer" succeeded for login "developer"` |

So `developer` and `kubeadmin` are distinguishable from real directory users, which matters because
neither belongs in a governance view.

**`failed for login` is not a failed login.** Provider order decides whether one appears:

- An **LDAP** login logs `failed for login` **first** — htpasswd is tried before ldap and rejects it —
  then `succeeded`. Measured 1 failed : 1 succeeded for a *single successful* login.
- An **htpasswd** login matches the first provider and logs **no** failure line at all.

A parser keying on `failed` therefore reports a phantom failure for every LDAP user and none for local
users. Key on `succeeded for login`, and treat `failed` as unreliable unless you also track which
provider emitted it.

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
