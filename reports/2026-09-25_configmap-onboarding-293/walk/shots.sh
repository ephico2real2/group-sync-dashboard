export KUBECONFIG=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/kc-crc
D=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/deploy293
P=$(oc get pods -n group-sync-dashboard -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | head -1)
oc port-forward -n group-sync-dashboard "$P" 18084:8080 >/dev/null 2>&1 & PF=$!; sleep 4
/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python - "$D" "$1" <<'PY'
import sys
from playwright.sync_api import sync_playwright
out, step = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_context(extra_http_headers={"X-Forwarded-User": "kubeadmin"}, viewport={"width": 1440, "height": 1000}, color_scheme="light").new_page()
    pg.goto("http://127.0.0.1:18084/#page=clusters&cluster=dashboard"); pg.wait_for_timeout(4000)
    pg.screenshot(path=f"{out}/{step}-cluster-configurations.png", full_page=True)
    body = " ".join(pg.locator("body").inner_text().split())
    for k in ("cm-demo-a", "cm-demo-b", "cm-demo-dup", "cm-demo-cred", "cluster-onboarding"):
        i = body.find(k); print(f"   page {step}: {k!r}", "absent" if i < 0 else "present: " + body[max(i-40,0):i+120])
    br.close()
PY
kill $PF
