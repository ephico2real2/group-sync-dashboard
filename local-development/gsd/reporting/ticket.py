"""Signed authorization tickets carried from the dashboard to the report service.

A ticket names its viewer, so whoever can sign one can attribute a run to anybody. Since #392
(docs/specs/SPEC_F6_ticket_signing_key.md) it is signed with the TICKET KEY, a Secret of its own that only the
dashboard and the report pod mount, and never with the service token, which the schedule Jobs also hold.
"""

from __future__ import annotations

import base64
import os
import re
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

#: 2 since #392: `v2.<payload>.<signature>`, signed with the ticket key. Version 1 was `<payload>.<signature>`,
#: signed with the service token.
TICKET_VERSION = 2
TIER_ALL = "all"
#: The refusal of a version-1 ticket. The server answers it with 401, as it does an expired ticket, so a page open
#: across the upgrade mints one fresh ticket instead of showing an administrator the refusal (SPEC_F6 §3.3).
EARLIER_FORMAT = "ticket is from an earlier release; mint a new ticket"
_PREFIX = f"v{TICKET_VERSION}"
# Review of the spec (Codex): a verifier that ignores `iat` accepts a ticket minted by a clock far
# ahead of ours for as long as that clock says. Bound both the skew and the lifetime.
MAX_CLOCK_SKEW_SECONDS = 30
MAX_TICKET_TTL_SECONDS = 3600


class TicketError(ValueError):
    """A ticket that must be refused; the message is safe to log."""


@dataclass(frozen=True, repr=False)
class TicketKeys:
    """The keys a ticket is verified with. `current` signs (in the dashboard) and verifies (in the report pod);
    `previous` exists only while a rotation is open and verifies the tickets the dashboard signed before it
    restarted onto `current` (SPEC_F6 §3.4). No repr: a key must not reach a log or a traceback."""

    current: bytes
    previous: bytes | None = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def _unb64(text: str) -> bytes:
    """Strict, canonical base64url. Python's decoder discards characters it does not know, so a ticket
    with `!!!!` spliced in still yielded the signed bytes and verified — one credential, many
    spellings (review of C3, Codex). Refused: any character outside the alphabet, a length no
    encoding produces, and a non-canonical form (re-encoding must give the input back)."""
    if not _B64URL.fullmatch(text) or len(text) % 4 == 1:
        raise ValueError("invalid base64url")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if _b64(raw) != text:
        raise ValueError("non-canonical base64url")
    return raw

def _sign(secret: bytes, payload: bytes) -> bytes:
    return hmac.new(secret, payload, hashlib.sha256).digest()


def mint(key: bytes, viewer: str, tier: str, ttl_seconds: int, now: float | None = None) -> str:
    """Mint one short-lived wide-tier ticket for a proxy-authenticated viewer, signed with the ticket key."""
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
    return f"{_PREFIX}.{_b64(payload)}.{_b64(_sign(key, payload))}"


def verify(keys: TicketKeys, ticket: str, forwarded_user: str | None, now: float | None = None) -> dict:
    """Return valid claims; refuse malformed, misbound, expired or future-dated tickets.

    The order is SPEC_F6 §3.3's: the shape (a version-1 ticket is told to mint again), the encoding, the signature
    under the current key and then the previous one, and only then the claims, so nothing unsigned is parsed."""
    parts = (ticket or "").split(".")
    if len(parts) == 2:
        raise TicketError(EARLIER_FORMAT)
    if len(parts) != 3 or parts[0] != _PREFIX:
        raise TicketError("ticket missing or malformed")
    try:
        payload = _unb64(parts[1])
        signature = _unb64(parts[2])
    except (ValueError, TypeError) as exc:
        raise TicketError("ticket is not base64url") from exc
    if not any(hmac.compare_digest(signature, _sign(key, payload)) for key in (keys.current, keys.previous) if key):
        raise TicketError("ticket signature does not verify with the ticket key")
    try:
        claims = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TicketError("ticket payload is not JSON") from exc
    if not isinstance(claims, dict):
        raise TicketError("ticket payload is not a JSON object")
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
    """Read and validate the service token or a ticket key once during application startup."""
    with open(path, "rb") as fh:
        raw = fh.read().strip()
    if len(raw) < 32:
        raise TicketError(f"the report secret at {path} is shorter than 32 bytes; refusing to use it")
    return raw


def load_ticket_keys(key_file: str, previous_file: str, service_token: bytes) -> TicketKeys:
    """Read the ticket key, and the previous key when its file exists (a rotation is open), once at startup.

    A key with the service token's bytes is refused: the schedule Jobs and the poller hold that token, so a ticket
    key equal to it would let them sign a ticket naming anybody, the hole #392 closes (SPEC_F6 §3.1)."""
    current = load_secret(key_file)
    previous = load_secret(previous_file) if previous_file and os.path.exists(previous_file) else None
    if service_token in (current, previous):
        raise TicketError("the ticket key is the service token's value; the two must be different secrets")
    return TicketKeys(current, previous)
