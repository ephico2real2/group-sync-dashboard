# Tutorial — CA trust in containers: OpenSSL's hashed directory, and three ways to use it on OpenShift

For an engineer who has seen `x509: certificate signed by unknown authority` and wants to
understand, not just work around, how a container decides which certificate authorities to
trust. Everything here was run on CRC (OpenShift 4.x with cert-manager 1.19 installed) on
2026-09-04, and every expected output shown is what actually came back.

What you will be able to do afterwards:

1. Explain what `/etc/pki/tls/certs/7886c608.0` is, how OpenSSL finds it, and why the number
   after the dot matters.
2. Make a container trust the cluster's own trust store (OpenShift's injected bundle).
3. Make a container trust a CA you created by hand.
4. Make a container trust a CA that cert-manager created, for a service whose certificate
   cert-manager issues.
5. Have Kyverno do all of it for every namespace that opts in — the enterprise way.
6. Diagnose the ways this goes wrong.

**What you need**: `oc` logged in with rights to create a project, `openssl` on your machine,
cert-manager on the cluster (`oc get crd certificates.cert-manager.io`) and, for 3.5, Kyverno
(`oc get crd clusterpolicies.kyverno.io`; this run used Kyverno 1.16.1). Every YAML in this
tutorial is applied with `cat <<EOF | oc apply -f -` so you can paste it as it stands; blocks
that substitute a shell variable use an unquoted `EOF`, blocks that must be taken literally use
`'EOF'`.

---

## Part 1 — The theory: how OpenSSL finds a CA

### 1.1 The problem a trust store solves

When a client verifies a server's certificate it has to walk a chain: the server's certificate
names its issuer, the issuer's certificate names *its* issuer, and so on up to a root the client
already trusts. Each link is a lookup by **subject name** — a distinguished name such as
`C=NG, O=Example Corp, CN=Example Corp Internal Root CA`. So a trust store must answer one
question quickly: *give me the certificate whose subject is this name.*

OpenSSL has two kinds of store:

| Store | How it is read | Where it usually is |
|---|---|---|
| a **bundle file** (`cafile`) | the whole file is parsed into memory when the context is created | `/etc/pki/tls/cert.pem`, `/etc/ssl/certs/ca-bundle.crt`, `/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem` |
| a **hashed directory** (`capath`) | one file at a time, on demand; **the file name is the index** | `/etc/pki/tls/certs/` |

The directory form is the subject of this tutorial. It is what makes "drop one file in and the
CA is trusted" possible without rebuilding a bundle.

### 1.2 The file name is a hash of the subject name

OpenSSL takes the subject name in its canonical DER form (case and whitespace normalised),
hashes it with SHA-1, and uses the first four bytes as a little-endian 32-bit number, printed as
eight lowercase hex digits. That is exactly what this prints:

```bash
openssl x509 -noout -subject_hash -in ca.crt
```

For the CA generated in Part 2 it prints `7886c608`. Two different OpenSSL builds agree, because
the algorithm is specified: the same certificate hashed to `7886c608` on macOS OpenSSL 3.6 and on
the container's OpenSSL 3.5. Before OpenSSL 1.0.0 the hash was MD5-based; that older value is
still printed by `-subject_hash_old` (`bac1f22a` for the same CA), and old distributions kept
both links per certificate so both generations of OpenSSL could find it.

### 1.3 The lookup, and the number after the dot

Given an issuer name to find, OpenSSL computes the hash and opens `<capath>/<hash>.0`. It loads
every certificate in that file into the store and checks whether one has the subject it wants.
If not, it opens `<hash>.1`, then `<hash>.2`, and so on — **and stops at the first number that
does not exist.** Four consequences follow, and each one was demonstrated in Part 3:

| Rule | Why | What you see if you break it |
|---|---|---|
| Numbering starts at `.0` and is contiguous | the lookup stops at the first missing number | a file named `<hash>.1` with no `.0` beside it is never opened (measured: `curl` exit 60) |
| The suffix exists for collisions | two different subject names can hash to the same 32 bits, and one subject can have two certificates (a re-keyed root, a cross-signed one) | if the directory already has `<hash>.0` for another CA, yours must be `.1` — replacing `.0` would shadow the other CA |
| One CA per file | a file is opened only when the name being looked up hashes to *that* file's name | a correct CA saved under the wrong hash is never opened (measured: `deadbeef.0`, exit 60) |
| A bundle cannot be dropped in as one file | same reason: only the certificate whose subject matches the file name is ever found | a 149-certificate cluster bundle named `<hash>.0` serves exactly one CA |

### 1.4 Where the entries come from

Nobody writes these names by hand. `openssl rehash` (older name `c_rehash`) walks a directory and
creates one symlink per certificate, named by its hash. RHEL-family systems, including Red Hat's
hardened images, go one step further: `update-ca-trust extract`, through p11-kit, generates both
the bundle files and the hashed directory from a single trust source under
`/etc/pki/ca-trust/`. Measured on the hardened `hi/python:3.14` image:

