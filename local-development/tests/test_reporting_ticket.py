"""The ticket: signature, expiry, tier, and the binding to the proxy's identity header."""
import pytest

from gsd.reporting.ticket import TicketError, mint, verify

SECRET = b"x" * 48


def _tampered(ticket: str) -> str:
    """Change one signature character to a different one. Overwriting the last two with "AA" was a no-op once in
    ~1,000 mints (the nonce makes the signature random), and the test then failed at random (main run 36362295306)."""
    i = len(ticket) - 5    # inside the signature, and not its last character, whose low bits are fixed padding
    return ticket[:i] + ("B" if ticket[i] == "A" else "A") + ticket[i + 1:]


def test_round_trip_binds_viewer_and_tier():
    t = mint(SECRET, "root", "all", 300, now=1_000)
    claims = verify(SECRET, t, "root", now=1_100)
    assert claims["viewer"] == "root" and claims["tier"] == "all" and claims["exp"] == 1_300


@pytest.mark.parametrize("bad", [
    ("wrong secret", lambda t: (b"y" * 48, t, "root", 1_100)),
    ("expired", lambda t: (SECRET, t, "root", 1_400)),
    ("other viewer", lambda t: (SECRET, t, "alice", 1_100)),
    ("no viewer header", lambda t: (SECRET, t, None, 1_100)),
    ("tampered", lambda t: (SECRET, _tampered(t), "root", 1_100)),
    ("malformed", lambda t: (SECRET, "nope", "root", 1_100)),
])
def test_every_refusal_is_a_ticket_error(bad):
    label, make = bad
    secret, ticket, user, now = make(mint(SECRET, "root", "all", 300, now=1_000))
    with pytest.raises(TicketError):
        verify(secret, ticket, user, now=now)


def test_only_the_wide_tier_is_ever_minted():
    with pytest.raises(TicketError):
        mint(SECRET, "root", "self", 300)


def test_a_short_secret_is_refused(tmp_path):
    from gsd.reporting.ticket import load_secret
    p = tmp_path / "token"
    p.write_bytes(b"short\n")
    with pytest.raises(TicketError):
        load_secret(str(p))
    p.write_bytes(b"a" * 48 + b"\n")
    assert load_secret(str(p)) == b"a" * 48      # trailing newline trimmed: both pods sign the same bytes


def test_ticket_issued_far_in_the_future_is_refused():
    ticket = mint(SECRET, "root", "all", 300, now=10_000)
    with pytest.raises(TicketError, match="issued too far in the future"):
        verify(SECRET, ticket, "root", now=1_000)


def test_small_clock_skew_is_tolerated_but_exact_expiry_is_not():
    ticket = mint(SECRET, "root", "all", 300, now=1_020)
    assert verify(SECRET, ticket, "root", now=1_000)["iat"] == 1_020
    with pytest.raises(TicketError, match="expired"):
        verify(SECRET, ticket, "root", now=1_320)


def test_a_ticket_has_exactly_one_spelling():
    """Codex, review C3: Python's permissive decoder dropped characters it did not know, so a ticket
    with `!!!!` spliced in still yielded the signed bytes and verified — one credential, many spellings.
    Strict alphabet, a producible length, and a canonical re-encoding, or it is malformed."""
    ticket = mint(SECRET, "root", "all", 300, now=1_000)
    body, sig = ticket.split(".")
    for malformed in (body[:4] + "!!!!" + body[4:] + "." + sig, body + "." + sig[:4] + "!!!!" + sig[4:],
                      body + "=" + "." + sig, body[:-1] + ("A" if body[-1] != "A" else "B") + "." + sig):
        with pytest.raises(TicketError):
            verify(SECRET, malformed, "root", now=1_100)
    assert verify(SECRET, ticket, "root", now=1_100)["viewer"] == "root"


def test_tampering_always_changes_the_ticket_and_is_refused():
    for _ in range(5_000):
        ticket = mint(SECRET, "root", "all", 300, now=1_000)
        bad = _tampered(ticket)
        assert bad != ticket
        with pytest.raises(TicketError):
            verify(SECRET, bad, "root", now=1_100)
