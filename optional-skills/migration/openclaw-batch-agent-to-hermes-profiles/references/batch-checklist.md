# Batch Migration Checklist

Use this checklist once per agent, then once across the batch.

## Per agent
- [ ] Workspace classified: real identity vs template files
- [ ] Hermes profile cloned from a known-good base
- [ ] `openclaw-workspace/` archive created
- [ ] Active `SOUL.md` is agent-specific
- [ ] Active `memories/MEMORY.md` is non-empty
- [ ] Active `memories/USER.md` is not degrading a richer profile
- [ ] `terminal.cwd` points to the workspace root
- [ ] `skills.external_dirs` includes the live workspace `skills/` directory
- [ ] At least one expected skill is visible

## Batch-wide
- [ ] Every agent has a unique target profile
- [ ] No workspace was skipped
- [ ] No profile points at the wrong `skills/` directory
- [ ] No profile was left with only copied templates
- [ ] All archives are present for audit and rollback
