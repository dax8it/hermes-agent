---
name: openclaw-batch-agent-to-hermes-profiles
description: Batch-migrate multiple OpenClaw agents/workspaces into separate Hermes profiles with per-agent archive, identity, memory, cwd, and skill verification.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Migration, OpenClaw, Hermes, Profiles, Multi-Agent]
    related_skills: [openclaw-migration, openclaw-agent-to-hermes-profile]
---

# Batch OpenClaw Agent → Hermes Profiles

Use this skill for multiple OpenClaw agents/workspaces.

If you are migrating only one agent/workspace, use `openclaw-agent-to-hermes-profile` instead.

## When to Use
Use this when you need to migrate multiple OpenClaw agents/workspaces into separate Hermes profiles in one batch.

This is the multi-agent version of the single-agent migration runbook. It is for cases where you want:
- one Hermes profile per OpenClaw agent
- isolated identities and memory surfaces
- preserved workspace provenance
- runtime-usable profiles, not just archived copies

## Core Principle
Batch migration is just repeated true migration with stricter bookkeeping.

Do not treat batch work as a dumb copy loop.
Every agent still needs to be classified, archived, synthesized, and verified individually.

## Prerequisites
You need:
- a list of OpenClaw agents and their workspace roots
- a target Hermes profile name for each agent
- a known-good Hermes base profile to clone from
- shell access to copy files and inspect configs

Optional but useful:
- `openclaw.json`
- old agent directories
- shared skills directories

## What to Capture Per Agent
For each agent/workspace, inspect and preserve:
- `SOUL.md`
- `USER.md`
- `MEMORY.md` if present
- `IDENTITY.md`
- `BOOTSTRAP.md`
- `HEARTBEAT.md`
- `AGENTS.md`
- `TOOLS.md`
- full `memory/`
- full `skills/`
- any agent-specific config or role notes

If files are generic templates, archive them but do not automatically promote them into active Hermes identity.

## Batch Strategy
Process agents one by one in this order:
1. classify the workspace
2. clone or create the Hermes profile
3. archive the source workspace under `openclaw-workspace/`
4. synthesize active Hermes files
5. wire `terminal.cwd` and `skills.external_dirs`
6. verify the migrated profile
7. move to the next agent

This avoids batch-wide contamination from one bad workspace.

## Step 1 — Classify Each Workspace
For each agent, decide:
- Is `SOUL.md` real or generic?
- Is `USER.md` useful or template junk?
- Is `MEMORY.md` substantive or absent?
- Does `IDENTITY.md` carry the real persona?
- Does `memory/` contain the continuity you actually need?
- Does `skills/` contain local overrides or agent-specific tools?

Rules:
- generic `SOUL.md` does not beat a specific `IDENTITY.md`
- blank `MEMORY.md` is not a real memory source
- template `USER.md` should be archived, not treated as rich context

## Step 2 — Create or Clone the Hermes Profile
Preferred command pattern:
```bash
source venv/bin/activate && hermes profile create <name> --clone
```

Do this once per agent.

## Step 3 — Archive the Workspace
For each agent, create:
- `~/.hermes/profiles/<name>/openclaw-workspace/`

Copy into it every relevant source file that exists:
- root continuity files
- full `memory/`
- full `skills/`

The archive is your evidence trail and rollback point.

## Step 4 — Build Active Hermes State
For each profile, create/verify:
- `SOUL.md`
- `memories/MEMORY.md`
- `memories/USER.md`

Rules:
- active `SOUL.md` must describe the agent
- active `memories/MEMORY.md` must be non-empty and role-specific
- do not overwrite a richer Hermes `USER.md` with a blank template
- synthesize missing memory from identity files, recent notes, and role docs

## Step 5 — Update Config
For each profile, verify:
- `terminal.cwd` points to the agent’s OpenClaw workspace root
- `skills.external_dirs` includes the live OpenClaw `skills/` directory when present
- `model.default` is set only if the agent truly depends on a different default model

Keep archived snapshot and live skill loading distinct:
- `openclaw-workspace/` = frozen record
- `skills.external_dirs` = runtime load path

## Step 6 — Verify Per Agent
Do not call the batch complete until each profile passes:
- agent-specific active `SOUL.md`
- non-empty active `memories/MEMORY.md`
- archived `openclaw-workspace/`
- working `skills.external_dirs`
- correct runtime cwd
- at least one expected imported skill visible

## Step 7 — Verify the Batch as a Whole
After all agents are migrated, verify:
- each agent got the right profile name
- each profile has the right workspace root
- no profile was left with only template content
- no agent’s skills were pointed at the wrong workspace
- no archived snapshot was skipped

## Failure Modes
### One bad workspace contaminates the batch
Fix:
- stop the batch
- migrate the affected agent manually
- resume from the next clean agent

### Generic templates got copied into active files
Fix:
- replace active Hermes files with synthesized content from the authoritative sources

### A profile has archive but no live skills
Fix:
- add the live `skills/` directory to `skills.external_dirs`

### A profile has live skills but no archive
Fix:
- archive the source workspace before declaring success

## Completion Criteria
The batch is complete only when every agent has:
- preserved source-of-truth workspace archive
- agent-specific active persona
- non-empty active memory
- correct cwd
- working runtime skills

## Related References
- `openclaw-agent-to-hermes-profile`
- `references/batch-runbook.md`
- `references/batch-checklist.md`
