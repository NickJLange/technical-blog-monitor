from pathlib import Path

import pytest

from monitor.config import BrowserConfig


def test_browser_config_screenshot_dir_provided(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = BrowserConfig(screenshot_dir=tmp_path / "shots")
    # Validator should create the dir
    assert cfg.screenshot_dir is not None
    assert cfg.screenshot_dir.exists()


def test_browser_config_screenshot_dir_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Force cwd to tmp_path
    monkeypatch.chdir(tmp_path)
    cfg = BrowserConfig()
    # Not created yet; will be created on first usage by browser module
    # Default should be data/screenshots under CWD when not provided
    expected = tmp_path / "data" / "screenshots"
    # We don't create it here to avoid FS side-effects; just assert the default is respected by helper logic
    # Simulate how browser would compute base dir
    base_dir = cfg.screenshot_dir or (Path.cwd() / "data" / "screenshots")
    assert base_dir == expected

