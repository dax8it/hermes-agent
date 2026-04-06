# Batch Runbook: OpenClaw Agents → Hermes Profiles

This runbook is the batch controller for migrating many agents. Execute the single-agent migration procedure once per agent, in a controlled loop.

## Objective
Migrate each OpenClaw agent into its own Hermes profile without cross-contamination.

## Batch Rules
- One agent, one profile, one archive.
- Never assume two workspaces are interchangeable.
- Never promote generic templates into active state.
- Verify each agent before proceeding to the next.

## Loop Structure
For each agent:
1. inspect workspace and classify files
2. create/clone target Hermes profile
3. archive source workspace under `openclaw-workspace/`
4. synthesize active Hermes `SOUL.md`
5. synthesize or copy `memories/MEMORY.md`
6. verify `memories/USER.md` is not degrading the profile
7. set `terminal.cwd`
8. wire `skills.external_dirs`
9. verify runtime skill visibility
10. mark agent complete and proceed

## Stop Conditions
Stop the batch if:
- a workspace is too ambiguous to classify
- a synthesized active file would be too generic to trust
- runtime skill loading fails
- the target profile points at the wrong workspace

## Recovery
If an agent fails:
- fix that agent manually
- verify it independently
- only then continue the batch

## Batch Completion
The batch is complete only when:
- every agent has a preserved archive
- every active profile is agent-specific
- every profile has non-empty memory
- every profile has correct cwd
- every profile loads the expected skills
