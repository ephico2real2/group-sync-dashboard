#!/usr/bin/env python3
"""The e2e-walk tools (local-development/e2e-walk/e2e_capture.py and e2e_extra.py), run unchanged except for two
things the walker's tier makes necessary: every screenshot masks the fleet account's name, and every recorded row is
cleaned of it and of any `sha256~` value before it is written.

Why: with the cluster-admin tier the Cluster Configurations tab shows the fleet row (`[data-cc-fleet]`), and the
account's name must not reach the report folder. A screenshot is pixels, so a grep cannot find the name in it
afterwards; the mask has to be applied when the picture is taken. The mask covers the fleet row's value, every
element whose text names the account (any case), and an opaque box over each rendered occurrence of the name
(`TEXT_BOXES_JS`). `evidence/mask-log.jsonl` records, per screenshot, how many elements and boxes were masked and
whether the page's text named the account at all — counts only, never the name.

    e2e_masked.py capture <e2e_capture.py arguments>
    e2e_masked.py extra   <e2e_extra.py arguments>

The fleet account's name is read from its Lease with oc (KUBECONFIG from the environment), never printed. The UI
password stays in GSD_UI_PASSWORD, as the tools expect."""
from __future__ import annotations

import json
import os
import pathlib
import re
import runpy
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TOOLS_DIR = HERE.parents[2] / "local-development" / "e2e-walk"   # this checkout's own tools
MASK_LOG = HERE.parent / "evidence" / "mask-log.jsonl"
FLEET_ROW = "[data-cc-fleet] .v > .mono"          # the selector the earlier walks mask
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "GSD_UI_PASSWORD"}

sys.path.insert(0, str(TOOLS_DIR))
import e2e_capture as cap  # noqa: E402  (the same module object e2e_extra.py imports by name)

FLEET = json.loads(subprocess.run(
    ["oc", "get", "leases.coordination.k8s.io", "-n", "group-sync-dashboard", "-l",
     "groupsync-dashboard.io/lease-type=fleet-account", "-o", "json"],
    env=CLEAN_ENV, capture_output=True, text=True, check=True, timeout=60).stdout)["items"][0]["metadata"][
    "annotations"]["groupsync-dashboard.io/account"]
FLEET_RE = re.compile(re.escape(FLEET), re.I)


def clean(text: str) -> str:
    text = re.sub(r"sha256~[A-Za-z0-9_-]+", "sha256~<redacted>", text)
    return FLEET_RE.sub("<fleet account>", text)


# One opaque box over every rendered occurrence of the name, from the text itself. get_by_text alone is not enough:
# it returns the SMALLEST element whose text matches, so on the Logins tab's "Allowed to log in, holds no access" row,
# `<td class="mono">NAME <span class="muted">· FULL NAME</span></td>` (local-development/gsd/static/index.html), whose
# full name also contains the account, it matched only `<span class="muted">· …</span>` and masked x 362–564 of
# screenshots/e2e-13-tab-logins.png while the td's own text node, the name at x 167–355, stayed readable. A Range over
# each matched substring of each text node gives the glyphs' own client rects, whatever element holds them.
TEXT_BOXES_JS = """(needle) => {
  const boxes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.data.toLowerCase();
    for (let at = text.indexOf(needle); at !== -1; at = text.indexOf(needle, at + needle.length)) {
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + needle.length);
      for (const r of range.getClientRects()) {
        if (r.width === 0 || r.height === 0) continue;
        const box = document.createElement('div');
        box.dataset.walkMask = '';
        box.style.cssText = `position:absolute;left:${r.left + scrollX - 2}px;top:${r.top + scrollY - 2}px;` +
          `width:${r.width + 4}px;height:${r.height + 4}px;background:#ff00ff;z-index:2147483647;pointer-events:none`;
        boxes.push(box);
      }
    }
  }
  boxes.forEach((b) => document.body.appendChild(b));
  return boxes.length;
}"""


def shot(self, slug: str, full: bool = True) -> str:
    """e2e_capture.Walk.shot with the fleet mask; the numbering and the blur are the tool's own."""
    self.n += 1
    name = f"{self.n:02d}-{slug}.png"
    page = self.page
    page.mouse.move(0, 0)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(150)
    row, named, boxes = page.locator(FLEET_ROW), page.get_by_text(FLEET_RE), page.locator("[data-walk-mask]")
    body_names_fleet = bool(FLEET_RE.search(page.locator("body").inner_text()))
    text_boxes = page.evaluate(TEXT_BOXES_JS, FLEET.lower())
    masked = {"shot": f"{self.out.name}/{name}", "fleet_row_elements": row.count(),
              "elements_naming_the_account": named.count(), "text_boxes": text_boxes,
              "page_text_named_the_account": body_names_fleet}
    try:
        page.screenshot(path=str(self.out / name), full_page=full, mask=[row, named, boxes])
    finally:
        page.evaluate("() => document.querySelectorAll('[data-walk-mask]').forEach((b) => b.remove())")
    with MASK_LOG.open("a") as f:
        f.write(json.dumps(masked) + "\n")
    return name


_record = cap.Walk.record


def record(self, step: str, ok: bool, detail: str, screenshot: str | None = None, **extra):
    extra = json.loads(clean(json.dumps(extra, default=str)))
    _record(self, step, ok, clean(detail), screenshot, **extra)


cap.Walk.shot = shot
cap.Walk.record = record

if __name__ == "__main__":
    mode, rest = sys.argv[1], sys.argv[2:]
    if mode == "capture":
        sys.argv = [str(TOOLS_DIR / "e2e_capture.py"), *rest]
        sys.exit(cap.main())
    if mode == "extra":
        sys.argv = [str(TOOLS_DIR / "e2e_extra.py"), *rest]
        runpy.run_path(str(TOOLS_DIR / "e2e_extra.py"), run_name="__main__")
        sys.exit(0)
    raise SystemExit("usage: e2e_masked.py capture|extra <arguments>")
