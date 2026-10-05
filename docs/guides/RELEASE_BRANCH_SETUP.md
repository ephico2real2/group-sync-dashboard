# The `release` branch: one-time setup, checks and upkeep

This page is for whoever sets up or looks after the `release` branch. Each step says what it does and why, then gives
two ways to do it (the GitHub web pages, and the `gh` command line) and a check. How promotion itself works is in
`docs/guides/RELEASING.md`, "Promotion to the lab" (#598).

## In one minute

The lab runs the dashboard from a branch. Until now that branch was `main`. A merge to `main` can reach the lab a
minute before its image has been built, and the pods wait in `ErrImagePull` until the image exists.

`release` is a branch that only receives a version **after its images are proven to exist**. The workflow
`.github/workflows/promote.yml` reads both images back from the registry and writes their exact digests into
`promotion.yaml`. Then it moves `release` forward. Nothing else may write `release`.

    main  --(merge)-->  publish.yml builds the images  -->  promote.yml checks them
                                                             |
                                                             v
                          release  <--(writes chart + promotion.yaml, digests pinned)

Four GitHub settings make "nothing else may write `release`" true. They are done once:

| Step | What it creates | Why it is needed |
|---|---|---|
| 1 | a **deploy key** with write access | the one credential allowed to push to `release` |
| 2 | an **environment** `release`, holding that key as a secret | only workflows running from `main` can read the key |
| 3 | the **branch** `release`, empty | promote.yml moves an existing branch forward; it never creates one |
| 4 | a **ruleset** on `release` | blocks every push except the deploy key's, and blocks force pushes and deletion |

The repository then has three branches on purpose: `main` (the source), `gh-pages` (the Helm repository) and
`release`.

## Before you start

- You need admin rights on `ephico2real2/group-sync-dashboard`, and the `gh` command line signed in (`gh auth status`).
- Steps 1 and 2 handle a **private key**. Run them in your own terminal, delete the key files afterwards, and never
  paste the private half anywhere else.
- Do the steps in order. Step 3 must come before step 4, because the ruleset blocks creating the branch.

## Step 1: the deploy key

**What it does.** It creates an SSH key pair. GitHub keeps the public half as a "deploy key" for this one repository,
with write access. The private half becomes the secret in step 2. The promote workflow uses it to push to `release`,
and nothing else uses it.

**On the web.**
1. On your laptop, make the key pair (see the first two commands below).
2. Settings → Deploy keys → Add deploy key.
3. Title `promote-release`, paste the content of `promote-release.pub`, tick **Allow write access**, and save.

**With `gh`.**

    cd "$(mktemp -d)"
    ssh-keygen -t ed25519 -N '' -C promote-release -f promote-release
    gh repo deploy-key add promote-release.pub -R ephico2real2/group-sync-dashboard --allow-write --title promote-release

The raw API does the same:

    gh api -X POST repos/ephico2real2/group-sync-dashboard/keys -f title=promote-release -f key="$(cat promote-release.pub)" -F read_only=false

**Check.**

    gh api repos/ephico2real2/group-sync-dashboard/keys --jq '.[] | [.id, .title, .read_only] | @tsv'

You should see `promote-release` with `read_only` `false`. Keep the terminal open for step 2.

## Step 2: the `release` environment and its secret

**What it does.** A GitHub environment is a named place to keep secrets, with rules about who may read them. This one,
`release`, accepts deployments only from the `main` branch. So the key is readable only by a workflow running from
`main`, never from a pull request or another branch.

**On the web.**
1. Settings → Environments → New environment, named `release`.
2. Under **Deployment branches and tags**, choose **Selected branches and tags**, add the rule `main`, and save.
3. Under **Environment secrets** → Add secret: name `RELEASE_DEPLOY_KEY`, value the whole content of the file
   `promote-release` (the private half, not the `.pub`).

**With `gh`.**

    gh api -X PUT repos/ephico2real2/group-sync-dashboard/environments/release --input - <<'EOF'
    {"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
    EOF
    gh api -X POST repos/ephico2real2/group-sync-dashboard/environments/release/deployment-branch-policies -f name=main -f type=branch
    gh secret set RELEASE_DEPLOY_KEY --env release -R ephico2real2/group-sync-dashboard < promote-release

Use `gh secret set` for the secret rather than the raw API. The API needs the value encrypted first, and `gh` does
that for you.

**Then delete the key files:**

    rm -f promote-release promote-release.pub

**Check** (names and rules only; GitHub never shows a secret's value):

    gh api repos/ephico2real2/group-sync-dashboard/environments/release --jq '.deployment_branch_policy'
    gh api repos/ephico2real2/group-sync-dashboard/environments/release/deployment-branch-policies --jq '.branch_policies[] | [.name, .type] | @tsv'
    gh api repos/ephico2real2/group-sync-dashboard/environments/release/secrets --jq '.secrets[].name'

You should see `custom_branch_policies: true`, one rule `main` of type `branch`, and the secret `RELEASE_DEPLOY_KEY`.

## Step 3: the empty `release` branch

**What it does.** It creates the branch `release` holding one commit with no files. `promote.yml` only ever moves an
existing branch forward, so the branch must exist before the first promotion. It starts empty so that its first real
content is a promotion.

**On the web.** Not possible. The web page creates a branch as a copy of another branch, files and all. Use `git` or
`gh` below.

**With `git`.**

    c=$(git commit-tree "$(git hash-object -t tree /dev/null)" -m "release starts empty")
    git push origin "${c}:refs/heads/release"

**With `gh`** (the same, through the API). `4b825dc…` is git's fixed id for an empty tree:

    c=$(gh api -X POST repos/ephico2real2/group-sync-dashboard/git/commits -f message="release starts empty" -f tree=4b825dc642cb6eb9a060e54bf8d69288fbee4904 --jq .sha)
    gh api -X POST repos/ephico2real2/group-sync-dashboard/git/refs -f ref=refs/heads/release -f sha="${c}"

**Check.**

    git ls-remote origin refs/heads/release
    git fetch origin release && git ls-tree origin/release | wc -l

You should see one commit, and `0` files.

## Step 4: the ruleset that locks `release`

**What it does.** A ruleset is a set of branch protections. This one refuses every creation, update and deletion of
`release`, and every force push, except from a **deploy key**. So people cannot push to `release`, even with admin
rights, and the promote workflow can.

**On the web.**
1. Settings → Rules → Rulesets → New branch ruleset, named `release`.
2. Enforcement status: **Active**.
3. Target branches → Add target → Include by pattern: `release`.
4. Rules: tick **Restrict creations**, **Restrict updates**, **Restrict deletions**, **Block force pushes**.
5. Bypass list → Add bypass → **Deploy keys**, mode **Always**. Save.

**With `gh`.**

    gh api -X POST repos/ephico2real2/group-sync-dashboard/rulesets --input - <<'EOF'
    {
      "name": "release",
      "target": "branch",
      "enforcement": "active",
      "conditions": {"ref_name": {"include": ["refs/heads/release"], "exclude": []}},
      "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
      "bypass_actors": [{"actor_id": null, "actor_type": "DeployKey", "bypass_mode": "always"}]
    }
    EOF

**Check.**

    gh api repos/ephico2real2/group-sync-dashboard/rulesets --jq '.[] | [.id, .name, .enforcement] | @tsv'

You should see `release`, `active`.

**Prove it holds.** Push a throwaway commit on top of `release` with your own credentials. It must be refused:

    c=$(git commit-tree "$(git hash-object -t tree /dev/null)" -p origin/release -m "probe: a hand push must be refused")
    git push origin "${c}:refs/heads/release"

GitHub answers `GH013: Repository rule violations … Cannot update this protected ref`, and `release` does not move.

## After the setup

**Step 5: the first promotion.** It runs on its own once the change that adds `promote.yml` (#614) is merged and its
`publish.yml` run is green. At any other time: Actions → promote → Run workflow on `main`, with no inputs. Then:

    git fetch origin release
    git log -1 --format=%s origin/release          # promote: main <sha>
    git ls-tree --name-only origin/release         # charts, environments, promotion.yaml

**Step 6: point the lab at `release` (optional).** During development the lab follows `main`. To use `release`, and
to switch back:

    local-development/release-crc.sh --argocd release
    local-development/release-crc.sh --argocd main

Each epic's post-release walk runs on `release`, then switches back.

## The record of this setup (2026-10-05, UTC)

| Step | Done by | Result |
|---|---|---|
| 1 | the operator | deploy key `promote-release`, `read_only=false`, created 00:54:42Z |
| 2 | the operator | environment `release`, one branch rule `main`; secret `RELEASE_DEPLOY_KEY` updated 00:58:04Z |
| 3 | the orchestrator | branch `release` at `1f3c3303f62d`, "release starts empty", 0 files |
| 4 | the orchestrator | ruleset `24475607` `release`, active, bypass `DeployKey`; GitHub accepted the deploy-key bypass on this user-owned repository, which settles SPEC_P1's open question 1 |
| proof | the orchestrator | a hand push was refused with `GH013 … Cannot update this protected ref`; `release` stayed at `1f3c3303f62d` |

Which commands were run against the repository on that day:
- **For real:** the ruleset `POST` and the hand-push proof (step 4), and `gh secret set` (step 2).
- **As harmless probes:**
  - the deploy-key `POST` (a read-only key, added and deleted at once);
  - the environment `PUT` (its own settings sent again);
  - the branch-policy `POST` (the existing `main` rule, not duplicated);
  - the empty-commit `POST` (a commit no branch points at).
- **Not run:** the `git/refs` call in step 3. The branch was created with the `git` form instead.

## Upkeep

- **Rotate the deploy key** (yearly, or if it may have leaked):
  1. Make a new pair and add it as in step 1, with a new title such as `promote-release-2027`.
  2. Run step 2's `gh secret set` with the new private half.
  3. Delete the old key: `gh api repos/ephico2real2/group-sync-dashboard/keys` lists the ids, then
     `gh repo deploy-key delete <id> -R ephico2real2/group-sync-dashboard`.
  4. Run the promote workflow by hand, to prove the new key works.
- **A promote run says the key is missing.** The environment or its secret is gone. Repeat step 2.
- **A promote run's push is refused.** The ruleset's bypass list has lost **Deploy keys**. Check step 4.
- **Undo the whole setup.** First point the lab at `main` (`release-crc.sh --argocd main`). Then delete, in this
  order:
  1. the ruleset (`gh api -X DELETE repos/ephico2real2/group-sync-dashboard/rulesets/<id>`);
  2. the branch;
  3. the environment;
  4. the deploy key.

## Words used on this page

- **Deploy key.** An SSH key that GitHub ties to one repository, not to a person.
- **Environment.** A GitHub setting that holds secrets and limits which branches' workflows may read them.
- **Ruleset.** A set of branch protections. Its **bypass list** names who may break them; here, only deploy keys.
- **Force push.** A push that rewrites a branch's history. It is blocked on `release`.
- **Digest.** The fixed fingerprint of an image (`sha256:…`). Unlike a tag, it can never point at a different
  image.
