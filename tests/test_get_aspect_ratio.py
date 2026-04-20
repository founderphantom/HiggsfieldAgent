import subprocess
import sys
import os
import tempfile

import pytest
from PIL import Image

SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "get_aspect_ratio.py"
)

# Higgsfield Soul v2 aspect ratio options (confirm during integration):
# 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9

def _run(width: int, height: int) -> str:
    """Create a temp image of given dimensions, run the script, return stdout."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (width, height), color="red")
        img.save(f, format="PNG")
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    finally:
        os.unlink(tmp_path)


def test_square_image():
    assert _run(1024, 1024) == "1:1"


def test_portrait_9_16():
    # 1080x1920 is exactly 9:16
    assert _run(1080, 1920) == "9:16"


def test_landscape_16_9():
    # 1920x1080 is exactly 16:9
    assert _run(1920, 1080) == "16:9"


def test_portrait_3_4():
    # 768x1024 is exactly 3:4
    assert _run(768, 1024) == "3:4"


def test_landscape_4_3():
    # 1024x768 is exactly 4:3
    assert _run(1024, 768) == "4:3"


def test_portrait_2_3():
    # 800x1200 is exactly 2:3
    assert _run(800, 1200) == "2:3"


def test_landscape_3_2():
    # 1200x800 is exactly 3:2
    assert _run(1200, 800) == "3:2"


def test_near_square_rounds_to_1_1():
    # 1000x1050 is close to 1:1
    assert _run(1000, 1050) == "1:1"


def test_iphone_photo_maps_to_3_4():
    # 3024x4032 = 3:4 ratio
    assert _run(3024, 4032) == "3:4"


def test_ultrawide_maps_to_16_9():
    # 2560x1080 ~= 2.37:1 — closest standard is 16:9 (1.78)
    assert _run(2560, 1080) == "16:9"


def test_missing_file_exits_nonzero():
    result = subprocess.run(
        [sys.executable, SCRIPT, "/nonexistent/image.png"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
