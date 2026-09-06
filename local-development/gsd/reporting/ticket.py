"""Signed authorization tickets carried from the dashboard to the report service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

TICKET_VERSION = 1
TIER_ALL = "all"
# Review of the spec (Codex): a verifier that ignores `iat` accepts a ticket minted by a clock far
# ahead of ours for as long as that clock says. Bound both the skew and the lifetime.
MAX_CLOCK_SKEW_SECONDS = 30
MAX_TICKET_TTL_SECONDS = 3600


class TicketError(ValueError):
    """A ticket that must be refused; the message is safe to log."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(secret: bytes, payload: bytes) -> bytes:
    return hmac.new(secret, payload, hashlib.sha256).digest()


def mint(secret: bytes, viewer: str, tier: str, ttl_seconds: int, now: float | None = None) -> str:
    """Mint one short-lived wide-tier ticket for a proxy-authenticated viewer."""
    if tier != TIER_ALL:
        raise TicketError("only the wide tier is ever minted")
    if not viewer:
        raise TicketError("a ticket needs a viewer")
    ttl = int(ttl_seconds)
    if ttl < 1 or ttl > MAX_TICKET_TTL_SECONDS:
        raise TicketError(f"ticket lifetime must be between 1 and {MAX_TICKET_TTL_SECONDS} seconds")
    issued = int(now if now is not None else time.time())
    payload = json.dumps(
        {"v": TICKET_VERSION, "viewer": viewer, "tier": tier, "iat": issued,
         "exp": issued + ttl, "nonce": secrets.token_urlsafe(8)},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return f"{_b64(payload)}.{_b64(_sign(secret, payload))}"


def verify(secret: bytes, ticket: str, forwarded_user: str | None, now: float | None = None) -> dict:
    """Return valid claims; refuse malformed, misbound, expired or future-dated tickets."""
    if not ticket or "." not in ticket:
        raise TicketError("ticket missing or malformed")
    body, _, sig = ticket.partition(".")
    try:
        payload = _unb64(body)
        signature = _unb64(sig)
    except (ValueError, TypeError) as exc:
        raise TicketError("ticket is not base64url") from exc
    if not hmac.compare_digest(signature, _sign(secret, payload)):
        raise TicketError("ticket signature does not verify")
    try:
        claims = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TicketError("ticket payload is not JSON") from exc
    if claims.get("v") != TICKET_VERSION:
        raise TicketError("ticket version is not understood")
    issued = claims.get("iat")
    expires = claims.get("exp")
    if not isinstance(issued, int):
        raise TicketError("ticket issued-at time is missing or invalid")
    if not isinstance(expires, int):
        raise TicketError("ticket expiry is missing or invalid")
    if expires <= issued:
        raise TicketError("ticket expiry is not after its issued-at time")
    if expires - issued > MAX_TICKET_TTL_SECONDS:
        raise TicketError("ticket lifetime exceeds the configured maximum")
    current = now if now is not None else time.time()
    if issued > current + MAX_CLOCK_SKEW_SECONDS:
        raise TicketError("ticket was issued too far in the future")
    if expires <= current:
        raise TicketError("ticket has expired")
    if claims.get("tier") != TIER_ALL:
        raise TicketError("ticket does not carry the wide tier")
    if not forwarded_user or claims.get("viewer") != forwarded_user:
        raise TicketError("ticket was minted for a different viewer")
    return claims


def load_secret(path: str) -> bytes:
    """Read and validate the shared token once during application startup."""
    with open(path, "rb") as fh:
        raw = fh.read().strip()
    if len(raw) < 32:
        raise TicketError(f"the report token at {path} is shorter than 32 bytes; refusing to sign with it")
    return raw