```text
/etc/pki/ca-trust/extracted/pem/
  README
  directory-hash/        438 entries — the per-CA PEM files
  email-ca-bundle.pem
  objsign-ca-bundle.pem
  tls-ca-bundle.pem      223752 bytes — the bundle curl reads
/etc/pki/tls/certs/      292 entries, every one a symlink into directory-hash/
/etc/ssl/certs/ca-bundle.crt -> /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
/etc/ssl/cert.pem            -> /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
```

Keep that layout in mind for Part 3.1: mounting something *over* `/etc/pki/ca-trust/extracted/pem`
hides `directory-hash/`, and every one of those 292 links then points at nothing.

### 1.5 Who consults the directory, and who does not

OpenSSL's default verify locations are a file *and* a directory. Which one a program reads
depends on how it was built and what it was told:

| Client | Reads the hashed directory? | Reads a bundle file? |
|---|---|---|
| Python's `ssl.create_default_context()`, and so `urllib` | yes — `capath=/etc/pki/tls/certs` is the compiled default | yes, `cafile=/etc/pki/tls/cert.pem` if it exists |
| curl | **only when told**: `--capath DIR` or `SSL_CERT_DIR=DIR` | yes — its compiled-in bundle (`/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem` on RHEL-family), or `--cacert FILE` / `CURL_CA_BUNDLE=FILE` |
| Python `httpx` / `requests` with defaults | no | their own `certifi` bundle; `requests` also reads `REQUESTS_CA_BUNDLE` |
| Go programs | no | the system bundle, or `SSL_CERT_FILE` / `SSL_CERT_DIR` |

Two variables therefore matter in Part 3. `SSL_CERT_DIR` names a hashed directory and is read by
every OpenSSL client and by curl; setting it to `/etc/pki/tls/certs`, which is already OpenSSL's
default, changes nothing for Python and makes curl read the directory too. `SSL_CERT_FILE` names a
bundle and is read by everyone — which is why it is dangerous when the file can be empty (see
Part 4).

**One curl rule that this tutorial found the hard way**: curl reads `SSL_CERT_DIR` (and
`SSL_CERT_FILE`) **only when `CURL_CA_BUNDLE` is not set**. With both set, `curl -v` names only
the `CAfile` and the hashed directory is never consulted — measured on curl 7.76 (UBI 9) and
curl 8.22 (the hardened image). So environment variables can give curl one store or the other,
never both. The way to name both is curl's own configuration file, `.curlrc`, found through
`CURL_HOME`:

```text
cacert = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
capath = /etc/pki/tls/certs
```

With that file `curl -v` reports both `CAfile` and `CApath`, and nothing but the curl tool reads
it — Python, libcurl users and the application's own TLS are untouched. Parts 3.5 and 3.6 use it.

---

## Part 2 — Hands on, locally: make a CA and watch the hash

Create a private CA and a server certificate signed by it. The configuration files are written
with heredocs so the whole thing is reproducible.

```bash
mkdir -p ~/ca-tutorial && cd ~/ca-tutorial

cat > ca.cnf <<'EOF'
[ req ]
distinguished_name = dn
x509_extensions    = ca_ext
prompt             = no
[ dn ]
C  = NG
O  = Example Corp
CN = Example Corp Internal Root CA
[ ca_ext ]
basicConstraints       = critical, CA:TRUE, pathlen:1
keyUsage               = critical, keyCertSign, cRLSign
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF
openssl req -x509 -new -newkey rsa:3072 -nodes -days 3650 -config ca.cnf -keyout ca.key -out ca.crt

cat > server.cnf <<'EOF'
[ req ]
distinguished_name = dn
req_extensions     = srv_ext
prompt             = no
[ dn ]
CN = server.ca-tutorial.svc
[ srv_ext ]
subjectAltName   = DNS:server.ca-tutorial.svc, DNS:server.ca-tutorial.svc.cluster.local, DNS:server
extendedKeyUsage = serverAuth
keyUsage         = critical, digitalSignature, keyEncipherment
EOF
openssl req -new -newkey rsa:2048 -nodes -config server.cnf -keyout server.key -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 365 \
  -extfile server.cnf -extensions srv_ext -out server.crt
openssl verify -CAfile ca.crt server.crt        # server.crt: OK
```

Now the hash, and a hashed directory of your own:

```bash
openssl x509 -noout -subject      -in ca.crt   # subject=C=NG, O=Example Corp, CN=Example Corp Internal Root CA
openssl x509 -noout -subject_hash -in ca.crt   # 7886c608
HASH=$(openssl x509 -noout -subject_hash -in ca.crt)

mkdir -p capath && cp ca.crt capath/$HASH.0
openssl verify -CApath capath server.crt       # server.crt: OK  — found through the directory

mv capath/$HASH.0 capath/$HASH.1
openssl verify -CApath capath server.crt       # error server.crt: verification failed — .1 with no .0 is never opened
rm capath/$HASH.1
```

Now let `openssl rehash` do the naming, which is what distributions run. It scans a directory
for files ending in `.pem`, `.crt`, `.cer` or `.crl` and creates one symlink per certificate,
`HHHHHHHH.D` (and `HHHHHHHH.rD` for revocation lists), numbering from `.0` and taking the next
number on a collision. A file that does not carry one of those extensions is ignored, which is
why the `$HASH.0` copy above would not have been linked:

