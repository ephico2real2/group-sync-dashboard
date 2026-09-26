"""Error-response helpers that reach kube.py's tolerated branches deliberately.

* ``forbidden_403(path)`` — a 403 whose body carries the path. kube.py's ``_get`` builds a
  FORBIDDEN message that ALWAYS contains the path (``f"403 Forbidden on {path} …"``), so the
  ``FORBIDDEN and path in exc.message`` guard is satisfied by construction; we include the path
  in the body too, for realism and for any caller that inspects it.
* ``crd_absent_404(path)`` — a plain 404. kube.py's ``_get`` builds ``f"HTTP 404 on {path}: …"``
  which STARTS WITH ``"HTTP 404 on <path>"``, the anchor the CRD-absent branches match on.
* ``status_json`` — the Kubernetes Status body used by these error responses.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from .responses import status_json


def forbidden_403(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=status_json(
            403,
            "Forbidden",
            f"forbidden: User cannot list resource on path {path} "
            f"(the mock fixture marks this endpoint forbidden)",
        ),
    )


def crd_absent_404(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=status_json(
            404,
            "NotFound",
            f"the server could not find the requested resource ({path})",
        ),
    )


def unauthorized_401() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=status_json(401, "Unauthorized", "Unauthorized: bearer token missing or invalid"),
    )


def not_found_404(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=status_json(404, "NotFound", f"no route registered for {path}"),
    )
