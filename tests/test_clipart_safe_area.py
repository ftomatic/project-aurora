"""Tests for transparent clipart canvas safe-area validation."""

from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from project_aurora.image_generation.clipart_safe_area import (
    normalize_complete_clipart_safe_area,
    validate_clipart_safe_area,
)


class ClipartSafeAreaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rejects_visible_artwork_touching_canvas_edges(self) -> None:
        path = self.base_path / "clipped.png"
        image = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        for x in range(0, 90):
            for y in range(10, 100):
                image.putpixel((x, y), (80, 60, 40, 255))
        image.save(path)

        errors = validate_clipart_safe_area(path)

        self.assertEqual(len(errors), 1)
        self.assertIn("left 0.0%", errors[0])
        self.assertIn("bottom 0.0%", errors[0])

    def test_accepts_artwork_with_five_percent_clear_margin(self) -> None:
        path = self.base_path / "safe.png"
        image = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        for x in range(10, 90):
            for y in range(10, 90):
                image.putpixel((x, y), (80, 60, 40, 255))
        image.save(path)

        self.assertEqual(validate_clipart_safe_area(path), ())

    def test_normalizes_complete_edge_near_artwork_inside_safe_area(self) -> None:
        path = self.base_path / "complete_botanical.png"
        image = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        for x in range(3, 97):
            for y in range(1, 99):
                image.putpixel((x, y), (80, 120, 40, 255))
        image.save(path)

        normalize_complete_clipart_safe_area(path)

        self.assertEqual(validate_clipart_safe_area(path), ())
        with Image.open(path) as normalized:
            self.assertEqual(normalized.size, (100, 100))
            self.assertEqual(normalized.mode, "RGBA")