```bash
cp ca.crt capath/example-corp-ca.pem
openssl rehash capath
ls -l capath
# 7886c608.0 -> example-corp-ca.pem
# example-corp-ca.pem
openssl verify -CApath capath server.crt       # server.crt: OK
```

`openssl rehash -v` prints each link as it makes it (`link example-corp-ca.pem -> 7886c608.0`);
`-old` adds the MD5-era names for pre-1.0.0 OpenSSL, which nothing current needs.

That is the entire mechanism. Everything on OpenShift is about getting one file to land at
`/etc/pki/tls/certs/<hash>.0` inside a container, or getting a bundle to where a program already
reads one.

---

## Part 3 — On OpenShift

Everything below lives in one project so it can be deleted in one command at the end.

```bash
oc new-project ca-tutorial
```

### 3.0 A TLS server to test against

Two servers will be used: one with a certificate from the CA you made in Part 2, one with a
certificate cert-manager issues in 3.3. Both run the same tiny HTTPS server. It answers
`hello over TLS from <name>`, which is the string every check below looks for.

```bash
cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: tls-server-script
data:
  server.py: |
    # A minimal HTTPS server for the tutorial: serves "hello" over TLS with the mounted cert.
    import http.server, ssl
    class Hello(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"hello over TLS from " + self.server.server_name.encode() + b"\n"
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("0.0.0.0", 8443), Hello)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain("/tls/tls.crt", "/tls/tls.key")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    srv.serve_forever()
EOF
```

The `securityContext` block on every pod below is what the `restricted` pod security profile
asks for; without it `oc apply` prints a warning on each pod.

### 3.1 The cluster's own trust store: the injected bundle

OpenShift will fill any ConfigMap that carries one label with the cluster's trust store — the
public CAs merged with whatever the cluster administrator configured in
`proxy/cluster.spec.trustedCA`. This is the bundle to use when a container must trust what the
*cluster* trusts: a corporate-signed API server, an internal registry, an OAuth route.

```bash
cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: trusted-ca
  labels:
    config.openshift.io/inject-trusted-cabundle: "true"
EOF
sleep 5
oc get cm trusted-ca -n ca-tutorial -o jsonpath='{.data.ca-bundle\.crt}' | grep -c 'BEGIN CERT'
# 149  — on CRC; the key is always named ca-bundle.crt
```

Note the `sleep`: the ConfigMap is created empty and the network operator fills it a moment
later. Every consumer must tolerate that window (Part 4).

**Layout A — mount beside the system store and name it (what the dashboard chart does).** The
bundle lands in its own subdirectory; the image's own trust store is untouched; curl is told
about the file through `CURL_CA_BUNDLE`, curl's own variable, which no other program reads.

```bash
cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: Pod
metadata:
  name: client-injected
spec:
  containers:
    - name: c
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["sleep", "infinity"]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      env:
        - { name: CURL_CA_BUNDLE, value: /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt }
      volumeMounts:
        - { name: trusted-ca, mountPath: /etc/pki/ca-trust/extracted/pem/injected, readOnly: true }
  volumes:
    - { name: trusted-ca, configMap: { name: trusted-ca, optional: true } }
EOF
oc wait -n ca-tutorial --for=condition=Ready pod/client-injected --timeout=120s

oc exec -n ca-tutorial client-injected -- sh -c '
  echo "bundle certs: $(grep -c "BEGIN CERT" $CURL_CA_BUNDLE)"
  echo "public host via the injected bundle: http $(curl -s -o /dev/null -w "%{http_code}" https://registry.access.redhat.com/)"
  echo "public host via the image own store: http $(env -u CURL_CA_BUNDLE curl -s -o /dev/null -w "%{http_code}" https://registry.access.redhat.com/)"'
# bundle certs: 149
# public host via the injected bundle: http 404      (404 is the registry's answer to "/"; the TLS handshake verified)
# public host via the image own store: http 404
```

`optional: true` on the volume matters: a required volume would block the first rollout of every
install until the operator has filled the ConfigMap.

**Layout B — mount over the system bundle (what the OpenShift documentation shows).** The
[custom PKI guide](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/configuring_network_settings/configuring-a-custom-pki)
mounts the ConfigMap over `/etc/pki/ca-trust/extracted/pem` with the key renamed to
`tls-ca-bundle.pem`. That file *is* the system bundle on RHEL-family images, so one mount
re-trusts every program that reads the bundle file, with no variables at all:

```bash
cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: Pod
metadata:
  name: client-docs-pattern
spec:
  containers:
    - name: c
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["sleep", "infinity"]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      volumeMounts:
        - { name: trusted-ca, mountPath: /etc/pki/ca-trust/extracted/pem, readOnly: true }
  volumes:
    - name: trusted-ca
      configMap:
        name: trusted-ca
        items: [{ key: ca-bundle.crt, path: tls-ca-bundle.pem }]
EOF
oc wait -n ca-tutorial --for=condition=Ready pod/client-docs-pattern --timeout=120s
oc exec -n ca-tutorial client-docs-pattern -- sh -c '
  echo "curl: http $(curl -s -o /dev/null -w "%{http_code}" https://registry.access.redhat.com/)"
  echo "the directory now holds: $(ls /etc/pki/ca-trust/extracted/pem)"'
# curl: http 404
# the directory now holds: tls-ca-bundle.pem
```

