# Rendering mermaid in the terminal — `mermaid-ascii`

[`mermaid-ascii`](https://github.com/AlexanderGrooff/mermaid-ascii) turns a mermaid diagram into an
ASCII / box-drawing picture printed straight to the terminal — no browser, no headless Chromium. It is
a **preview** tool: fast, offline, and readable in a log. The SVG render through
`@mermaid-js/mermaid-cli` (what the CI `diagrams` job gates on) stays the source of truth for
correctness; `mermaid-ascii` is for eyeballing a diagram while you write it and for showing what shipped
in the CI log.

It renders **flowcharts / graphs** well. Sequence diagrams, gantt, state, etc. are not supported — for
those, keep using `mmdc` / the rendered page.

## Install (macOS)

The upstream one-liner uses `wget`, which macOS does not ship; use `curl` instead. This picks the asset
for the running Mac (`Darwin_arm64` on Apple Silicon, `Darwin_x86_64` on Intel) and drops the binary on
your PATH:

```sh
# From a scratch dir. Downloads the release asset for THIS machine, unpacks, installs to /usr/local/bin.
url=$(curl -s https://api.github.com/repos/AlexanderGrooff/mermaid-ascii/releases/latest \
        | grep "browser_download_url.*mermaid-ascii" | grep "$(uname)_$(uname -m)" \
        | cut -d: -f2,3 | tr -d '"' | tr -d ' ')
curl -sL "$url" -o mermaid-ascii.tar.gz
tar xzf mermaid-ascii.tar.gz
sudo install -m 0755 mermaid-ascii /usr/local/bin/mermaid-ascii     # /usr/local/bin is on PATH
mermaid-ascii --help
```

`/usr/local/bin` is already on the default macOS PATH; if you prefer a user-local dir use
`~/.local/bin` (add it to PATH in your shell rc if it isn't already). No `sudo` is needed if the target
dir is writable by you.

## Use it

```sh
mermaid-ascii -f diagram.mmd          # render a file (box-drawing charset)
mermaid-ascii --ascii -f diagram.mmd  # plain ASCII (no unicode) — better for logs and copy-paste
mermaid-ascii --max-width auto -f d.mmd   # fit to the terminal — INTERACTIVE ONLY (`auto` needs a real TTY)
mermaid-ascii --max-width 120 -f d.mmd    # fixed width — use a NUMBER when piping/capturing (`auto` errors there)
mermaid-ascii -x 3 -y 2 -f diagram.mmd    # tighten horizontal/vertical node spacing (helps a wide flowchart)
some-command | mermaid-ascii -f -     # read from stdin
```

Our diagrams live inside ```` ```mermaid ```` fences in the docs, not as `.mmd` files. Pull one block
out and preview it — the same extraction the CI job does:

```sh
python3 - <<'PY' | mermaid-ascii --ascii -f -
import re, pathlib, sys
md = pathlib.Path("docs/reference-architecture.md").read_text()
sys.stdout.write(re.findall(r"```mermaid\n(.*?)```", md, re.S)[0])   # the first block; [n] for the nth
PY
```

## In CI

The `.github/workflows/ci.yml` `diagrams` job extracts every ```` ```mermaid ```` block to `mmd/*.mmd`
and renders each to SVG (the correctness gate). It also installs the Linux `mermaid-ascii` build and
prints each extracted diagram as ASCII in a collapsible log group — a human-readable preview of what
shipped, beside the SVG render. That preview is **display only**: it never fails the job (an unsupported
diagram type prints a note), so the SVG render remains the single gate.

Reference: the upstream README — <https://github.com/AlexanderGrooff/mermaid-ascii/blob/master/README.md>.
