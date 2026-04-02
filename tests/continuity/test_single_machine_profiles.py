"""Single-machine multi-profile isolation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_cli.gateway import get_service_name
from hermes_cli.profiles import create_profile, resolve_profile_env
from honcho_integration.cli import _write_config


@pytest.fixture()
def isolated_profiles(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    default_home = home / ".hermes"
    default_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setenv("HERMES_HOME", str(default_home))
    return {"home": home, "default_home": default_home}


def test_two_profiles_keep_distinct_homes_honcho_configs_and_gateway_names(isolated_profiles, monkeypatch):
    alpha_dir = create_profile("alpha", no_alias=True)
    beta_dir = create_profile("beta", no_alias=True)

    (alpha_dir / "config.yaml").write_text("terminal:\n  cwd: /tmp/alpha-worktree\n", encoding="utf-8")
    (beta_dir / "config.yaml").write_text("terminal:\n  cwd: /tmp/beta-worktree\n", encoding="utf-8")

    assert resolve_profile_env("alpha") == str(alpha_dir)
    assert resolve_profile_env("beta") == str(beta_dir)

    monkeypatch.setenv("HERMES_HOME", str(alpha_dir))
    _write_config({"apiKey": "alpha-key", "hosts": {"hermes": {"workspace": "/tmp/alpha-worktree"}}})
    alpha_service = get_service_name()

    monkeypatch.setenv("HERMES_HOME", str(beta_dir))
    _write_config({"apiKey": "beta-key", "hosts": {"hermes": {"workspace": "/tmp/beta-worktree"}}})
    beta_service = get_service_name()

    assert alpha_service == "hermes-gateway-alpha"
    assert beta_service == "hermes-gateway-beta"
    assert alpha_service != beta_service

    alpha_honcho = json.loads((alpha_dir / "honcho.json").read_text(encoding="utf-8"))
    beta_honcho = json.loads((beta_dir / "honcho.json").read_text(encoding="utf-8"))
    assert alpha_honcho["apiKey"] == "alpha-key"
    assert beta_honcho["apiKey"] == "beta-key"
    assert alpha_honcho["hosts"]["hermes"]["workspace"] == "/tmp/alpha-worktree"
    assert beta_honcho["hosts"]["hermes"]["workspace"] == "/tmp/beta-worktree"
