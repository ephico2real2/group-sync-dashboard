# The hover rail clear of the first cell — the walk behind #219

Deployed head `67cca41` (`fix/219-hover-rail`, through the Argo Application; `running : 67cca4104a — verified
in-pod`), walked with `walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900: the first row of
the Groups and Users tables hovered, the first cell's and the header's ink measured from the cell's left edge
with a Range, the rail's presence read from the computed `box-shadow`.

| claim | measured |
|---|---|
| the first cell's ink starts past the 3 px rail, header aligned | `groups  : first cell ink in / header ink in / rail painted [3, 3, True]` |
| the same on Users | `users   : first cell ink in / header ink in / rail painted [3, 3, True]` |
| no uncaught error | `errors  : []` |

Capture: `01-hovered-row.png` — the hovered Groups row, the accent rail at its left edge and the name clear
of it.
