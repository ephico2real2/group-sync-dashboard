#!/bin/bash
# Epic A (#381) walk on chart 0.58.3: the Cluster Configurations tab before, with, and after a cluster added by the
# committed GitOps onboarding example (#389), plus the docs index (#319) as GitHub renders it. Read-only except the
# throwaway ConfigMap it applies and deletes.
set -uo pipefail
export KUBECONFIG=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/kc-crc
E=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk-epicA
PY=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
REPO=/Users/olasumbo/gitRepos/group-sync-dashboard
NS=group-sync-dashboard
SHA=$(git -C "$REPO" rev-parse HEAD)
CLUSTER=gitops-example-389

shot() {  # shot <file-stem>: the Cluster Configurations tab, full page, through the dashboard container's port
  local P; P=$(oc get pods -n $NS -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | grep -v report | head -1)
  oc port-forward -n $NS "$P" 18085:8080 >/dev/null 2>&1 & local PF=$!; sleep 4
  "$PY" - "$E/$1.png" "$CLUSTER" <<'PYEOF'
import sys
from playwright.sync_api import sync_playwright
out, cluster = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 1000},
                        color_scheme="light").new_page()
    pg.goto("http://127.0.0.1:18085/#page=clusters&cluster=dashboard"); pg.wait_for_timeout(4000)
    pg.screenshot(path=out, full_page=True)
    body = " ".join(pg.locator("body").inner_text().split())
    i = body.find(cluster)
    print(f"  {out.rsplit('/', 1)[1]}: {cluster!r}", "absent" if i < 0 else "present: " + body[max(i - 60, 0):i + 160])
    br.close()
PYEOF
  kill $PF
}

echo "== image and chart"; oc get deployment group-sync-dashboard -n $NS -o jsonpath='{.metadata.labels.helm\.sh/chart} {.spec.template.spec.containers[0].image}{"\n"}'
echo "== 1 before"; shot 1-cluster-configurations-before

sed -e "s|name: cluster-onboarding|name: cluster-onboarding-epic-a|" -e "s|name: ocp-east|name: $CLUSTER|" \
    -e "s|https://api.ocp-east.example.com:6443|https://api.crc.testing:6443|" \
    "$REPO/examples/cluster-onboarding/configmap.yaml" > "$E/cm.yaml"
echo "== apply $(date -u +%FT%TZ)"; oc apply -f "$E/cm.yaml"
t0=$(date +%s); until oc get secret gsd-cluster-$CLUSTER -n $NS >/dev/null 2>&1 || [ $(( $(date +%s) - t0 )) -gt 420 ]; do sleep 15; done
echo "   secret after $(( $(date +%s) - t0 ))s: $(oc get secret gsd-cluster-$CLUSTER -n $NS -o jsonpath='{.metadata.annotations.groupsync-dashboard\.io/managed-by}' 2>&1)"
sleep 20   # one poll of the new cluster, so the row has data
echo "== 2 with the GitOps cluster"; shot 2-cluster-configurations-gitops-cluster-added

echo "== delete $(date -u +%FT%TZ)"; oc delete configmap cluster-onboarding-epic-a -n $NS
t0=$(date +%s); while oc get secret gsd-cluster-$CLUSTER -n $NS >/dev/null 2>&1 && [ $(( $(date +%s) - t0 )) -lt 420 ]; do sleep 15; done
echo "   secret gone after $(( $(date +%s) - t0 ))s: $(oc get secret gsd-cluster-$CLUSTER -n $NS 2>&1 | tail -1)"
echo "== 3 after"; shot 3-cluster-configurations-after-removal

echo "== 4 docs index at $SHA"
"$PY" - "$E/4-docs-index.png" "https://github.com/ephico2real2/group-sync-dashboard/blob/$SHA/docs/README.md" <<'PYEOF'
import sys
from playwright.sync_api import sync_playwright
out, url = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 1600}, color_scheme="light").new_page()
    pg.goto(url, wait_until="domcontentloaded"); pg.wait_for_selector("article.markdown-body", timeout=30000)
    pg.locator("article.markdown-body").screenshot(path=out)
    print("  4-docs-index.png:", pg.locator("article.markdown-body h1").first.inner_text())
    br.close()
PYEOF
echo "== done"