It works, and it is the right shape for a third-party image you cannot configure. Two things to
know before choosing it:

* The mount replaces the **whole directory**. On UBI 9 that is harmless: `/etc/pki/tls/certs`
  there holds two bundle symlinks and nothing else. On the hardened images it is not: their
  `/etc/pki/tls/certs` holds 292 symlinks into `directory-hash/`, which the mount hides, and
  OpenSSL's directory lookup — Python's default context, `urllib`, and any `<hash>.0` file you add
  in 3.2 — stops working while curl keeps working. Measured on `hi/python:3.14`: with this mount
  in place, Python's default context failed to verify a public host while curl succeeded.
* While the ConfigMap is still empty, `tls-ca-bundle.pem` is an empty file and **every** client
  that reads the bundle fails: curl with exit 77, Python's default context with a verification
  error. Layout A confines that window to curl.

### 3.2 A CA you created by hand

Put the CA from Part 2 into a ConfigMap and its server certificate into a TLS Secret, run the
server, and give a client the CA as one hashed file.

```bash
cd ~/ca-tutorial
oc create configmap example-corp-ca -n ca-tutorial --from-file=ca.crt=ca.crt
oc create secret tls server-manual-tls -n ca-tutorial --cert=server.crt --key=server.key

cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: Pod
metadata:
  name: server
  labels: { app: server }
spec:
  containers:
    - name: tls
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["python3", "/script/server.py"]
      ports: [{ containerPort: 8443 }]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      volumeMounts:
        - { name: tls, mountPath: /tls, readOnly: true }
        - { name: script, mountPath: /script, readOnly: true }
  volumes:
    - { name: tls, secret: { secretName: server-manual-tls } }
    - { name: script, configMap: { name: tls-server-script } }
---
apiVersion: v1
kind: Service
metadata:
  name: server
spec:
  selector: { app: server }
  ports: [{ port: 8443, targetPort: 8443 }]
EOF
```

Now the client. The hash is computed on your machine and substituted into the YAML — this block
uses an unquoted `EOF` on purpose — and the ConfigMap's one key is mounted as a **single file**
with `subPath`, so the rest of `/etc/pki/tls/certs/` stays exactly as the image shipped it.
`SSL_CERT_DIR` is set so curl reads the directory too (Part 1.5).

```bash
HASH=$(openssl x509 -noout -subject_hash -in ca.crt); echo $HASH     # 7886c608

cat <<EOF | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: Pod
metadata:
  name: client-manual
spec:
  containers:
    - name: c
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["sleep", "infinity"]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      env:
        - { name: SSL_CERT_DIR, value: /etc/pki/tls/certs }
      volumeMounts:
        - name: example-corp-ca
          mountPath: /etc/pki/tls/certs/$HASH.0
          subPath: ca.crt
          readOnly: true
  volumes:
    - { name: example-corp-ca, configMap: { name: example-corp-ca } }
EOF
oc wait -n ca-tutorial --for=condition=Ready pod/server pod/client-manual --timeout=120s
```

Verify, and while you are there, break it on purpose to see each rule from Part 1.3:

```bash
oc exec -n ca-tutorial client-manual -- sh -c '
  H=7886c608
  echo "the mounted file hashes to: $(openssl x509 -noout -subject_hash -in /etc/pki/tls/certs/$H.0)"
  echo "1. curl, SSL_CERT_DIR set:        $(curl -s https://server.ca-tutorial.svc:8443/ || echo exit $?)"
  echo "2. curl, SSL_CERT_DIR unset:      $(env -u SSL_CERT_DIR curl -s https://server.ca-tutorial.svc:8443/ || echo exit $?)"
  echo "3. curl --capath, no variable:    $(env -u SSL_CERT_DIR curl -s --capath /etc/pki/tls/certs https://server.ca-tutorial.svc:8443/)"
  echo "4. python urllib, no variable:    $(env -u SSL_CERT_DIR python3 -c "import urllib.request; print(urllib.request.urlopen(\"https://server.ca-tutorial.svc:8443/\").read().decode().strip())")"
  mkdir -p /tmp/cp; cp /etc/pki/tls/certs/$H.0 /tmp/cp/$H.1
  echo "5. only $H.1 present:        $(env -u SSL_CERT_DIR curl -s --capath /tmp/cp https://server.ca-tutorial.svc:8443/ || echo exit $?)"
  mv /tmp/cp/$H.1 /tmp/cp/$H.0
  echo "6. renamed to $H.0:          $(env -u SSL_CERT_DIR curl -s --capath /tmp/cp https://server.ca-tutorial.svc:8443/)"
  mv /tmp/cp/$H.0 /tmp/cp/deadbeef.0
  echo "7. right CA, wrong hash:          $(env -u SSL_CERT_DIR curl -s --capath /tmp/cp https://server.ca-tutorial.svc:8443/ || echo exit $?)"'
```

Expected, verbatim from the run this tutorial was written from:

