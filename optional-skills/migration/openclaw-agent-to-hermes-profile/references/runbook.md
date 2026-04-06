# Runbook: OpenClaw Agent → Hermes Profile

Use this runbook when migrating one OpenClaw agent/workspace into one Hermes profile.

## Goal
Produce a Hermes profile that is both:
- faithful to the original OpenClaw workspace
- actually usable at runtime inside Hermes

That means preserving raw source material and also constructing non-generic active Hermes files.

## Prerequisites
You need:
- the OpenClaw workspace path
- the target Hermes profile name
- a working Hermes profile to clone from
- shell access to copy files and inspect configs

Optional but useful:
- access to `openclaw.json`
- access to the old agent directory if one exists

## Step 1 — Inspect the workspace and classify files
Inspect these if present:
- `SOUL.md`
- `USER.md`
- `MEMORY.md`
- `IDENTITY.md`
- `BOOTSTRAP.md`
- `HEARTBEAT.md`
- `AGENTS.md`
- `TOOLS.md`
- `memory/`
- `skills/`

Classify each file as one of:
- authoritative active identity
- useful archived continuity
- generic template / bootstrap artifact

Rules:
- If `SOUL.md` is generic and `IDENTITY.md` is specific, trust `IDENTITY.md` more.
- If `MEMORY.md` is missing, recent `memory/` notes become the best continuity source.
- If `USER.md` is blank template text, preserve it in the archive but do not promote it over richer Hermes user context.

## Step 2 — Create the Hermes profile
Preferred command:
```bash
source venv/bin/activate && hermes profile create <name> --clone
```

Why clone:
- inherits a sane `config.yaml`
- inherits working `.env`
- avoids rebuilding auth/runtime basics from scratch

## Step 3 — Archive the original OpenClaw workspace inside the Hermes profile
Create:
- `~/.hermes/profiles/<name>/openclaw-workspace/`

Copy into that snapshot every relevant source-of-truth file that exists:
- `SOUL.md`
- `USER.md`
- `AGENTS.md`
- `TOOLS.md`
- `MEMORY.md`
- `IDENTITY.md`
- `BOOTSTRAP.md`
- `HEARTBEAT.md`
- full `memory/`
- full `skills/`

Why:
- this preserves what OpenClaw actually knew at migration time
- this gives you rollback and auditability
- this prevents loss when active Hermes files are synthesized rather than copied verbatim

## Step 4 — Build active Hermes identity files
The active Hermes profile should use:
- `SOUL.md`
- `memories/MEMORY.md`
- `memories/USER.md`

### 4A. Build `SOUL.md`
Do not blindly copy the OpenClaw `SOUL.md`.

Instead:
- if OpenClaw `SOUL.md` is already agent-specific, adapt or promote it
- if OpenClaw `SOUL.md` is generic, synthesize Hermes `SOUL.md` from:
  - `IDENTITY.md`
  - role-specific notes
  - recent `memory/` files
  - active-task files

### 4B. Build `memories/MEMORY.md`
A true migration must leave this file non-empty.

Preferred order:
1. copy substantive OpenClaw `MEMORY.md`
2. otherwise synthesize from:
   - `IDENTITY.md`
   - recent `memory/` notes
   - active tasks / role docs
   - stable operating boundaries

### 4C. Build `memories/USER.md`
- if OpenClaw `USER.md` has real user-specific facts, copy/adapt it
- if it is blank template text, archive it only
- do not overwrite richer Hermes user context with a worse file

## Step 5 — Update the Hermes profile config
Set or verify:
- `terminal.cwd` = OpenClaw workspace root
- `model.default` = OpenClaw agent model if known and still desired
- `skills.external_dirs` includes the live OpenClaw `skills/` directory when present

Important distinction:
- `openclaw-workspace/` = frozen archive
- `skills.external_dirs` = live runtime skill loading

You usually want both.

## Step 6 — Verify the migration
Do not stop at file copy success. Verify usability.

Required checks:
1. `SOUL.md` is agent-specific and non-generic
2. `memories/MEMORY.md` is non-empty and role-specific
3. archived `openclaw-workspace/` exists
4. `skills.external_dirs` resolves correctly
5. the profile starts in the right cwd
6. at least one expected imported skill is visible to Hermes

## Step 7 — Fix common bad outcomes
### Bad outcome: active `SOUL.md` is generic
Fix:
- regenerate from `IDENTITY.md` + role notes + `memory/`

### Bad outcome: active `memories/MEMORY.md` is empty or shallow
Fix:
- synthesize from recent continuity artifacts instead of leaving the file blank

### Bad outcome: archived snapshot exists but live skills are missing
Fix:
- add the live OpenClaw `skills/` path to `skills.external_dirs`

### Bad outcome: copied `USER.md` degraded the profile
Fix:
- restore the richer Hermes `memories/USER.md`
- keep the OpenClaw `USER.md` only in the archive if it was template junk

## Completion criteria
The migration is complete only when all of the following are true:
- raw OpenClaw continuity is archived
- active Hermes persona is agent-specific
- active Hermes memory is non-empty and role-specific
- runtime cwd is correct
- runtime skill loading works

## Related references
- `references/migration-checklist.md`
- `references/operator-notes.md`
