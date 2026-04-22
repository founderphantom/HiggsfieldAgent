"""Tests for generate_fufu helper functions."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_fufu import ensure_chrome_ready


def test_already_running_does_not_launch_chrome():
    """If Chrome answers on the CDP port, return without launching a new process."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        with patch("subprocess.Popen") as mock_popen:
            ensure_chrome_ready("http://localhost:9222")
            mock_get.assert_called_once_with(
                "http://localhost:9222/json/version", timeout=2.0
            )
            mock_popen.assert_not_called()


def test_not_running_launches_chrome_with_correct_args():
    """If Chrome is not running, launch it with the required flags."""
    call_count = 0

    def fake_get(url, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("httpx.get", side_effect=fake_get):
        with patch("subprocess.Popen") as mock_popen:
            with patch("time.sleep"):
                ensure_chrome_ready("http://localhost:9222", timeout=5)

    mock_popen.assert_called_once()
    launched_args = mock_popen.call_args[0][0]
    assert launched_args[0] == "google-chrome"
    assert "--remote-debugging-port=9222" in launched_args
    assert any("--user-data-dir=" in a for a in launched_args)
    assert "--disable-blink-features=AutomationControlled" in launched_args


def test_timeout_raises_runtime_error():
    """Raise RuntimeError if Chrome never responds within the timeout window."""
    with patch("httpx.get", side_effect=httpx.ConnectError("connection refused")):
        with patch("subprocess.Popen"):
            with patch("time.sleep"):
                # timeout=-1 → deadline is already past → polling loop never runs
                with pytest.raises(RuntimeError, match="Chrome did not start in time"):
                    ensure_chrome_ready("http://localhost:9222", timeout=-1)
