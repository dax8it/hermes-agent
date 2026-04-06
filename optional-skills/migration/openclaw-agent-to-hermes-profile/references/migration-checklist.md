# OpenClaw → Hermes Migration Checklist

Use this as the literal execution checklist for one agent/workspace.

## 0) Identify the source of truth
Mark each as present / absent:
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
- `openclaw.json`

If `SOUL.md` or `USER.md` look generic, treat them as templates until `IDENTITY.md` and `memory/` prove otherwise.

## 1) Decide what becomes active Hermes state
Active Hermes files:
- `SOUL.md`
- `memories/MEMORY.md`
- `memories/USER.md`

Archive everything else under `openclaw-workspace/`.

Rules:
- Never leave `memories/MEMORY.md` empty for a true migration.
- Never overwrite a richer Hermes `USER.md` with a blank template.
- Never copy a generic OpenClaw `SOUL.md` into active Hermes if `IDENTITY.md` contains the real agent identity.

## 2) Archive the OpenClaw workspace
Copy the full workspace tree you care about into:
- `~/.hermes/profiles/<name>/openclaw-workspace/`

Include:
- all root continuity files
- full `memory/`
- full `skills/`

## 3) Build the active profile
Set:
- `terminal.cwd` to the OpenClaw workspace root
- `skills.external_dirs` to the live OpenClaw `skills/` directory
- `SOUL.md` to a real agent identity description
- `memories/MEMORY.md` to a distilled continuity summary

## 4) Verify
At minimum verify:
- active `SOUL.md` is agent-specific
- active `memories/MEMORY.md` is non-empty
- archived snapshot exists
- live `skills.external_dirs` resolves
- profile starts in the right cwd