```text
the mounted file hashes to: 7886c608
1. curl, SSL_CERT_DIR set:        hello over TLS from server
2. curl, SSL_CERT_DIR unset:      exit 60
3. curl --capath, no variable:    hello over TLS from server
4. python urllib, no variable:    hello over TLS from server
5. only 7886c608.1 present:        exit 60
6. renamed to 7886c608.0:          hello over TLS from server
7. right CA, wrong hash:          exit 60
```

Read the lines against Part 1: curl needs to be told about the directory (1 vs 2, or 3); Python
reads it by default (4); a `.1` without a `.0` is never opened (5 vs 6); the file name is the
index, so the right CA under the wrong name is invisible (7). Exit 60 is curl's "peer certificate
cannot be authenticated with known CA certificates".

The alternative that needs no mount arrangement at all is `curl --cacert /path/to/ca.crt`, which
is fine for a one-off and useless for a program that does not take that flag.

### 3.3 A CA that cert-manager created

Most clusters do not want hand-made CAs. cert-manager can be the CA: a self-signed bootstrap
issuer signs a CA certificate, a CA issuer built on that certificate signs server certificates,
and every Secret it writes carries the CA in `ca.crt`. The hashed-directory trick then works
from the Secret directly, no ConfigMap needed.

```bash
cat <<'EOF' | oc apply -n ca-tutorial -f -
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: selfsigned-bootstrap
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: tutorial-root-ca
spec:
  isCA: true
  commonName: Tutorial Root CA (cert-manager)
  secretName: tutorial-root-ca
  duration: 87600h
  privateKey:
    algorithm: ECDSA
    size: 256
  issuerRef:
    name: selfsigned-bootstrap
    kind: Issuer
---
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: tutorial-ca
spec:
  ca:
    secretName: tutorial-root-ca
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: server-cm
spec:
  secretName: server-cm-tls
  duration: 2160h
  dnsNames:
    - server-cm.ca-tutorial.svc
    - server-cm.ca-tutorial.svc.cluster.local
  issuerRef:
    name: tutorial-ca
    kind: Issuer
EOF
sleep 15
oc get certificate -n ca-tutorial
# NAME               READY   SECRET             AGE
# server-cm          True    server-cm-tls      15s
# tutorial-root-ca   True    tutorial-root-ca   15s
oc get secret server-cm-tls -n ca-tutorial -o jsonpath='{.data}' | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin)))'
# ['ca.crt', 'tls.crt', 'tls.key']
```

(cert-manager 1.18 and later print a warning that `spec.privateKey.rotationPolicy` now defaults
to `Always`; that is informational.)

The server is the same script with the cert-manager Secret; the client mounts `ca.crt` out of
that same Secret as the hashed file. The hash has to come from the CA cert-manager actually
produced, so read it back from the Secret:

```bash
oc get secret server-cm-tls -n ca-tutorial -o jsonpath='{.data.ca\.crt}' | base64 -d > cm-ca.crt
openssl x509 -noout -subject -in cm-ca.crt           # subject=CN=Tutorial Root CA (cert-manager)
CM_HASH=$(openssl x509 -noout -subject_hash -in cm-ca.crt); echo $CM_HASH   # 743f690f on this run

cat <<EOF | oc apply -n ca-tutorial -f -
apiVersion: v1
kind: Pod
metadata:
  name: server-cm
  labels: { app: server-cm }
spec:
  containers:
    - name: tls
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["python3", "/script/server.py"]
      ports: [{ containerPort: 8443 }]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      volumeMounts:
        - { name: tls, mountPath: /tls, readOnly: true }
        - { name: script, mountPath: /script, readOnly: true }
  volumes:
    - { name: tls, secret: { secretName: server-cm-tls } }
    - { name: script, configMap: { name: tls-server-script } }
---
apiVersion: v1
kind: Service
metadata:
  name: server-cm
spec:
  selector: { app: server-cm }
  ports: [{ port: 8443, targetPort: 8443 }]
---
apiVersion: v1
kind: Pod
metadata:
  name: client-cm
spec:
  containers:
    - name: c
      image: registry.access.redhat.com/ubi9/python-312:latest
      command: ["sleep", "infinity"]
      securityContext:
        allowPrivilegeEscalation: false
        runAsNonRoot: true
        capabilities: { drop: ["ALL"] }
        seccompProfile: { type: RuntimeDefault }
      env:
        - { name: SSL_CERT_DIR, value: /etc/pki/tls/certs }
      volumeMounts:
        - name: tutorial-ca
          mountPath: /etc/pki/tls/certs/$CM_HASH.0
          subPath: ca.crt
          readOnly: true
  volumes:
    - name: tutorial-ca
      secret:
        secretName: server-cm-tls
        items: [{ key: ca.crt, path: ca.crt }]
EOF
oc wait -n ca-tutorial --for=condition=Ready pod/server-cm pod/client-cm --timeout=120s

oc exec -n ca-tutorial client-cm -- sh -c '
  echo "mounted: $(openssl x509 -noout -subject_hash -in /etc/pki/tls/certs/'$CM_HASH'.0) $(openssl x509 -noout -subject -in /etc/pki/tls/certs/'$CM_HASH'.0)"
  echo "curl:          $(curl -s https://server-cm.ca-tutorial.svc:8443/)"
  echo "python urllib: $(python3 -c "import urllib.request; print(urllib.request.urlopen(\"https://server-cm.ca-tutorial.svc:8443/\").read().decode().strip())")"
  echo "no variable:   $(env -u SSL_CERT_DIR curl -s https://server-cm.ca-tutorial.svc:8443/ || echo exit $?)"'
# mounted: 743f690f subject=CN=Tutorial Root CA (cert-manager)
# curl:          hello over TLS from server-cm
# python urllib: hello over TLS from server-cm
# no variable:   exit 60
```

