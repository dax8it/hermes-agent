from __future__ import annotations

from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


@dataclass
class _CompletedProcess:
    stdout: str


def _load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "continuity" / "update_implementation_status.py"
    spec = spec_from_file_location("update_implementation_status", script_path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_continuity_git_timeline_includes_path_scoped_commits():
    module = _load_module()

    def fake_runner(command, **kwargs):
        if "--" in command:
            return _CompletedProcess(
                stdout=(
                    "2b4d967a\tfeat(continuity): add guarded dashboard actions\n"
                    "49dcb8dc\tfix(api): allow same-origin continuity panel actions\n"
                )
            )
        return _CompletedProcess(
            stdout=(
                "e6a52075\tfix(config): keep continuity defaults migration-free\n"
                "2b4d967a\tfeat(continuity): add guarded dashboard actions\n"
                "deadbeef\tfix(api): unrelated endpoint cleanup\n"
            )
        )

    assert module._continuity_git_timeline(runner=fake_runner) == [
        ("e6a52075", "fix(config): keep continuity defaults migration-free"),
        ("2b4d967a", "feat(continuity): add guarded dashboard actions"),
        ("49dcb8dc", "fix(api): allow same-origin continuity panel actions"),
    ]
