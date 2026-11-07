---
allowed-tools:
  - Bash(git:*)
  - Bash(gh pr create:*)
  - Bash(gh pr view:*)
  - Bash(python scripts/check_version.py:*)
  - Read
  - Edit
  - Write
  - AskUserQuestion
---

You are preparing a release of this Home Assistant integration. Branch model:
`develop` is the work in progress, `main` is the released state. A release is a
pull request from `develop` into `main`; merging it runs
`.github/workflows/release.yaml`, which checks the version, runs the tests and
validation, and creates the tag `vX.Y.Z` and the GitHub release. Never push to
`main` directly and never create tags yourself.

Work through the steps in order.

## 1. Inspect the current state

- Make sure the current branch is `develop` (`git branch --show-current`); stop and
  tell the user if it is not.
- Run `git fetch --tags origin`, `git status` and `git diff HEAD`.
- Read the version from `custom_components/blood_glucose_monitor/manifest.json`
  and the newest tag from `git tag --list 'v*' --sort=-v:refname | head -1`.
- List the commits since that tag: `git log --oneline <tag>..HEAD` (all commits if
  there is no tag yet).
- Read the `## [Unreleased]` section of `CHANGELOG.md`.

## 2. Check the documentation

Compare `README.md` and the translations with the changes. Ask the user:

```
AskUserQuestion: "Does the README need updates before this release? Here is what I found: [gaps, or 'Nothing — README matches the current code']."
Options: ["README is fine as-is", "Please update it as described"]
```

Apply the updates if wanted.

## 3. Group uncommitted changes into conventional commits

`feat:` (new user-visible functionality), `fix:`, `docs:`, `chore:`, `refactor:`,
`test:`. One commit per type, split only if changes of one type are unrelated.
Never stage with `git add -A`; name the files.

## 4. Determine the version

- No tag yet: release the version that is already in `manifest.json`.
- Otherwise apply semver to the commits since the newest tag and the new
  commits: `BREAKING CHANGE` → major, any `feat:` → minor, else patch. While
  the major version is 0, a breaking change bumps the minor version.

## 5. Draft the release plan

Ask for one confirmation before touching git:

```
AskUserQuestion: "Release plan — confirm to proceed:

Commits:
  [each proposed commit message with its files]

CHANGELOG entry:
  ## [A.B.C] - YYYY-MM-DD
  ### Added / Changed / Fixed / Removed
  - ...

Version: X.Y.Z → A.B.C (newest tag: vX.Y.Z or none)
Then: push develop and open a pull request develop → main."
Options: ["Proceed", "Cancel — I'll make changes first"]
```

Stop if the user cancels.

## 6. Prepare the release on develop

1. Create the commits from step 3 (`git add <files>`, `git commit -m "<type>: …"`).
2. Set `"version"` in `custom_components/blood_glucose_monitor/manifest.json`.
3. In `CHANGELOG.md`, turn the `## [Unreleased]` content into
   `## [A.B.C] - YYYY-MM-DD` (today, Keep a Changelog sections) and leave an
   empty `## [Unreleased]` section above it. Entries describe user-visible
   behaviour, in English.
4. Run `python scripts/check_version.py --release`; fix any error it reports.
5. Commit: `git add custom_components/blood_glucose_monitor/manifest.json CHANGELOG.md`
   and `git commit -m "chore(release): vA.B.C"`.
6. Push: `git push origin develop`.
7. Open the pull request:
   `gh pr create --base main --head develop --title "Release vA.B.C" --body-file <file>`
   with the CHANGELOG section of the version as body.

Report the pull request URL. Tell the user to merge it with a **merge commit**
(not squash or rebase, so `develop` and `main` keep a shared history) once the
checks are green; the release workflow then creates tag and release.