Two things worth trying from here. Ask the hand-made client for the cert-manager server, or the
other way round, and watch it fail with exit 60: each client trusts exactly the one CA it was
given, which is the point. And when the client and the server are in different namespaces,
copy `ca.crt` alone into a ConfigMap in the client's namespace — never the Secret, which holds
the private key.

`items` on the Secret volume is deliberate: it exposes `ca.crt` alone to the client. Without it
the Secret's `tls.key` would be reachable through the same volume.

### 3.4 How the dashboard chart does this

The `group-sync-dashboard` chart wires all three layouts for you:

| Value | Layout | Effect |
|---|---|---|
| `trustedCA.injected.enabled` (default on) | 3.1, layout A | the labelled ConfigMap, mounted beside the system store, named to the application in `GSD_TRUSTED_CA_FILE` and to curl in `CURL_CA_BUNDLE` |
| `trustedCA.existingConfigMap.enabled` + `name` | 3.2 | a ConfigMap you made, mounted beside the system store and named to the application |
| `trustedCA.existingConfigMap.subjectHash` | 3.2, the hashed file | the same ConfigMap mounted a second time as `/etc/pki/tls/certs/<hash>.0` (or `<hash>.N`), so curl and every OpenSSL client in the pod trust it |

curl is configured by a mounted `.curlrc` (`<release>-curlrc`, found through `CURL_HOME`) that
names the injected bundle as `cacert` and the hashed directory as `capath` — the only way curl
takes both (Part 1.5). The first version of the chart used `CURL_CA_BUNDLE` and `SSL_CERT_DIR`,
and the tutorial's own verification showed the second was being ignored.

See `charts/group-sync-dashboard/values.yaml#trustedCA` for the comments, and
`DESIGN_hardened_image.md` for the measurements behind the choice of variables.

### 3.5 The enterprise way: Kyverno does it for every namespace

Hand-editing every Deployment does not scale, and a platform team does not want application
teams to know a subject hash. With Kyverno (installed on this cluster) one ClusterPolicy does the
whole job for any namespace that opts in with a label:

1. **generate** a `trusted-ca` ConfigMap carrying OpenShift's injection label, so the cluster
   fills it with its trust store;
2. **generate** a copy of the enterprise CA ConfigMap, cloned from the platform team's single
   copy and kept in sync with it;
3. **generate** a `.curlrc` ConfigMap naming both stores for curl;
4. **mutate** every Pod at admission so each container mounts all three and carries
   `CURL_HOME` — a Deployment that says nothing about CAs comes out trusting the cluster and the
   enterprise CA, for curl and for every OpenSSL client.

A Pod that must not be touched sets the annotation `trust.example.com/inject-ca: "false"`.

