"""The password as the wire carries it — `Basic base64(user:password)` (RFC 7617 §2) — echoed by a remote reaches no
line and no error handed to the caller, so no finding and no API response (#283's scrub; the code review of #419, N3)."""
from __future__ import annotations

import base64
import logging

import pytest

from gsd.fleetlogin import LoginError
from test_fleet_login import PASSWORD, USER, Target, make, refused_401


def test_the_basic_credential_echoed_by_the_remote_is_redacted(caplog):
    basic = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    fl, _ = make(Target(refused_401(body=f"denied; request had Authorization: Basic {basic}")))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
    assert basic not in exc.value.message, exc.value.message
    assert basic not in "\n".join(caplog.messages)
    assert "Basic <redacted>" in exc.value.message
