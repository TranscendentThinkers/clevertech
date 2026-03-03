# Contributing Guide — Clevertech App

## Git Workflow

### Branch Structure

| Branch | Purpose |
|---|---|
| `main` | **Always = UAT signed-off code.** Production deploys from here only. |
| `feature/<name>` | Active development. Created from `main`, tagged and deleted after merge. |

> **Rule:** `main` is sacrosanct. It reflects exactly what is running and signed off on UAT.

---

### Daily Developer Discipline

**Before starting any work — compare with GitHub first, do NOT pull blindly:**
```bash
cd /home/bharatbodh/bharatbodh-bench/apps/clevertech
git fetch origin

# Check if GitHub has anything UAT doesn't
git log --oneline HEAD..origin/main
# Empty → UAT is ahead, safe to proceed without pulling
# Not empty → review those commits before deciding to pull
```

> UAT is always the source of truth. Never pull from GitHub without first checking what it contains.

**After every working session — commit and push everything:**
```bash
git add -A
git commit -m "Brief description of what changed"
git push origin main
```

> **Never leave uncommitted changes overnight.**

---

### For New Features or Bug Fixes

```bash
# 1. Create a feature branch from main
git checkout -b feature/your-feature-name

# 2. Work and commit regularly — commit as often as needed (every iteration, every fix)
#    All these commits are your learning/development history — don't worry about quantity
git add -A
git commit -m "Add: description of change"

# 3. Push to GitHub regularly
git push origin feature/your-feature-name

# 4. After UAT sign-off → raise PR to main on GitHub
#    On GitHub, choose "Squash and merge" — all commits squashed into 1 clean commit on main
#    Write a meaningful single commit message summarising the entire feature

# 5. Before deleting the branch — tag it to preserve full development history
git tag archive/your-feature-name origin/feature/your-feature-name
git push origin archive/your-feature-name

# 6. Delete the feature branch (history is safe in the tag)
git push origin --delete feature/your-feature-name
git checkout main
```

> **Why Squash and Merge?**
> - `main` stays clean — one meaningful commit per feature
> - Feature branch had 15 iterations? All preserved in the `archive/` tag forever
> - GitHub Tags section becomes your full development archive
> - Branch list stays clean with only active work visible

---

### Commit Message Convention

```
Fix: <what was broken and how it was fixed>
Add: <new feature or file added>
Update: <what was modified and why>
Docs: <documentation-only change>
```

**Examples:**
```
Fix: block loose items in Phase 1 BOM upload for leaf nodes
Add: project_tracking report for BOM hierarchy view
Update: make/buy defaults — M/G=Make, D=blank, others=Buy
Docs: architectural_decisions — loose item blocking scope
```

---

### Production Deploy Rule

- Production **only pulls from `main`**
- Never edit files directly on the production server
- If a hotfix is needed on prod → fix on UAT first → push to `main` → pull on prod

---

### Verify Sync Before Ending Session

```bash
# Check nothing is left uncommitted or unstaged
git status

# Check nothing is left unpushed (UAT → GitHub)
git log --oneline origin/main..HEAD
# Empty = UAT is fully pushed to GitHub ✓

# Check GitHub has nothing UAT hasn't reviewed
git log --oneline HEAD..origin/main
# Empty = GitHub has nothing new ✓
# Not empty = review before pulling
```
