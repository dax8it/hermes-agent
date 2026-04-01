"""Tests for CLI /continuity command dispatch."""

from unittest.mock import patch

from cli import HermesCLI


class TestCLIContinuityCommand:
    def _make_cli(self):
        cli_obj = HermesCLI.__new__(HermesCLI)
        cli_obj._app = None
        cli_obj._last_invalidate = 0.0
        cli_obj._command_running = False
        cli_obj._command_status = ""
        return cli_obj

    def test_continuity_command_dispatches_to_handler(self):
        cli_obj = self._make_cli()
        with patch.object(cli_obj, "_handle_continuity_command") as mock_handle:
            assert cli_obj.process_command("/continuity benchmark")
        mock_handle.assert_called_once_with("/continuity benchmark")
