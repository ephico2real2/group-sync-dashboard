"""The default Route must render with NO cluster and NO host — that is the whole reason it exists.

An Ingress needs a host at render time: a hostless Ingress produces no Route on OpenShift, so the
chart either takes ingress.host or reads the cluster's apps domain with `lookup`, and refuses to
render when it can do neither. ArgoCD renders with `helm template` and no cluster connection, so
under ArgoCD that refusal was unconditional. The Route moves host generation onto the cluster:
`spec.subdomain` names the host and the router reports it in status, and the ServiceAccount
references the Route by NAME instead of carrying a literal callback URL.

These shell out to `helm template` with NO `--set ingress.host` and NO `--set route.host`, on
purpose: that is exactly the render ArgoCD performs.

Measured on OpenShift 4.18.2 before this was written, in a scratch namespace:
    subdomain only        -> spec.host stays empty (also after re-apply); status host = <subdomain>.<domain>
    no host, no subdomain -> spec.host FILLED by the API server as <name>-<namespace>.<domain>
The second form appends the namespace and is the one ArgoCD reports OutOfSync (argo-cd#20305),
which is why the template emits `subdomain` and these tests pin that spec.host is ABSENT rather
than merely empty.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

INGRESS_ONLY = ("--set", "route.enabled=false", "--set", "ingress.enabled=true")
PROXY_OFF = ("--set", "oauthProxy.enabled=false", "--set", "visibility.enabled=false")


def render(*extra: str, release: str = "group-sync-dashboard", namespace: str = "group-sync-dashboard"):
    """Render the chart with no host and no cluster — the ArgoCD render. Returns (ok, output)."""
    args = ["helm", "template", release, str(CHART), "-n", namespace, *extra]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def objects(out: str) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(out) if doc]


def kinds(out: str) -> list[str]:
    return [o["kind"] for o in objects(out)]


def one(out: str, kind: str) -> dict:
    found = [o for o in objects(out) if o["kind"] == kind]
    assert len(found) == 1, f"expected exactly one {kind}, found {len(found)}"
    return found[0]


class TestTheDefaultIsARouteThatNeedsNoCluster:
    def test_the_default_renders_with_no_host_and_no_cluster(self):
        ok, out = render()
        assert ok, out

    def test_it_emits_a_route_and_no_ingress(self):
        ok, out = render()
        assert ok, out
        assert "Route" in kinds(out) and "Ingress" not in kinds(out)

    def test_the_route_is_named_like_the_service(self):
        """Release, Service and Route share one name, so the SA can reference the Route exactly."""
        ok, out = render()
        assert ok, out
        assert one(out, "Route")["metadata"]["name"] == one(out, "Service")["metadata"]["name"] == "group-sync-dashboard"

    def test_the_route_asks_for_the_fullname_as_a_subdomain_and_sets_no_host(self):
        """subdomain, and spec.host ABSENT — not empty. An empty host is filled by the API server
        as <name>-<namespace>, which appends the namespace and drifts under ArgoCD."""
        ok, out = render()
        assert ok, out
        spec = one(out, "Route")["spec"]
        assert spec["subdomain"] == "group-sync-dashboard"
        assert "host" not in spec
        assert "group-sync-dashboard-group-sync-dashboard" not in out

    def test_the_subdomain_is_the_fullname_not_the_release_name_when_they_differ(self):
        """A release not named after the chart gets <release>-<chart>, like every other object."""
        ok, out = render(release="gsd", namespace="x")
        assert ok, out
        assert one(out, "Route")["spec"]["subdomain"] == "gsd-group-sync-dashboard"

    def test_the_route_targets_the_service_by_its_named_port(self):
        """`http` in both proxy modes; only the Service's targetPort moves to the proxy. This is
        also what the ingress-to-route controller generated from the Ingress on the reference cluster."""
        ok, out = render()
        assert ok, out
        route, service = one(out, "Route"), one(out, "Service")
        assert route["spec"]["to"] == {"kind": "Service", "name": service["metadata"]["name"]}
        assert route["spec"]["port"]["targetPort"] == "http"
        assert [p["name"] for p in service["spec"]["ports"]] == ["http"]

    def test_tls_reencrypts_with_the_proxy_on_and_follows_the_value_with_it_off(self):
        ok, out = render()
        assert ok, out
        assert one(out, "Route")["spec"]["tls"] == {"termination": "reencrypt", "insecureEdgeTerminationPolicy": "Redirect"}
        ok, out = render(*PROXY_OFF)
        assert ok, out
        assert one(out, "Route")["spec"]["tls"]["termination"] == "edge"
        ok, out = render(*PROXY_OFF, "--set", "route.termination=passthrough")
        assert ok, out
        assert one(out, "Route")["spec"]["tls"]["termination"] == "passthrough"

    def test_an_empty_insecure_policy_is_omitted(self):
        ok, out = render("--set", "route.insecureEdgeTerminationPolicy=")
        assert ok, out
        assert "insecureEdgeTerminationPolicy" not in one(out, "Route")["spec"]["tls"]

    def test_route_annotations_land_on_the_route(self):
        ok, out = render("--set", "route.annotations.haproxy\\.router\\.openshift\\.io/timeout=60s")
        assert ok, out
        assert one(out, "Route")["metadata"]["annotations"] == {"haproxy.router.openshift.io/timeout": "60s"}

    def test_argocd_annotations_land_on_the_service_account_and_not_on_the_route(self):
        """Both halves in one render, so a regression that moves the annotation shows up."""
        ok, out = render("--set", "argocd.enabled=true")
        assert ok, out
        assert one(out, "ServiceAccount")["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "ServerSideApply=true"
        assert "argocd.argoproj.io/sync-options" not in (one(out, "Route")["metadata"].get("annotations") or {})

    def test_the_route_carries_no_argocd_sync_option(self):
        """Nothing in the Route's spec is server-populated, so there is no SSA fight to settle —
        and SSA on a Route is exactly what would strip a host the server chose."""
        ok, out = render("--set", "argocd.enabled=true")
        assert ok, out
        assert "argocd.argoproj.io/sync-options" not in (one(out, "Route")["metadata"].get("annotations") or {})


class TestADeliberateHostIsUsedAsGiven:
    def test_route_host_becomes_spec_host_and_replaces_the_subdomain(self):
        ok, out = render("--set", "route.host=gsd.apps.example.com")
        assert ok, out
        spec = one(out, "Route")["spec"]
        assert spec["host"] == "gsd.apps.example.com"
        assert "subdomain" not in spec

    def test_an_ingress_host_from_an_older_values_file_is_honoured(self):
        """Upgrading a release whose values pinned ingress.host must not silently move its URL."""
        ok, out = render("--set", "ingress.host=pinned.apps.example.com")
        assert ok, out
        assert one(out, "Route")["spec"]["host"] == "pinned.apps.example.com"

    def test_route_host_wins_over_ingress_host(self):
        ok, out = render("--set", "route.host=route.example.com", "--set", "ingress.host=ingress.example.com")
        assert ok, out
        assert one(out, "Route")["spec"]["host"] == "route.example.com"

    def test_the_service_account_still_references_the_route_when_the_host_is_pinned(self):
        """The reference resolves against whatever host the Route reports, so pinning changes nothing here."""
        ok, out = render("--set", "route.host=gsd.apps.example.com")
        assert ok, out
        ann = one(out, "ServiceAccount")["metadata"]["annotations"]
        assert "serviceaccounts.openshift.io/oauth-redirectreference.primary" in ann
        assert "serviceaccounts.openshift.io/oauth-redirecturi.primary" not in ann


class TestTheServiceAccountFollowsTheExposure:
    def test_route_uses_a_redirect_reference_naming_the_chart_route(self):
        ok, out = render()
        assert ok, out
        sa, route = one(out, "ServiceAccount"), one(out, "Route")
        ann = sa["metadata"]["annotations"]
        assert "serviceaccounts.openshift.io/oauth-redirecturi.primary" not in ann
        assert json.loads(ann["serviceaccounts.openshift.io/oauth-redirectreference.primary"]) == {
            "kind": "OAuthRedirectReference",
            "apiVersion": "v1",
            "reference": {"kind": "Route", "name": route["metadata"]["name"]},
        }

    def test_ingress_keeps_the_literal_redirect_uri(self):
        ok, out = render(*INGRESS_ONLY, "--set", "ingress.host=t.example.com")
        assert ok, out
        ann = one(out, "ServiceAccount")["metadata"]["annotations"]
        assert ann["serviceaccounts.openshift.io/oauth-redirecturi.primary"] == "https://t.example.com/oauth/callback"
        assert "serviceaccounts.openshift.io/oauth-redirectreference.primary" not in ann

    def test_no_service_account_means_no_reference_and_the_route_still_renders(self):
        ok, out = render("--set", "serviceAccount.create=false")
        assert ok, out
        assert "ServiceAccount" not in kinds(out) and "Route" in kinds(out)

    def test_with_the_proxy_off_neither_annotation_is_emitted(self):
        ok, out = render(*PROXY_OFF)
        assert ok, out
        ann = one(out, "ServiceAccount")["metadata"].get("annotations") or {}
        assert not any(k.startswith("serviceaccounts.openshift.io/oauth-redirect") for k in ann)


class TestTheIngressPathIsUnchanged:
    def test_ingress_only_emits_an_ingress_and_no_route(self):
        ok, out = render(*INGRESS_ONLY, "--set", "ingress.host=t.example.com")
        assert ok, out
        assert "Ingress" in kinds(out) and "Route" not in kinds(out)
        assert one(out, "Ingress")["spec"]["rules"][0]["host"] == "t.example.com"

    def test_ingress_only_still_refuses_to_render_without_a_host(self):
        """The Ingress guard is not weakened by the Route existing beside it."""
        ok, out = render(*INGRESS_ONLY)
        assert not ok
        assert "ingress.host is not set and the cluster apps domain could not be read" in out

    def test_the_refusal_names_the_route_as_the_way_out(self):
        ok, out = render(*INGRESS_ONLY)
        assert not ok
        assert "route.enabled=true" in out

    def test_the_ingress_termination_rule_is_unchanged(self):
        ok, out = render(*INGRESS_ONLY, "--set", "ingress.host=t.example.com")
        assert ok, out
        assert one(out, "Ingress")["metadata"]["annotations"]["route.openshift.io/termination"] == "reencrypt"
        ok, out = render(*INGRESS_ONLY, *PROXY_OFF, "--set", "ingress.host=t.example.com")
        assert ok, out
        assert one(out, "Ingress")["metadata"]["annotations"]["route.openshift.io/termination"] == "edge"


class TestTheRenderSurvivesHostileNames:
    def test_a_quote_in_the_fullname_still_yields_valid_json(self):
        """The reference used to be hand-built inside a single-quoted YAML scalar, so a quote in
        the name broke the render (Codex, #45). The API's own error for a bad name is the one the
        operator should see, not a YAML parse error from the chart."""
        ok, out = render("--set-string", "fullnameOverride=x'y\"z")
        assert ok, out
        ann = one(out, "ServiceAccount")["metadata"]["annotations"]
        ref = json.loads(ann["serviceaccounts.openshift.io/oauth-redirectreference.primary"])
        assert ref["reference"]["name"] == one(out, "Route")["metadata"]["name"] == "x'y\"z"

    def test_the_encoded_reference_is_the_same_json_for_an_ordinary_name(self):
        """Encoding must not change what a valid name means. toJson sorts keys, so the bytes differ
        from the hand-built form (kind first); the JSON is the same, and OpenShift parses it."""
        ok, out = render()
        assert ok, out
        ann = one(out, "ServiceAccount")["metadata"]["annotations"]
        assert ann["serviceaccounts.openshift.io/oauth-redirectreference.primary"] == (
            '{"apiVersion":"v1","kind":"OAuthRedirectReference","reference":{"kind":"Route","name":"group-sync-dashboard"}}'
        )


def _notes_probe_chart(tmp_root: pathlib.Path) -> pathlib.Path:
    """A copy of the chart whose NOTES.txt is rendered INTO a manifest, so `helm template` can
    show it. `helm template` drops NOTES, and `helm install --dry-run` — even `--dry-run=client` —
    still asks the cluster for its version and fails in CI, which is how the first version of
    these tests went red there while passing against a live CRC. The probe moves NOTES.txt out of
    templates/ (where .Files cannot see it) and renders it with `tpl` in the same context, so every
    helper and value resolves exactly as in the real NOTES."""
    probe = tmp_root / "probe-chart"
    shutil.copytree(CHART, probe)
    (probe / "files").mkdir()
    (probe / "templates" / "NOTES.txt").rename(probe / "files" / "NOTES.txt")
    (probe / "templates" / "notes-probe.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: notes-probe\ndata:\n"
        "  notes: {{ tpl (.Files.Get \"files/NOTES.txt\") . | toYaml | indent 4 | trim }}\n"
    )
    return probe


class TestTheNotesNameTheRightObject:
    @pytest.fixture(autouse=True)
    def _probe(self, tmp_path_factory):
        self.probe = _notes_probe_chart(tmp_path_factory.mktemp("notes"))

    def notes(self, *extra: str) -> str:
        done = subprocess.run(["helm", "template", "group-sync-dashboard", str(self.probe), "-n", "group-sync-dashboard",
                               "-s", "templates/notes-probe.yaml", *extra], capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        return one(done.stdout, "ConfigMap")["data"]["notes"]

    def test_route_notes_read_the_host_from_status(self):
        n = self.notes()
        assert "oc get route group-sync-dashboard -n group-sync-dashboard -o jsonpath='{.status.ingress[0].host}'" in n
        assert "oc get ingress" not in n

    def test_ingress_notes_read_the_host_from_the_rule(self):
        n = self.notes(*INGRESS_ONLY, "--set", "ingress.host=t.example.com")
        assert "oc get ingress group-sync-dashboard -n group-sync-dashboard -o jsonpath='{.spec.rules[0].host}'" in n
        assert "curl -sk https://t.example.com/api/version" in n

    def test_a_carried_over_ingress_host_is_called_out_with_its_origin(self):
        """Both reviewers of #45 named the edge: the chart cannot tell a pinned host from one set
        only because the Ingress demanded it. The fallback stays, but it is not silent."""
        n = self.notes("--set", "ingress.host=old.example.com")
        assert "came from ingress.host" in n and "old.example.com" in n
        assert "move it to route.host" in n
        assert "came from ingress.host" not in self.notes("--set", "route.host=pinned.example.com")
        assert "came from ingress.host" not in self.notes()

    def test_the_unauthenticated_warning_names_the_object_that_is_exposed(self):
        assert "WARNING: the Route has NO authentication" in self.notes(*PROXY_OFF)
        assert "WARNING: the Ingress has NO authentication" in self.notes(*INGRESS_ONLY, *PROXY_OFF, "--set", "ingress.host=t.example.com")


class TestTheFlagsAreValidatedTogether:
    def test_both_on_fails_the_render(self):
        """Two objects claiming one hostname; the second sits refused with HostAlreadyClaimed."""
        ok, out = render("--set", "ingress.enabled=true", "--set", "ingress.host=t.example.com")
        assert not ok
        assert "route.enabled and ingress.enabled are both true" in out

    def test_neither_on_emits_neither_object(self):
        """Bring-your-own exposure; with the proxy on the SA still needs a literal callback host."""
        ok, out = render("--set", "route.enabled=false", "--set", "ingress.host=t.example.com")
        assert ok, out
        assert "Route" not in kinds(out) and "Ingress" not in kinds(out)
        ann = one(out, "ServiceAccount")["metadata"]["annotations"]
        assert ann["serviceaccounts.openshift.io/oauth-redirecturi.primary"] == "https://t.example.com/oauth/callback"

    def test_neither_on_with_the_proxy_on_and_no_host_is_refused(self):
        ok, out = render("--set", "route.enabled=false")
        assert not ok
        assert "ingress.host is not set" in out

    def test_neither_on_with_the_proxy_off_needs_no_host_at_all(self):
        """No object to expose and no callback to advertise: nothing needs the host."""
        ok, out = render("--set", "route.enabled=false", *PROXY_OFF)
        assert ok, out
        assert "Route" not in kinds(out) and "Ingress" not in kinds(out)

    def test_the_both_flags_error_says_it_is_a_policy_and_names_both_ways_out(self):
        ok, out = render("--set", "ingress.enabled=true", "--set", "ingress.host=t.example.com")
        assert not ok
        assert "as a policy" in out
        assert "route.enabled=true is the OpenShift default" in out
        assert "ingress.enabled=true is for plain Kubernetes" in out
