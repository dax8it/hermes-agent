---
name: openclaw-agent-to-hermes-profile
description: Migrate one OpenClaw agent/workspace into one Hermes profile, preserving source workspace truth while creating usable active Hermes state.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Migration, OpenClaw, Hermes, Profiles, Persona, Memory]
    related_skills: [openclaw-migration, openclaw-batch-agent-to-hermes-profiles]
---

# OpenClaw Agent → Hermes Profile

Use this skill for a single OpenClaw agent/workspace.

If you are migrating multiple agents/workspaces, use `openclaw-batch-agent-to-hermes-profiles` instead.

## When to Use
Use this when migrating one OpenClaw agent/workspace into one Hermes profile and you want a true migration, not just a shell clone.

This skill is for cases where you need to preserve:
- agent identity
- continuity files and daily notes
- local skill surface
- working directory/runtime setup

## Core Principle
True migration means two things at once:
1. preserve the original OpenClaw workspace truth
2. build active Hermes files that are actually usable

Do not confuse “copied files” with “correct migration.”
If the OpenClaw workspace contains generic templates, blindly copying them into active Hermes files can make the migration worse.

## Fast Decision Tree
- If `SOUL.md` is specific and good, adapt/promote it.
- If `SOUL.md` is generic but `IDENTITY.md` is specific, synthesize active Hermes `SOUL.md` from `IDENTITY.md` + recent `memory/` notes.
- If `MEMORY.md` exists and is substantive, copy/adapt it into `memories/MEMORY.md`.
- If `MEMORY.md` is missing or weak, synthesize `memories/MEMORY.md` from `IDENTITY.md`, `memory/`, active-task files, and role docs.
- If `USER.md` is blank template text, archive it but do not let it degrade the active Hermes user profile.
- If `skills/` exists, preserve it in the archive and also wire the live path into `skills.external_dirs`.

## What Success Looks Like
A correct migration yields:
- one isolated Hermes profile per former OpenClaw agent
- agent-specific `SOUL.md`
- non-empty, role-specific `memories/MEMORY.md`
- correct `terminal.cwd`
- working live skill imports via `skills.external_dirs`
- archived source-of-truth workspace snapshot under `openclaw-workspace/`

## Canonical Procedure
Use the runbook as the primary execution doc:
- `references/runbook.md`

## Quick Operator References
Use these alongside the runbook:
- `references/migration-checklist.md`
- `references/operator-notes.md`

## Critical Pitfalls
- `hermes profile create --clone` does not import OpenClaw continuity by itself.
- Blindly copying generic `SOUL.md` / `USER.md` is not migration.
- `skills.external_dirs` without an archived snapshot preserves runtime but loses provenance.
- An archived snapshot without `skills.external_dirs` preserves provenance but can break runtime usefulness.
- A true migration should not leave `memories/MEMORY.md` blank.
- If Hermes is not on PATH, use the working virtualenv or absolute binary path.

## Operator Guidance
Default to the runbook for sequence, the checklist for execution, and the operator notes for failure handling.
