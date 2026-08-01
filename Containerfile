# Two stages so the wheel-build toolchain never reaches the runtime image.
FROM registry.access.redhat.com/ubi9/python-311:latest AS build

USER 0
WORKDIR /build

COPY pyproject.toml README.md ./
COPY gsd ./gsd

# Build a wheel and resolve dependencies into a self-contained prefix, so the runtime
# stage needs no compiler and no package index.
RUN python -m pip install --no-cache-dir --upgrade pip build \
 && python -m build --wheel --outdir /wheels \
 && python -m pip install --no-cache-dir --prefix=/install /wheels/*.whl


# ubi9-minimal + python3.11 rather than the s2i python image: no build toolchain, no
# assemble scripts. (There is no ubi9/python-311-minimal — that tag does not exist.)
FROM registry.access.redhat.com/ubi9-minimal:latest

# OpenShift runs containers as an arbitrary high UID in the root group, not as the UID the
# image declares. Anything the process writes at runtime must therefore be group-writable
# and group-owned by root — the SQLite file included.
# Both lib AND lib64: RHEL splits purelib from platlib, so every compiled wheel
# (pydantic_core, uvloop, httptools, _yaml) lands in lib64 while the pure-Python packages
# land in lib. Listing only lib imports pydantic but not pydantic_core.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/install/lib/python3.11/site-packages:/install/lib64/python3.11/site-packages \
    GSD_CONFIG=/etc/gsd/clusters.yaml \
    GSD_DB_PATH=/data/gsd.db \
    GSD_LOG_LEVEL=INFO
#   GSD_LOG_LEVEL: DEBUG | INFO | WARNING | ERROR | CRITICAL
#   Set explicitly rather than left to the code default so it is discoverable in
#   `podman inspect` / `oc set env --list` — an env var nobody knows exists is not a
#   feature. DEBUG adds per-poll timing, HTTP request lines, page counts and the
#   countdown to the next binding refresh; it is safe to leave on briefly but is chatty
#   at one line or more per poll per cluster.

USER 0
RUN microdnf install -y python3.11 \
 && microdnf clean all \
 && rm -rf /var/cache/yum

COPY --from=build /install /install

RUN mkdir -p /data /etc/gsd \
 && chgrp -R 0 /data /etc/gsd \
 && chmod -R g=u /data /etc/gsd

# A non-root default so the image is also safe to run outside OpenShift, where no
# arbitrary UID is assigned.
USER 1001

EXPOSE 8080
VOLUME ["/data"]

# Readiness is deliberately not gated on a reachable cluster: an unreachable cluster is a
# thing this dashboard exists to display, so failing readiness for one would take the
# dashboard down exactly when it has something to report.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python3.11", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"]

# `python3.11 -m uvicorn`, not the /install/bin/uvicorn console script: that script's
# shebang points at the *build* stage's interpreter path, which does not exist here.
# Single worker on purpose — the poller runs in-process and owns the SQLite store, so a
# second worker would mean two pollers racing on the same file and duplicate observations.
CMD ["python3.11", "-m", "uvicorn", "gsd.api:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
