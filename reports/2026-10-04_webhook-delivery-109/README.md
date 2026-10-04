# #109 on the lab: webhook delivery of scheduled reports, 2026-10-04

**Outcome.** The lab served application 4.4.0, deployed by Argo CD from main at `451ff688` (PR #583, SPEC_F4). The
spec's §5 walk ran inside the reporting window (01:27–01:29 New York) and every check passed (`walk.log`).
- **Job 1** (`delivery-walk-1`, created from the suspended CronJob `delivery-walk`) fanned out to the six clusters.
  The checks in `walk.log` show, for each of the six runs:
  - one `delivered` line in the Job's log (`evidence/job1.log`);
  - one event at the receiver (`evidence/receiver-cut.log`), a CloudEvent 1.0 as
    `application/cloudevents+json; charset=utf-8`, of type `io.github.ephico2real2.gsd.report.run.finished`;
  - `data` matching the Job's line for that run (id, cluster, status, sha256, sizes);
  - an `attachment` whose base64 decodes to exactly the stored html artefact. Its sha256 equals the artefact read
    through the service (`evidence/artifacts.jsonl`).
- **The URL is printed nowhere.** The Secret's URL carried a random marker in its path, kept in a shell variable and
  only counted:
  - the marker in Job 1's log: 0;
  - in Job 1's YAML: 0;
  - in the receiver's log: 0;
  - the receiver's host and `/hook/` in Job 1's log: 0.

  The receiver logs the path's length, never the path.
- **Job 2, with the receiver deleted** (`evidence/job2.log`):
  - each of the six runs made 4 attempts with full-jitter backoff (delays from 0.0 s to 6.8 s);
  - each was named `delivery failed for run <id>: ConnectError after 4 attempt(s)`, and the Job failed;
  - all six runs are `done`;
  - the marker, the host and `/hook/` appear 0 times in its log.
- **Removal:** the receiver Pod, its Service, the Secret and both Jobs were removed, and nothing labelled
  `app=gsd-delivery-walk` remains. The CronJob stays suspended.
- **PVC UIDs** were unchanged. Argo CD read Synced and Healthy at `451ff688`.

The same `groups` data on each cluster sealed the same sha256 in Job 1 and Job 2 (`fc82af0d…` on `dashboard`, for
example): #270's seal, once more.

| Path | Contents |
|---|---|
| `walk.log` | each command and its output, the checks, the counts |
| `evidence/job1.log`, `evidence/job2.log` | the two Jobs' logs |
| `evidence/receiver-cut.log` | what the receiver received, each base64 body replaced by its length |
| `evidence/artifacts.jsonl` | each run's stored html artefact: sha256 and size |
| `scripts/` | `run.sh`, `receiver.yaml`, `check.py`, `artifact_sha.py` |
