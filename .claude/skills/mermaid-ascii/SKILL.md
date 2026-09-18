---
name: mermaid-ascii
description: Preview a mermaid diagram as ASCII in the terminal with mermaid-ascii — no browser, offline, readable in a log. Use it whenever you write, edit or review a ```mermaid block in this repo's docs, before committing. Flowcharts/graphs only; the CI diagrams job's SVG render stays the correctness gate.
---

# Preview mermaid diagrams in the terminal — `mermaid-ascii`

When you add or change a ```` ```mermaid ```` block in this repo (`docs/reference-architecture.md`,
`docs/DESIGN_*`, `docs/specs/SPEC_*`, the tutorial), **look at it as ASCII before you commit** —
`mermaid-ascii` renders it straight to the terminal, no browser. It catches "this arrow points the
wrong way / this node is orphaned" in a second, which reading the source does not. Full reference and
the CI wiring: `local-development/docs/mermaid-ascii-terminal.md`.

**It is a preview, not the gate.** The CI `diagrams` job renders every block to SVG through
`@mermaid-js/mermaid-cli` — that is the correctness check. `mermaid-ascii` handles **flowcharts /
graphs**; sequence, gantt, state, class diagrams are unsupported — for those, use `mmdc` or the page.

## Have it installed

```sh
command -v mermaid-ascii >/dev/null || {
  url=$(curl -s https://api.github.com/repos/AlexanderGrooff/mermaid-ascii/releases/latest \
          | grep "browser_download_url.*mermaid-ascii" | grep "$(uname)_$(uname -m)" \
          | cut -d: -f2,3 | tr -d '"' | tr -d ' ')
  curl -sL "$url" -o /tmp/mermaid-ascii.tar.gz && tar xzf /tmp/mermaid-ascii.tar.gz -C /tmp
  install -m 0755 /tmp/mermaid-ascii /usr/local/bin/mermaid-ascii     # sudo if /usr/local/bin isn't yours
}
```

macOS ships `curl`, not `wget` (the upstream one-liner's `wget` won't work). `$(uname)_$(uname -m)`
selects the right asset — `Darwin_arm64` / `Darwin_x86_64` locally, `Linux_x86_64` in CI.

## Preview a block

Our diagrams live inside markdown fences, not `.mmd` files, so pull the block out and pipe it — the same
extraction the CI job does:

```sh
# Preview the Nth ```mermaid block of a doc (0-based). --ascii = plain charset (log/paste friendly).
python3 - "docs/reference-architecture.md" 0 <<'PY' | mermaid-ascii --ascii -f -
import re, pathlib, sys
md = pathlib.Path(sys.argv[1]).read_text()
sys.stdout.write(re.findall(r"```mermaid\n(.*?)```", md, re.S)[int(sys.argv[2])])
PY
```

`-x`/`-y` tighten node spacing for a wide flowchart. Drop `--ascii` for unicode box-drawing when the
terminal supports it. **Gotcha:** `--max-width auto` needs a real TTY and ERRORS when piped or captured
(as above, and in CI) — pass a number (`--max-width 120`) there, or omit it. HTML in labels (`<br/>`,
`&lt;`) is not decoded; a flowchart with heavy inline HTML reads better on the rendered page.

## In CI

The `diagrams` job (`.github/workflows/ci.yml`) already installs the Linux build and prints every
extracted diagram as ASCII in a collapsible log group — a preview of what shipped, beside the SVG gate.
It is display-only and never fails the job. If you add a new flowchart, that preview will appear in the
job log automatically; nothing to wire.
