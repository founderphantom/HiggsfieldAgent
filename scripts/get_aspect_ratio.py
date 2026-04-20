#!/usr/bin/env python3
"""Given an image path, print the closest Higgsfield aspect ratio to stdout.

Usage:
    python get_aspect_ratio.py <image_path>

Output (stdout):
    One of: 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9
"""
import sys
from PIL import Image

# Higgsfield Soul v2 aspect ratio options.
# Each entry is (label, width/height ratio).
RATIOS = [
    ("1:1", 1.0),
    ("2:3", 2 / 3),
    ("3:2", 3 / 2),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
]


def closest_ratio(width: int, height: int) -> str:
    actual = width / height
    best_label = RATIOS[0][0]
    best_diff = abs(actual - RATIOS[0][1])
    for label, ratio in RATIOS[1:]:
        diff = abs(actual - ratio)
        if diff < best_diff:
            best_diff = diff
            best_label = label
    return best_label


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: get_aspect_ratio.py <image_path>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        with Image.open(path) as img:
            width, height = img.size
    except (FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(closest_ratio(width, height))


if __name__ == "__main__":
    main()
