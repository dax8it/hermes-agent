# Operator Notes

## Copy / archive layout
For a migration of `<agent>` from OpenClaw to Hermes, the target profile should end up like this:

```text
~/.hermes/profiles/<agent>/
├── SOUL.md
├── memories/
│   ├── MEMORY.md
│   └── USER.md
├── openclaw-workspace/
│   ├── SOUL.md
│   ├── USER.md
│   ├── AGENTS.md
│   ├── TOOLS.md
│   ├── IDENTITY.md
│   ├── BOOTSTRAP.md
│   ├── HEARTBEAT.md
│   ├── memory/
│   └── skills/
└── config.yaml
```

## Command templates
Use these as starting points and substitute the real profile name and paths.

Create profile:
```bash
source venv/bin/activate && hermes profile create <name> --clone
```

Inspect profile:
```bash
source venv/bin/activate && hermes -p <name> profile show <name>
```

Read active persona:
```bash
python - <<'PY'
from pathlib import Path
base = Path.home() / '.hermes' / 'profiles' / '<name>'
print((base / 'SOUL.md').read_text())
print((base / 'memories' / 'MEMORY.md').read_text())
PY
```

Check external skills:
```bash
source venv/bin/activate && HERMES_HOME=/Users/you/.hermes/profiles/<name> python - <<'PY'
from agent.skill_utils import get_external_skills_dirs
print([str(p) for p in get_external_skills_dirs()])
PY
```

## Failure modes
- Blank template copied into active memory: fix by synthesizing `memories/MEMORY.md` from `IDENTITY.md` and `memory/`.
- Generic OpenClaw `SOUL.md` copied verbatim: fix by synthesizing a real Hermes persona from workspace identity files.
- Archived snapshot exists but runtime skills are missing: fix by setting `skills.external_dirs` to the live workspace `skills/` directory.
- `USER.md` contains no user facts: archive it, but do not treat it as meaningful continuity.
- A workspace has no `MEMORY.md`: do not skip the migration; synthesize one from the available sources.
- `hermes` not found on PATH: use the installed virtualenv or absolute binary path.