```bash
cat <<'EOF' | oc apply -f -
# Enterprise CA trust, cluster-wide, with Kyverno.
#
# A platform team keeps ONE copy of the enterprise CA (ConfigMap example-corp-ca in the
# ca-tutorial namespace, key ca.crt). Any namespace labelled
#   trust.example.com/inject-ca: enabled
# gets, without its owners doing anything:
#   1. a ConfigMap "trusted-ca" carrying OpenShift's injection label, which the cluster fills
#      with its own trust store (the public CAs merged with proxy/cluster.spec.trustedCA);
#   2. a copy of the enterprise CA ConfigMap, kept in sync with the platform team's copy;
#   3. a .curlrc ConfigMap naming both stores for curl — `cacert` the cluster bundle, `capath`
#      the hashed directory — because curl ignores SSL_CERT_DIR whenever CURL_CA_BUNDLE is set
#      (measured on curl 7.76 and 8.22), so environment variables can never give curl both;
#   4. every Pod mutated at admission so each container mounts all three — the cluster bundle
#      beside the system store, the enterprise CA as the hashed file /etc/pki/tls/certs/7886c608.0,
#      the .curlrc at /etc/curl — and carries CURL_HOME=/etc/curl. Every OpenSSL client (Python,
#      urllib …) reads the hashed directory by default; curl reads it through the file.
# A Pod that must not be touched sets the annotation trust.example.com/inject-ca: "false".
#
# 7886c608 is the enterprise CA's subject hash (`openssl x509 -noout -subject_hash -in ca.crt`).
# It is a property of the CA, so a platform team hardcodes it here and changes it when the CA
# changes. Mounting it under .0 assumes no public CA in the image shares the hash — check with
# `ls /etc/pki/tls/certs/7886c608.*` in the image; on a collision use .1.
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: enterprise-ca-trust
spec:
  background: true
  rules:
    # ---- 1. the cluster's trust store, per namespace ----
    - name: create-injected-bundle-configmap
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchLabels:
                  trust.example.com/inject-ca: enabled
      generate:
        apiVersion: v1
        kind: ConfigMap
        name: trusted-ca
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          metadata:
            labels:
              config.openshift.io/inject-trusted-cabundle: "true"
              trust.example.com/managed-by: kyverno

    # ---- 2. the enterprise CA, cloned from the platform team's copy ----
    - name: clone-enterprise-ca-configmap
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchLabels:
                  trust.example.com/inject-ca: enabled
      generate:
        apiVersion: v1
        kind: ConfigMap
        name: example-corp-ca
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        clone:
          namespace: ca-tutorial
          name: example-corp-ca

    # ---- 3. curl's configuration, per namespace ----
    - name: create-curlrc-configmap
      match:
        any:
          - resources:
              kinds: [Namespace]
              selector:
                matchLabels:
                  trust.example.com/inject-ca: enabled
      generate:
        apiVersion: v1
        kind: ConfigMap
        name: curlrc
        namespace: "{{request.object.metadata.name}}"
        synchronize: true
        data:
          metadata:
            labels:
              trust.example.com/managed-by: kyverno
          data:
            .curlrc: |
              cacert = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
              capath = /etc/pki/tls/certs

    # ---- 4. every pod in such a namespace trusts all of it ----
    - name: mount-ca-trust-into-pods
      match:
        any:
          - resources:
              kinds: [Pod]
              namespaceSelector:
                matchLabels:
                  trust.example.com/inject-ca: enabled
      preconditions:
        all:
          - key: "{{ request.object.metadata.annotations.\"trust.example.com/inject-ca\" || 'true' }}"
            operator: NotEquals
            value: "false"
      mutate:
        patchStrategicMerge:
          spec:
            containers:
              - (name): "*"
                env:
                  - name: CURL_HOME
                    value: /etc/curl
                volumeMounts:
                  - name: trusted-ca
                    mountPath: /etc/pki/ca-trust/extracted/pem/injected
                    readOnly: true
                  - name: enterprise-ca
                    mountPath: /etc/pki/tls/certs/7886c608.0
                    subPath: ca.crt
                    readOnly: true
                  - name: curlrc
                    mountPath: /etc/curl
                    readOnly: true
            volumes:
              - name: trusted-ca
                configMap:
                  name: trusted-ca
                  optional: true
              - name: enterprise-ca
                configMap:
                  name: example-corp-ca
              - name: curlrc
                configMap:
                  name: curlrc
EOF
oc get clusterpolicy enterprise-ca-trust        # READY should be true within a few seconds
```

Now a namespace that opts in, and a Deployment that knows nothing about certificates:

```bash
cat <<'EOF' | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: ca-tutorial-app
  labels:
    trust.example.com/inject-ca: enabled
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
  namespace: ca-tutorial-app
spec:
  replicas: 1
  selector:
    matchLabels: { app: app }
  template:
    metadata:
      labels: { app: app }
    spec:
      containers:
        - name: app
          image: registry.access.redhat.com/ubi9/python-312:latest
          command: ["sleep", "infinity"]
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            capabilities: { drop: ["ALL"] }
            seccompProfile: { type: RuntimeDefault }
EOF
oc rollout status deploy/app -n ca-tutorial-app --timeout=180s
```

What Kyverno did, and the proof by `oc exec`:

```bash
oc get cm -n ca-tutorial-app
# NAME                       DATA   AGE
# curlrc                     1      ...      generated
# example-corp-ca            1      ...      cloned from ca-tutorial
# kube-root-ca.crt           1      ...
# openshift-service-ca.crt   1      ...
# trusted-ca                 1      ...      generated, then filled by OpenShift (149 certs)

POD=$(oc get pod -n ca-tutorial-app -l app=app -o jsonpath='{.items[0].metadata.name}')
oc get pod -n ca-tutorial-app $POD -o jsonpath='{.spec.containers[0].env}{"\n"}{.spec.containers[0].volumeMounts[*].mountPath}{"\n"}'
# [{"name":"CURL_HOME","value":"/etc/curl"}]
# /etc/pki/ca-trust/extracted/pem/injected /etc/pki/tls/certs/7886c608.0 /etc/curl ...

oc exec -n ca-tutorial-app $POD -- sh -c '
  echo "curlrc: $(tr "\n" " " < /etc/curl/.curlrc)"
  echo "enterprise CA server via curl:  $(curl -s https://server.ca-tutorial.svc:8443/)"
  echo "python urllib:                  $(python3 -c "import urllib.request; print(urllib.request.urlopen(\"https://server.ca-tutorial.svc:8443/\").read().decode().strip())")"
  echo "public host via cluster bundle: http $(curl -s -o /dev/null -w "%{http_code}" https://registry.access.redhat.com/)"
  curl -sv https://server.ca-tutorial.svc:8443/ -o /dev/null 2>&1 | grep -i "cafile\|capath"'
# curlrc: cacert = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt capath = /etc/pki/tls/certs
# enterprise CA server via curl:  hello over TLS from server
# python urllib:                  hello over TLS from server
# public host via cluster bundle: http 404
# *  CAfile: /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
# *  CApath: /etc/pki/tls/certs
```

