# SPEC_D2b §5 Step 0, verbatim, with the scratch kubeconfig and a fixed WALK directory (a scratch dir outside the worktree).
export KUBECONFIG=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/kc-crc
NS=group-sync-dashboard; APP=group-sync-dashboard; ARGO_NS=openshift-gitops
WALK=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk
PY=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
cd /Users/olasumbo/gitRepos/group-sync-dashboard
pod() { oc get pods -n "$NS" -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | head -1; }
api_as() { oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -H "X-Forwarded-User: $1" "http://127.0.0.1:8080$2"; }
code_as() { oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -o /dev/null -w '%{http_code}' -H "X-Forwarded-User: $1" "http://127.0.0.1:8080$2"; }
resolved() { oc logs -n "$NS" "$(pod)" -c dashboard | grep cluster-resolved | grep "cluster=$1 " | tail -1; }
traffic() {  # traffic <seconds>: kubeadmin, jane.smith and developer ask /api/whoami at once, each in its own loop
  end=$(( $(date +%s) + $1 ))
  for u in kubeadmin jane.smith developer; do
    ( while [ "$(date +%s)" -lt "$end" ]; do api_as "$u" /api/whoami >/dev/null; done ) &
  done
  wait
}
