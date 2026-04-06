# Migrating OpenClaw Agents into Hermes Profiles

This guide covers the advanced migration path for users who had multiple named OpenClaw agents or separate OpenClaw workspaces and now want one Hermes profile per agent.

Examples:
- Filippo → Hermes profile `filippo`
- Smarty → Hermes profile `smarty`
- Sparky → Hermes profile `sparky`
- Huggy → Hermes profile `huggy`

## Pick the Right Migration Tier

### Tier 1 — import one OpenClaw footprint into the current Hermes home
Use this when you want to bring your main OpenClaw setup into your current Hermes installation:

```bash
hermes claw migrate
```

That path is documented here:
- `docs/migration/openclaw.md`
- `website/docs/guides/migrate-from-openclaw.md`

It is the right choice for:
- one primary OpenClaw setup
- one current Hermes home
- direct import of persona, memory, skills, config, and compatible secrets

### Tier 2 — convert OpenClaw agents/workspaces into separate Hermes profiles
Use this when you want one Hermes profile per former OpenClaw agent.

This is the right choice for:
- named specialist agents
- separate OpenClaw workspaces
- per-agent identity and memory isolation
- preserving each source workspace while still making the resulting Hermes profile usable

## What Makes Profile Migration Different

A profile migration is not just “copy files into a new folder.”

A correct migration does two things at the same time:
1. preserves the OpenClaw workspace as evidence and rollback state
2. creates active Hermes files that are actually useful at runtime

That means separating:
- archived source truth under `openclaw-workspace/`
- active Hermes state under `SOUL.md`, `memories/`, and `config.yaml`

If you blindly copy generic template files into active Hermes state, you can make the migration worse.

## Shareable Assets in This Repo

### Public CLI/script path
- `hermes claw migrate`
- `optional-skills/migration/openclaw-migration/SKILL.md`
- `optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py`
- `docs/migration/openclaw.md`
- `website/docs/guides/migrate-from-openclaw.md`

### Public profile-migration skills
Single agent:
- `optional-skills/migration/openclaw-agent-to-hermes-profile/SKILL.md`
- `optional-skills/migration/openclaw-agent-to-hermes-profile/references/runbook.md`
- `optional-skills/migration/openclaw-agent-to-hermes-profile/references/migration-checklist.md`
- `optional-skills/migration/openclaw-agent-to-hermes-profile/references/operator-notes.md`

Batch / multi-agent:
- `optional-skills/migration/openclaw-batch-agent-to-hermes-profiles/SKILL.md`
- `optional-skills/migration/openclaw-batch-agent-to-hermes-profiles/references/batch-runbook.md`
- `optional-skills/migration/openclaw-batch-agent-to-hermes-profiles/references/batch-checklist.md`

## Single-Agent Workflow

Use the `openclaw-agent-to-hermes-profile` skill when migrating one agent/workspace.

Core procedure:
1. inspect and classify the OpenClaw workspace files
2. create or clone the target Hermes profile
3. archive the source workspace under `openclaw-workspace/`
4. build active Hermes `SOUL.md`, `memories/MEMORY.md`, and `memories/USER.md`
5. wire `terminal.cwd`
6. wire `skills.external_dirs`
7. verify the migrated profile is actually usable

Use this skill when you care about preserving:
- role-specific identity
- continuity notes and daily memory
- runtime working directory
- live access to the old workspace skills surface

## Batch / Multi-Agent Workflow

Use the `openclaw-batch-agent-to-hermes-profiles` skill when migrating many agents/workspaces.

Core rule:
- one agent, one profile, one archive

Process agents one by one:
1. classify workspace
2. create/clone target profile
3. archive source workspace
4. build active Hermes files
5. set runtime cwd and live skill directories
6. verify the profile
7. move to the next agent

Do not treat batch migration as a dumb copy loop. Each agent still needs separate classification and verification.

## Recommended Commands

Create a profile from a known-good base:
```bash
source venv/bin/activate && hermes profile create <name> --clone
```

Inspect a migrated profile:
```bash
source venv/bin/activate && hermes -p <name> profile show <name>
```

Export a migrated profile for sharing or backup:
```bash
source venv/bin/activate && hermes profile export <name> -o <name>.tar.gz
```

Import that profile elsewhere:
```bash
source venv/bin/activate && hermes profile import <name>.tar.gz --name <name>
```

## Success Criteria

A profile migration is complete only when all of the following are true:
- the source workspace is preserved under `openclaw-workspace/`
- active `SOUL.md` is agent-specific
- active `memories/MEMORY.md` is non-empty and role-specific
- `terminal.cwd` points at the correct workspace
- `skills.external_dirs` points at the live skills path when needed
- at least one expected imported skill is visible to Hermes

## Common Failure Modes

### Generic templates got copied into active state
Fix:
- regenerate active `SOUL.md` and memory from `IDENTITY.md`, continuity notes, and role docs

### Archive exists but runtime skills do not load
Fix:
- add the live workspace `skills/` directory to `skills.external_dirs`

### Runtime works but provenance was lost
Fix:
- copy the full source workspace into `openclaw-workspace/`

### A blank `USER.md` degraded the profile
Fix:
- restore the richer Hermes `memories/USER.md`
- keep the OpenClaw `USER.md` only as archived source material

## Bottom Line

Use `hermes claw migrate` for the basic one-home import.
Use the profile-migration skills when you want the “Filippo / Smarty / Sparky / Huggy” style result: one real Hermes profile per former OpenClaw agent, with preserved source truth and usable live state.