Two things to know about generate rules. Kyverno creates the ConfigMaps when a namespace is
created or updated with the label; adding a new generate rule to an existing policy does not
reach namespaces that already exist until they are touched (`oc annotate ns ca-tutorial-app
trust.example.com/touched=$(date +%s) --overwrite` is enough). And Kyverno's background
controller needs permission to create ConfigMaps in the target namespaces — check with
`oc auth can-i create configmaps --as=system:serviceaccount:kyverno:kyverno-background-controller -n <ns>`;
on this cluster it already had it.

The opt-out, verified: a Pod annotated `trust.example.com/inject-ca: "false"` in the same
namespace came out with no env and no CA volumes.

### 3.6 Clean up — or keep it

The `ca-tutorial` and `ca-tutorial-app` namespaces and the `enterprise-ca-trust` policy were
left in place on CRC so the pods above can be inspected with `oc exec`. To remove everything:

```bash
oc delete clusterpolicy enterprise-ca-trust
oc delete project ca-tutorial-app ca-tutorial
rm -rf ~/ca-tutorial
```

---

## Part 4 — When it does not work

| Symptom | Meaning | Check |
|---|---|---|
| `curl: (60) SSL certificate problem: unable to get local issuer certificate` | curl found no CA for the chain | is `SSL_CERT_DIR`, `--capath`, `CURL_CA_BUNDLE` or `--cacert` pointing at where the CA is? curl does not read the hashed directory unless told |
| `curl: (77) error adding trust anchors from file` | the file `CURL_CA_BUNDLE` / `--cacert` names is empty or missing | an injected ConfigMap that OpenShift has not filled yet; a wrong path |
| Python verifies, curl does not | the CA is in the hashed directory and curl was not told about it | set `SSL_CERT_DIR=/etc/pki/tls/certs` |
| Neither verifies although the file is there | the file name is not the CA's hash, or it is `.1` with no `.0` | `openssl x509 -noout -subject_hash -in FILE` must equal the name before the dot; numbering starts at `.0` |
| A bundle of several CAs in one hashed file, only one works | one file serves one subject hash | one CA per file, or use a bundle where a bundle is read |
| Worked, then the CA rotated and the pod still fails | a `subPath` mount does not follow later ConfigMap or Secret changes | restart the pod (cert-manager users: a rotated CA needs a rollout) |
| On a hardened image, mounting over `/etc/pki/ca-trust/extracted/pem` broke Python but not curl | the mount hid `directory-hash/`, which every entry of `/etc/pki/tls/certs` links into | use layout A, or mount the single file with `subPath` |
| `oc apply` warns about PodSecurity "restricted" | the pod lacks the `securityContext` block shown above | add it; it is required for the pod to run under the restricted profile on OpenShift 4.11+ |
| `SSL_CERT_FILE` set, everything fails at once | it names a bundle every OpenSSL client reads, and the bundle is empty or missing | prefer a `.curlrc` for curl and the application's own setting for the application; never point `SSL_CERT_FILE` at a file that can be empty |
| `CURL_CA_BUNDLE` and `SSL_CERT_DIR` both set, the hashed CA works for Python but not curl | curl ignores `SSL_CERT_DIR` whenever `CURL_CA_BUNDLE` is set; `curl -v` shows only `CAfile` | name both in `$CURL_HOME/.curlrc` (`cacert = …`, `capath = …`), or pass `--capath` explicitly |

## Sources

* OpenSSL: [`X509_LOOKUP_hash_dir`](https://docs.openssl.org/master/man3/X509_LOOKUP_hash_dir/)
  (the lookup, the `.N` suffix) and [`openssl-rehash`](https://docs.openssl.org/master/man1/openssl-rehash/)
  (how the links are made); a worked walkthrough of the latter at
  [misterpki.com/openssl-rehash](https://www.misterpki.com/openssl-rehash/) (extensions scanned,
  `HHHHHHHH.D` and `HHHHHHHH.rD`, `-old`, `-CApath` with `-untrusted` intermediates).
* Kyverno, [Generate rules](https://kyverno.io/docs/policy-types/cluster-policy/generate/) and
  [Mutate rules](https://kyverno.io/docs/policy-types/cluster-policy/mutate/): the two rule types 3.5 uses.
* Red Hat, OpenShift 4.21, [Configuring a custom PKI](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/configuring_network_settings/configuring-a-custom-pki):
  the injected ConfigMap and the mount over `/etc/pki/ca-trust/extracted/pem`.
* Project Hummingbird, [Custom CA certificates with Python](https://hummingbird-project.io/docs/using/custom-ca-python/):
  "Approach 2", the hashed-directory mount.
* cert-manager, [CA issuer](https://cert-manager.io/docs/configuration/ca/) and
  [SelfSigned issuer](https://cert-manager.io/docs/configuration/selfsigned/): the bootstrap chain used in 3.3.
* This repository's design record, `DESIGN_hardened_image.md`, section 8: which variable reaches which client, measured.
