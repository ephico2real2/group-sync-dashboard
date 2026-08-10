#!/usr/bin/env python3
"""Capture one screenshot per dashboard tab, for the README.

README screenshots rot silently: the UI changes, the images do not, and nothing fails. This
exists so regenerating them is one command rather than a manual pass with a browser, which is
the difference between images that describe the product and images that describe last quarter.

    # through the real ingress, logging in as a cluster user. THIS IS THE ONE TO USE.
    GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) \
      .venv/bin/python capture-screenshots.py \
        --base https://group-sync-dashboard.apps-crc.testing \
        --login-user kubeadmin --provider developer

    # or bypass oauth-proxy by port-forwarding to the container's own port
    oc port-forward -n group-sync-dashboard deploy/group-sync-dashboard 18080:8080 &
    .venv/bin/python capture-screenshots.py

    # --theme light captures the other shipped theme; both are WCAG-tested
    .venv/bin/python capture-screenshots.py --base http://127.0.0.1:8080 --theme light

WHY THE INGRESS IS WORTH THE LOGIN. Port-forwarding reaches the same process and renders the
same markup for five of the six tabs — the proxy adds authentication, not HTML. Usage is the
exception and it is not cosmetic: that tab reports on who has used the dashboard, the username
comes from the proxy's header, and with the proxy bypassed the page correctly says it is
recording nothing. Screenshotting that produces an image of a working feature looking broken,
which is worse than no image. So the ingress path exists, and it is the documented one.

IT REFUSES TO CAPTURE A BROKEN PAGE. Every capture fails on an uncaught JavaScript error or a
visible "Dashboard API error". This project has already shipped a stray backtick that blanked
the entire page while 431 tests passed, and a screenshot is a worse detector than a test: a
blank or half-rendered image looks like a design choice and gets committed. Failing loudly is
the only honest option, so a green run means the pages actually rendered.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

REPO = pathlib.Path(__file__).resolve().parents[1]

# (tab label, output filename).
#
# Deliberately NOT anchored on heading text, which tests/test_ui.py can do because it seeds a
# fixed database and this cannot. Half the headings carry live counts — "Groups · 62 shown",
# "Unmanaged · 4" — so an exact-text wait passes on the cluster it was written against and
# times out on every other one, including the same cluster after a poll. The wait below is
# structural instead: the clicked tab reports aria-current, the network settles, and some
# heading exists.
# Numbered in TAB-STRIP ORDER, which is the only ordering a reader can check against the
# screenshots. Logins was missing entirely — seven tabs ship and six were captured — so Usage
# moved from 06 to 07 rather than leaving a number that no longer means its position.
TABS = [
    ("Overview",        "01-overview.png"),
    ("Groups",          "02-groups.png"),
    ("Access granted",  "03-access-granted.png"),
    ("RBAC policy",     "04-rbac-policy.png"),
    ("Namespace audit", "05-namespace-audit.png"),
    ("Logins",          "06-logins.png"),
    ("Usage",           "07-usage.png"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:18080",
                    help="dashboard base URL (default: %(default)s)")
    ap.add_argument("--out", default="docs/screenshots",
                    help="output directory, relative to the repo root (default: %(default)s)")
    ap.add_argument("--theme", choices=("dark", "light"), default="dark",
                    help="both themes ship and both are WCAG-tested (default: %(default)s)")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--scale", type=float, default=1.0, metavar="N",
                    help="device pixel ratio (default: %(default)s). 2 renders crisp on HiDPI "
                         "and roughly quadruples the file size — 4.6 MB versus 1.2 MB for the "
                         "six tabs, for images GitHub displays at about 900px wide either way. "
                         "Not worth committing by default.")
    ap.add_argument("--provider", default="developer", metavar="NAME",
                    help="the identity provider to pick on OpenShift's chooser, when more than "
                         "one is configured (default: %(default)s, which is the one kubeadmin "
                         "authenticates through on the reference lab). An LDAP persona needs "
                         "--provider ldap-local. Naming it beats guessing: the previous guess "
                         "matched nothing once a second provider existed, and the failure looked "
                         "like a timeout on the password form.")
    ap.add_argument("--login-user", default=None, metavar="USER",
                    help="log in through OpenShift OAuth first, reading the password from "
                         "GSD_UI_PASSWORD. Required only for --base pointing at the ingress; "
                         "the Usage tab cannot render without an authenticated identity, "
                         "because the username comes from the proxy.")
    args = ap.parse_args()

    password = os.environ.get("GSD_UI_PASSWORD")
    if args.login_user and not password:
        # Env only, never an argument: a password in argv is visible in `ps` to every process
        # on the host. Same rule as cluster-report.py.
        print("ERROR: --login-user needs the password in GSD_UI_PASSWORD", file=sys.stderr)
        return 2

    out = REPO / args.out
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=args.scale,
            color_scheme=args.theme,
            ignore_https_errors=True,
        )
        page = context.new_page()

        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(args.base, wait_until="networkidle")

        if args.login_user:
            # THREE pages, not one, and each is conditional. Assuming a username field would be
            # on the first page cost a 30s timeout on a page whose entire text is "Log in with
            # OpenShift".
            #
            # 1. oauth-proxy's own interstitial. It renders unless the proxy runs with
            #    -skip-provider-button, which this chart does not set.
            interstitial = page.locator("button:has-text('Log in with OpenShift')")
            if interstitial.count():
                interstitial.first.click()
                page.wait_for_load_state("networkidle")

            # 2. OpenShift's identity-provider chooser, shown only with more than one provider
            #    configured — and NAMED rather than guessed.
            #
            #    This used to guess: `a:has-text('htpasswd'), a:has-text('kube:admin'), …`. It
            #    worked while CRC had one provider and broke silently the moment the lab added a
            #    second. Measured on the reference cluster, the chooser offers exactly
            #    `developer` and `ldap-local` and there is NO kube:admin link — so the guess
            #    matched nothing, the click never happened, and the script then waited 20s for a
            #    username field on a page that was still the chooser. The documented invocation
            #    could not have worked.
            #
            #    kubeadmin authenticates through the `developer` provider on this lab, which is
            #    why that is the default; an LDAP persona needs --provider ldap-local.
            chooser = page.locator(f"a:has-text('{args.provider}')")
            if chooser.count():
                chooser.first.click()
                page.wait_for_load_state("networkidle")
            elif page.locator("a").count() and not page.locator("input[name='username']").count():
                # Offered a choice, and ours is not among them. Fail with the list rather than
                # timing out on a form that will never appear.
                offered = [t.strip() for t in page.locator("a").all_inner_texts() if t.strip()]
                print(f"ERROR: no identity provider named {args.provider!r}. "
                      f"This cluster offers: {', '.join(offered) or '(none found)'}",
                      file=sys.stderr)
                browser.close()
                return 1

            # 3. The credential form.
            page.wait_for_selector("input[name='username']", timeout=20_000)
            page.fill("input[name='username']", args.login_user)
            page.fill("input[name='password']", password)
            page.click("button[type='submit'], input[type='submit']")
            page.wait_for_load_state("networkidle")

            # 4. The service-account consent screen: "Service account <x> is requesting
            #    permission to access your account". It appears because this chart makes the
            #    ServiceAccount itself the OAuth client (see templates/serviceaccount.yaml)
            #    rather than registering an OAuthClient object, and the proxy requests
            #    approval_prompt=force, so it is shown on EVERY login and not just the first.
            #    Only user:info and user:check-access are requested.
            approve = page.locator("input[name='approve']")
            if approve.count():
                approve.first.click()
                page.wait_for_load_state("networkidle")

            # Prove the login worked rather than screenshotting a login page six times. The
            # tab strip only exists once the dashboard itself has rendered.
            try:
                page.wait_for_selector("button.tab", timeout=20_000)
            except Exception:
                print(f"ERROR: login as {args.login_user} did not reach the dashboard; the "
                      f"page is at {page.url}", file=sys.stderr)
                browser.close()
                return 1
            print(f"  logged in as {args.login_user}")

        failures = []
        for label, filename in TABS:
            errors.clear()
            page.click(f'button.tab:text-is("{label}")')
            # aria-current is set by the same render pass that draws the section, so it is a
            # signal the page has switched rather than that the click was received.
            page.wait_for_selector(
                f'button.tab[aria-current="page"]:text-is("{label}")', timeout=15_000)
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("h2", timeout=15_000)
            # Tables and counts land after their fetch resolves; networkidle can fall quiet a
            # frame before the DOM settles, and a screenshot taken then shows empty cells.
            page.wait_for_timeout(600)

            # Clear the interaction state the click itself created. Clicking leaves the pointer
            # on the button and the button focused, so the capture kept a :hover background and
            # a :focus-visible ring on a tab — and because the header drops the cluster selector
            # on the Usage tab, the strip shifts and the leftover hover can land on a DIFFERENT
            # tab than the current one. In a README that reads as a rendering bug rather than
            # as a mouse that happened to be somewhere.
            page.mouse.move(0, 0)
            page.evaluate("document.activeElement && document.activeElement.blur()")
            page.wait_for_timeout(150)

            body = page.locator("body").inner_text()
            if errors:
                failures.append(f"{label}: JavaScript error — {errors[0]}")
                continue
            if "Dashboard API error" in body:
                failures.append(f"{label}: the page rendered an API error")
                continue

            target = out / filename
            page.screenshot(path=str(target), full_page=True)
            kb = target.stat().st_size // 1024
            print(f"  {filename:26} {label:16} {kb} KB")

        browser.close()

    if failures:
        print("\nREFUSED to publish — these pages did not render cleanly:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print(f"\n{len(TABS)} screenshots written to {out.relative_to(REPO)} ({args.theme} theme)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
