"""Tests for higgsfield_api.py"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_get_jwt_from_cached_session():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jwt": "test.jwt.token"}
    with patch("httpx.Client.post", return_value=mock_resp):
        from higgsfield_api import _get_jwt_for_session
        token = _get_jwt_for_session("sess_abc123")
    assert token == "test.jwt.token"


def test_login_full_flow_prompts_otp_and_returns_jwt():
    sign_in_resp = MagicMock(status_code=200)
    sign_in_resp.json.return_value = {
        "response": {
            "id": "sia_test",
            "status": "needs_second_factor",
            "supported_second_factors": [
                {"strategy": "email_code", "email_address_id": "idn_test"}
            ],
        }
    }
    attempt_resp = MagicMock(status_code=200)
    attempt_resp.json.return_value = {
        "response": {"status": "complete", "created_session_id": "sess_new"}
    }
    jwt_resp = MagicMock(status_code=200)
    jwt_resp.json.return_value = {"jwt": "new.jwt.token"}

    with patch("builtins.input", return_value="123456"), \
         patch("higgsfield_api.SESSION_CACHE") as mock_cache, \
         patch("httpx.Client.post", side_effect=[
             sign_in_resp,
             MagicMock(status_code=200),  # prepare_second_factor
             attempt_resp,
             jwt_resp,
         ]):
        from higgsfield_api import login_full
        token = login_full("user@example.com", "password123")
    assert token == "new.jwt.token"
    mock_cache.write_text.assert_called_once_with("sess_new")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def test_upload_image_returns_media_id_and_url(tmp_path):
    img_path = tmp_path / "test.jpg"
    from PIL import Image as PILImage
    PILImage.new("RGB", (10, 10), color="red").save(img_path)

    batch_resp = MagicMock(status_code=200)
    batch_resp.json.return_value = [{
        "id": "media-abc123",
        "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_x/media-abc123.jpg",
        "upload_url": (
            "https://d276s3zg8h21b2.cloudfront.net/user_x/media-abc123.jpg"
            "?X-Amz-Signature=xyz"
        ),
        "content_type": "image/jpeg",
    }]
    put_resp = MagicMock(status_code=200)
    confirm_resp = MagicMock(status_code=200)
    confirm_resp.json.return_value = {"id": "media-abc123", "status": "uploaded"}

    with patch("httpx.Client.post", side_effect=[batch_resp, confirm_resp]), \
         patch("httpx.Client.put", return_value=put_resp):
        from higgsfield_api import upload_image
        media_id, cdn_url = upload_image("test.jwt", str(img_path))

    assert media_id == "media-abc123"
    assert "cloudfront" in cdn_url


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
def test_start_generation_returns_four_job_ids():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "id": "workspace-id",
        "job_sets": [{
            "id": "set-id",
            "jobs": [
                {"id": "job-1"}, {"id": "job-2"},
                {"id": "job-3"}, {"id": "job-4"},
            ],
        }],
    }
    with patch("httpx.Client.post", return_value=mock_resp):
        from higgsfield_api import start_generation
        job_ids = start_generation(
            "test.jwt",
            "media-abc",
            "https://cdn.example.com/media-abc.jpg",
            "3:4",
        )
    assert job_ids == ["job-1", "job-2", "job-3", "job-4"]


# ---------------------------------------------------------------------------
# Poll + share
# ---------------------------------------------------------------------------
def test_poll_jobs_returns_when_all_complete():
    in_progress = MagicMock(status_code=200)
    in_progress.json.return_value = {"status": "in_progress"}
    completed = MagicMock(status_code=200)
    completed.json.return_value = {"status": "completed"}

    with patch("httpx.Client.get", side_effect=[
        in_progress, in_progress, in_progress, in_progress,
        completed, completed, completed, completed,
    ]):
        with patch("time.sleep"):
            from higgsfield_api import poll_jobs
            poll_jobs("test.jwt", ["j1", "j2", "j3", "j4"])


def test_poll_jobs_raises_on_timeout():
    always_running = MagicMock(status_code=200)
    always_running.json.return_value = {"status": "in_progress"}
    with patch("httpx.Client.get", return_value=always_running):
        with patch("time.sleep"):
            from higgsfield_api import poll_jobs
            with pytest.raises(RuntimeError, match="timed out"):
                poll_jobs("test.jwt", ["j1"], timeout=-1)


def test_get_share_links_returns_higg_ai_urls():
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"share_url": "https://higg.ai/AbCdEfGhIjK"}
    with patch("httpx.Client.patch", return_value=mock_resp):
        from higgsfield_api import get_share_links
        links = get_share_links("test.jwt", ["j1", "j2", "j3", "j4"])
    assert links == ["https://higg.ai/AbCdEfGhIjK"] * 4


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------
def test_run_generation_returns_success(tmp_path):
    img_path = tmp_path / "test.jpg"
    from PIL import Image as PILImage
    PILImage.new("RGB", (1080, 1440)).save(img_path)

    with patch("higgsfield_api.get_jwt", return_value="jwt_tok"), \
         patch("higgsfield_api.upload_image",
               return_value=("media-id", "https://cdn.example.com/m.jpg")), \
         patch("higgsfield_api.start_generation",
               return_value=["j1", "j2", "j3", "j4"]), \
         patch("higgsfield_api.poll_jobs"), \
         patch("higgsfield_api.get_share_links",
               return_value=["u1", "u2", "u3", "u4"]), \
         patch.dict("os.environ", {
             "HIGGSFIELD_EMAIL": "user@example.com",
             "HIGGSFIELD_PASSWORD": "pw",
         }):
        from higgsfield_api import run_generation
        result = run_generation(str(img_path))

    assert result == {"status": "success", "links": ["u1", "u2", "u3", "u4"]}


def test_run_generation_returns_error_on_exception(tmp_path):
    img_path = tmp_path / "test.jpg"
    from PIL import Image as PILImage
    PILImage.new("RGB", (100, 100)).save(img_path)

    with patch("higgsfield_api.get_jwt",
               side_effect=RuntimeError("Login failed (401)")), \
         patch.dict("os.environ", {
             "HIGGSFIELD_EMAIL": "u@e.com",
             "HIGGSFIELD_PASSWORD": "pw",
         }):
        from higgsfield_api import run_generation
        result = run_generation(str(img_path))

    assert result["status"] == "error"
    assert "Login failed" in result["message"]


def test_run_generation_errors_without_credentials(tmp_path):
    img_path = tmp_path / "test.jpg"
    from PIL import Image as PILImage
    PILImage.new("RGB", (100, 100)).save(img_path)

    with patch.dict("os.environ", {}, clear=True):
        from higgsfield_api import run_generation
        result = run_generation(str(img_path))

    assert result["status"] == "error"
    assert "HIGGSFIELD_EMAIL" in result["message"]
