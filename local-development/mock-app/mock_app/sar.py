"""A faithful-enough RBAC authorizer for the SubjectAccessReview endpoint (DESIGN §5).

kube.py posts a SubjectAccessReview whose ``spec.groups`` is ALREADY the union of the viewer's
resolved OpenShift Group memberships and the virtual ``system:*`` groups — the client resolves
membership upstream in ``fetch_groups_of_user`` (endpoint b). So this authorizer does NOT
resolve membership; it takes ``spec.user`` + ``spec.groups`` as the subject set and evaluates
the fixture's ``(Cluster)RoleBinding`` → ``(Cluster)Role`` rules against
``spec.resourceAttributes``.

Only ``status.allowed`` is read by the client, and it must be a real JSON boolean; this class
therefore always returns a plain ``bool`` and never raises for a well-formed body. The four
measured personas resolve to their measured tiers from the reference fixture — that is the
acceptance oracle (DESIGN §5.4), not a hardcoded answer map.
"""

from __future__ import annotations

from .fixture import Binding, Fixture, Role, Rule, Subject


class SarAuthorizer:
    def __init__(self, fixture: Fixture):
        self._fx = fixture
        self._cluster_roles: dict[str, Role] = {r.name: r for r in fixture.cluster_roles}
        # Namespaced roles keyed by (namespace, name).
        self._namespaced_roles: dict[tuple[str, str], Role] = {
            (r.namespace, r.name): r for r in fixture.namespaced_roles
        }

    # ── public ────────────────────────────────────────────────────────────────────────────

    def review(self, user: str, groups: list[str], attrs: dict) -> bool:
        """Return whether the subject may perform ``attrs`` — a real bool, never raises."""
        allowed, _ = self.explain(user, groups, attrs)
        return allowed

    def explain(self, user: str, groups: list[str], attrs: dict) -> tuple[bool, str | None]:
        """``(allowed, granting_binding_name_or_None)`` — for the /_mock/ SAR probe too."""
        verb = attrs.get("verb", "")
        resource = attrs.get("resource", "")
        api_group = attrs.get("group", "")          # the k8s field name is "group", not "apiGroup"
        namespace = attrs.get("namespace")          # None/"" → cluster-scoped check
        subresource = attrs.get("subresource")      # None/"" → bare resource

        group_set = set(groups)

        # Cluster-scoped bindings are ALWAYS considered. clusterrolebindings is itself
        # cluster-scoped, so a namespaced RoleBinding can never grant it (DESIGN §5.2.2).
        candidate_bindings: list[tuple[Binding, str]] = [
            (b, "ClusterRoleBinding") for b in self._fx.cluster_role_bindings
        ]
        if namespace:
            candidate_bindings += [
                (b, "RoleBinding")
                for b in self._fx.role_bindings
                if b.namespace == namespace
            ]

        for binding, binding_kind in candidate_bindings:
            if not self._subject_intersects(binding.subjects, user, group_set):
                continue
            role = self._resolve_role(binding, binding_kind, namespace)
            if role is None:
                continue
            for rule in role.rules:
                if self._rule_matches(rule, verb, api_group, resource, subresource):
                    return True, binding.name
        return False, None

    # ── internals ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _subject_intersects(subjects: tuple[Subject, ...], user: str, group_set: set[str]) -> bool:
        for s in subjects:
            if s.kind == "User" and s.name == user:
                return True
            if s.kind == "Group" and s.name in group_set:
                return True
            # A ServiceAccount subject is written as kind: ServiceAccount (name + namespace), NOT as a
            # User of its system: name — so it must be expanded to the canonical username the SA
            # authenticates as. Real RBAC binds `system:serviceaccount:<ns>:<name>` (review #118 C3).
            if s.kind == "ServiceAccount" and s.namespace and s.name:
                if user == f"system:serviceaccount:{s.namespace}:{s.name}":
                    return True
        return False

    def _resolve_role(self, binding: Binding, binding_kind: str, namespace: str | None) -> Role | None:
        ref = binding.role_ref
        if ref.kind == "ClusterRole":
            return self._cluster_roles.get(ref.name)
        if ref.kind == "Role":
            # A namespaced Role is scoped to the binding's own namespace.
            return self._namespaced_roles.get((binding.namespace, ref.name))
        return None

    @staticmethod
    def _rule_matches(
        rule: Rule, verb: str, api_group: str, resource: str, subresource: str | None
    ) -> bool:
        # resourceNames caveat: a rule that names specific objects does NOT grant an
        # unqualified verb (the SAR carries no object name — the admin default is `list`, the
        # usage default is `update`, neither names an object). cluster-admin carries none.
        if rule.resourceNames:
            return False
        if not (verb in rule.verbs or "*" in rule.verbs):
            return False
        # Empty api_group is the CORE group — matched literally, never treated as unset.
        if not (api_group in rule.apiGroups or "*" in rule.apiGroups):
            return False
        return SarAuthorizer._resource_matches(rule.resources, resource, subresource)

    @staticmethod
    def _resource_matches(resources: tuple[str, ...], resource: str, subresource: str | None) -> bool:
        target = f"{resource}/{subresource}" if subresource else resource
        for r in resources:
            if r == "*":            # cluster-admin's ["*"] matches everything, subresources too
                return True
            if r == target:
                return True
        # A rule scoped to "resource/sub" does NOT grant the bare resource, and a rule for the
        # bare resource does NOT grant a subresource — both fall through to False here.
        return False
