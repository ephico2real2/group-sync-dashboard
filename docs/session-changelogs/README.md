# Session change logs

One file per working session, in the format the `changelog` project skill
(`.claude/skills/changelog/SKILL.md`) defines: what the session
did, in order, with the commit, PR or measurement behind each line. This is the **session** record;
`../CHANGELOG.md` is the product record an operator reads per release, and the two never merge.

| File | Convention |
|---|---|
| `YYYY-MM-DD_<slug>.md` | the date the session STARTED (a session spanning midnight keeps it) and a two- or three-word subject |
| entries | appended after each commit that has passed its tests and review — never before validation |
| numbers | measured by the session (`git log`, `gh pr view`, the test summary lines), never recalled |

Every `path.md` / `path.py#anchor` written in backticks here is held by
`local-development/tests/test_docs_citations.py` to a file that exists in the repository, like every
other document under `docs/`.
