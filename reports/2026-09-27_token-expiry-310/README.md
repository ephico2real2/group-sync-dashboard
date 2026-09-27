# Retrieved-token expiry — #310, Part B

Source: [issue #310](https://github.com/ephico2real2/group-sync-dashboard/issues/310), the comment
dated 2026-09-23T01:45:46Z, “First recorded observation of a token expiring — two runs, on
`shared-qa`”. These excerpts were transcribed from the supplied issue export for the documentation
write-up on 2026-09-27. The folder date is the write-up date; the observations are from 2026-09-23.
The comment does not state an application commit, application version or chart version.

The raw pod logs from 2026-09-23 are no longer retrievable: the dashboard pod that ran then has since
been replaced (the running pod started 2026-09-27T08:44:51Z, read on 2026-09-27), and the lab forwards
no logs. **The comment's
quoted lines ARE the capture.** These files preserve those lines exactly, including spacing,
abbreviations and the omitted-polls marker; they are not reconstructed raw logs or a new lab run.
This write-up made no lab changes and did not touch `shared-qa`'s state.

| Capture | Source and contents |
|---|---|
| [Run 1](run-1.txt) | The complete quoted timeline under “Run 1 — 10-minute token”, including its recorded `exp` decode. |
| [Run 2](run-2.txt) | The complete quoted timeline under “Run 2 — 20-minute token, rotated into the existing Secret”, including its recorded `exp` decode. |
| [Expiry claims](exp-claims.txt) | Only the literal `exp` fields excerpted from those timelines, in run order. The comment gives clock times, no epoch values or `iat` decode; none have been inferred. No token is included. |
| [Authentication warning](auth-failed.txt) | The complete quoted warning under “Finding 2 — the 401 cannot distinguish expiry from revocation”. The comment does not attach a timestamp or separate run attribution to this warning. The comment wraps the warning onto four lines; the dashboard logs it as one line. |
| [Findings](findings.txt) | Verbatim excerpts: the introductory setup and poll cadence, Finding 1's explanation and consequence, Finding 2's interpretation, and Finding 3 from “Measured:” onwards. Blank lines separate excerpts. These are the observer's findings, not additional log lines. |

The write-up is [Case G](../../docs/VALIDATION_satokenlookup.md#5e-case-g--a-retrieved-token-expiring).
