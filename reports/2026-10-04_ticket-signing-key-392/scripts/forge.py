"""Runs INSIDE the report pod (#392 lab check). Builds two tickets for the viewer `walk-forger-392`, each signed with
the SERVICE TOKEN read from its mounted file: the old format (`<payload>.<sig>`) and the new one (`v2.<payload>.<sig>`).
Neither is a valid ticket after #392. Posts each to the service's own runs endpoint on the loopback and prints only
the status codes and the service's refusal words. No token, key or ticket is printed."""
import base64, hashlib, hmac, json, ssl, time, urllib.error, urllib.request
token = open("/etc/gsd/report/token", "rb").read().strip()
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE  # loopback only
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
now = int(time.time())
claims = {"v": 2, "viewer": "walk-forger-392", "tier": "all", "iat": now, "exp": now + 300}
out = {}
for name, prefix, version in (("v1_signed_with_token", "", 1), ("v2_signed_with_token", "v2.", 2)):
    payload = json.dumps({**claims, "v": version}, separators=(",", ":")).encode()
    ticket = prefix + b64(payload) + "." + b64(hmac.new(token, payload, hashlib.sha256).digest())
    req = urllib.request.Request("https://127.0.0.1:8443/report/api/runs", method="POST",
                                 data=json.dumps({"report": "groups", "cluster": "dashboard"}).encode(),
                                 headers={"Content-Type": "application/json", "X-GSD-Report-Ticket": ticket,
                                          "X-Forwarded-User": "walk-forger-392"})
    try:
        r = urllib.request.urlopen(req, context=ctx, timeout=30); out[name] = {"status": r.status}
    except urllib.error.HTTPError as e:
        out[name] = {"status": e.code, "detail": json.loads(e.read() or b"{}").get("detail")}
print(json.dumps(out))
