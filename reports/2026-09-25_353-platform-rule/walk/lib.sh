# #353 evidence helpers: the scratch kubeconfig only; nothing here changes the shared context.
export KUBECONFIG=<the scratch kubeconfig>
NS=group-sync-dashboard; APP=group-sync-dashboard; ARGO_NS=openshift-gitops
W=<the scratch folder this run wrote to>
pod() { oc get pods -n "$NS" -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | head -1; }
api_as() { oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -H "X-Forwarded-User: $1" "http://127.0.0.1:8080$2"; }
pvcs() { oc get pvc -n "$NS" -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,VOL:.spec.volumeName,CREATED:.metadata.creationTimestamp' | grep -E 'NAME|group-sync-dashboard-(data|report-artifacts)'; }
argo() { oc get application -n "$ARGO_NS" "$APP" -o jsonpath='{.status.sync.status} {.status.health.status} {.status.sync.revision}{"\n"}'; }
schema() { oc exec -n "$NS" "$(pod)" -c dashboard -- python3 -c "import sqlite3; c=sqlite3.connect('file:/data/gsd.db?mode=ro', uri=True); print('user_version', c.execute('PRAGMA user_version').fetchone()[0]); print('rbac_group_binding columns', [r[1] for r in c.execute('PRAGMA table_info(rbac_group_binding)')])"; }
