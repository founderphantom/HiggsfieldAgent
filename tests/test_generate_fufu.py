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
    assert any(a.startswith("--user-data-dir=") and ".higgsfield-chrome" in a for a in launched_args)
    assert "--disable-blink-features=AutomationControlled" in launched_args


def test_timeout_raises_runtime_error():
    """Raise RuntimeError if Chrome never responds within the timeout window."""
    with patch("httpx.get", side_effect=httpx.ConnectError("connection refused")):
        with patch("subprocess.Popen") as mock_popen:
            with patch("time.sleep"):
                with pytest.raises(RuntimeError, match="Chrome did not start in time"):
                    ensure_chrome_ready("http://localhost:9222", timeout=-1)
            mock_popen.assert_called_once()


def test_run_generation_calls_ensure_chrome_ready():
    """run_generation() must call ensure_chrome_ready before attaching the browser."""
    with patch("generate_fufu.get_aspect_ratio_for_image", return_value="16:9"):
        with patch("generate_fufu.ensure_chrome_ready") as mock_ensure:
            with patch("generate_fufu.Browser") as mock_browser_cls:
                mock_browser = MagicMock()
                mock_browser.stop = AsyncMock()
                mock_browser_cls.return_value = mock_browser

                with patch("generate_fufu.ChatGoogle"):
                    with patch("generate_fufu.Agent") as mock_agent_cls:
                        mock_agent = MagicMock()
                        mock_agent_cls.return_value = mock_agent
                        mock_history = MagicMock()
                        mock_history.final_result.return_value = "FAILED: test"
                        mock_agent.run = AsyncMock(return_value=mock_history)

                        from generate_fufu import run_generation
                        asyncio.run(
                            run_generation("/fake/image.png", cdp_url="http://localhost:9222")
                        )

                        mock_ensure.assert_called_once_with("http://localhost:9222")
                        mock_browser_cls.assert_called_once_with(cdp_url="http://localhost:9222")
                        mock_browser.stop.assert_awaited_once()
