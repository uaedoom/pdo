"""Tests for the shell tool and its dangerous-command detector."""
from __future__ import annotations

import pytest

from pdo.tools.shell import ShellTool, is_dangerous


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -rf ./build",
        "sudo apt-get install vim",
        "shutdown now",
        "reboot",
        "mkfs.ext4 /dev/sdb",
        "dd if=/dev/zero of=/dev/sda",
        ":(){:|:&};:",
        "rm *.py",
    ],
)
def test_dangerous_commands_are_flagged(command):
    dangerous, reason = is_dangerous(command)
    assert dangerous
    assert reason


@pytest.mark.parametrize(
    "command",
    ["ls -la", "echo hello", "python script.py", "git status", "cat file.txt"],
)
def test_safe_commands_are_allowed(command):
    dangerous, _ = is_dangerous(command)
    assert not dangerous


def test_custom_denylist_is_respected():
    dangerous, reason = is_dangerous("deploy --prod", denylist=["deploy --prod"])
    assert dangerous
    assert "denylist" in reason


def test_shell_cancels_dangerous_without_confirmation():
    tool = ShellTool(confirm=lambda _prompt: False)
    result = tool.run(command="rm -rf /tmp/whatever")
    assert "Cancelled" in result


def test_shell_runs_safe_command():
    tool = ShellTool(confirm=lambda _prompt: True)
    result = tool.run(command="echo pdo-test")
    assert "pdo-test" in result
    assert "[exit 0]" in result
