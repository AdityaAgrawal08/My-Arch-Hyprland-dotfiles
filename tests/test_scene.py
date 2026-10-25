#!/usr/bin/env python3
"""Regression tests for the Pillow-only scene analyser."""

from __future__ import annotations

import argparse
import colorsys
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

LIB = Path(__file__).resolve().parents[1] / "hypr/.config/hypr/scripts/lib"
sys.path.insert(0, str(LIB))

import build_theme  # noqa: E402
import scene  # noqa: E402
import vibrant  # noqa: E402


def gradient(
    size: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        amount = y / (size - 1)
        colour = tuple(
            int(first + (second - first) * amount) for first, second in zip(top, bottom)
        )
        draw.line([(0, y), (size, y)], fill=colour)
    return image


def sky_subject_image() -> Image.Image:
    size = 256
    image = gradient(size, (60, 120, 190), (130, 185, 235))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 158, size, size), fill=(48, 48, 48))
    draw.rectangle((100, 100, 156, 156), fill=(240, 120, 30))
    return image


def landscape_image() -> Image.Image:
    size = 256
    image = gradient(size, (60, 120, 190), (130, 185, 235))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, int(size * 0.60), size, size), fill=(40, 110, 40))
    draw.rectangle((110, 140, 146, 176), fill=(170, 40, 35))
    draw.polygon([(100, 140), (156, 140), (128, 120)], fill=(90, 30, 25))
    return image


def monochrome_with_red_subject() -> Image.Image:
    image = gradient(256, (20, 20, 20), (210, 210, 210))
    draw = ImageDraw.Draw(image)
    draw.rectangle((112, 112, 144, 144), fill=(220, 30, 30))
    return image


def sunset_image() -> Image.Image:
    size = 256
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        if y < int(size * 0.55):
            amount = y / (size * 0.55)
            colour = (
                int(30 + 55 * amount),
                int(45 + 30 * amount),
                int(100 + 40 * amount),
            )
        elif y < int(size * 0.75):
            amount = (y - size * 0.55) / (size * 0.20)
            colour = (
                int(250 - 20 * amount),
                int(160 - 45 * amount),
                int(90 + 55 * amount),
            )
        else:
            amount = (y - size * 0.75) / (size * 0.25)
            colour = (
                int(55 + 10 * amount),
                int(40 + 10 * amount),
                int(85 + 15 * amount),
            )
        draw.line([(0, y), (size, y)], fill=colour)
    return image


def blue_dominant_image() -> Image.Image:
    size = 256
    image = gradient(size, (30, 80, 160), (60, 120, 200))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 200, size, size), fill=(20, 40, 90))
    draw.ellipse((118, 118, 138, 138), fill=(80, 200, 200))
    return image


def forest_image() -> Image.Image:
    size = 256
    rng = random.Random(7)
    image = gradient(size, (28, 64, 32), (54, 110, 48))
    draw = ImageDraw.Draw(image)
    for _ in range(180):
        x = rng.randrange(size)
        y = rng.randrange(size)
        width = rng.randrange(6, 26)
        height = rng.randrange(6, 26)
        green = rng.randrange(90, 190)
        red = rng.randrange(20, 70)
        blue = rng.randrange(20, 70)
        draw.ellipse((x, y, x + width, y + height), fill=(red, green, blue))
    return image


def hue_of(value: str) -> float:
    red, green, blue = (component / 255.0 for component in vibrant.hex_to_rgb(value))
    return colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0


class SceneTests(unittest.TestCase):
    def test_sky_subject_seed_is_not_the_sky(self) -> None:
        image = sky_subject_image()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        self.assertIn("seed", result)
        self.assertLess(vibrant.hue_distance(hue_of(result["seed"]), 30.0), 35.0)
        self.assertGreater(result["scene"]["metrics"]["skyFraction"], 0.30)
        self.assertIn("sky-water", [tag["name"] for tag in result["scene"]["tags"]])

    def test_scene_off_keeps_the_old_blue_result(self) -> None:
        image = sky_subject_image()
        result = vibrant.extract_image(image, scene_mode="off")
        self.assertNotIn("scene", result)
        self.assertNotIn("seed", result)
        self.assertLess(vibrant.hue_distance(hue_of(result["accent"]), 215.0), 35.0)

    def test_landscape_demotes_the_sky_for_a_green_seed(self) -> None:
        image = landscape_image()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        tags = {tag["name"]: tag["confidence"] for tag in result["scene"]["tags"]}
        self.assertGreaterEqual(tags.get("nature", 0.0), 0.5)
        self.assertGreater(result["scene"]["metrics"]["greenFraction"], 0.20)
        self.assertLess(vibrant.hue_distance(hue_of(result["seed"]), 120.0), 50.0)

    def test_sunset_uses_a_warm_seed(self) -> None:
        image = sunset_image()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        tags = {tag["name"]: tag["confidence"] for tag in result["scene"]["tags"]}
        self.assertGreaterEqual(tags.get("sunset", 0.0), 0.5)
        hue = hue_of(result["seed"])
        self.assertTrue(hue < 90.0 or hue > 300.0, hue)

    def test_blue_dominant_image_keeps_a_blue_seed(self) -> None:
        image = blue_dominant_image()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        metrics = result["scene"]["metrics"]
        self.assertGreater(metrics["blueFraction"], 0.70)
        self.assertLess(metrics["greenFraction"], 0.05)
        hue = hue_of(result["seed"])
        self.assertTrue(190.0 <= hue <= 265.0, hue)

    def test_forest_prefers_a_nature_strategy(self) -> None:
        image = forest_image()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        tags = {tag["name"]: tag["confidence"] for tag in result["scene"]["tags"]}
        self.assertGreaterEqual(tags.get("nature", 0.0), 0.5)
        self.assertEqual(result["scene"]["strategy"]["scheme"], "scheme-content")
        self.assertLess(vibrant.hue_distance(hue_of(result["seed"]), 120.0), 45.0)

    def test_monochrome_image_uses_neutral_strategy(self) -> None:
        image = gradient(256, (14, 14, 14), (226, 226, 226))
        result = vibrant.extract_image(image, scene_mode="heuristic")
        self.assertTrue(result["grayscale"])
        self.assertNotIn("seed", result)
        tags = {tag["name"] for tag in result["scene"]["tags"]}
        self.assertIn("monochrome", tags)
        self.assertEqual(result["scene"]["strategy"]["scheme"], "scheme-monochrome")

    def test_small_colour_subject_survives_a_monochrome_scene(self) -> None:
        image = monochrome_with_red_subject()
        result = vibrant.extract_image(image, scene_mode="heuristic")
        self.assertFalse(result["grayscale"])
        self.assertIn("seed", result)
        hue = hue_of(result["accent"])
        self.assertTrue(hue < 20.0 or hue > 340.0, hue)

    def test_scene_failure_emits_a_degraded_marker(self) -> None:
        image = sky_subject_image()
        with mock.patch.object(
            vibrant, "analyze_scene", side_effect=RuntimeError("boom")
        ):
            result = vibrant.extract_image(image, scene_mode="heuristic")
        self.assertTrue(result["scene"]["degraded"])
        self.assertEqual(result["scene"]["mode"], "degraded")
        self.assertEqual(result["scene"]["version"], scene.VERSION)
        self.assertNotIn("seed", result)

    def test_low_key_image_darkens_the_strategy(self) -> None:
        image = Image.new("RGB", (256, 256), (10, 16, 30))
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 60, 220, 200), fill=(20, 40, 80))
        draw.ellipse((112, 112, 140, 140), fill=(220, 150, 80))
        result = vibrant.extract_image(image, scene_mode="heuristic")
        tags = {tag["name"]: tag["confidence"] for tag in result["scene"]["tags"]}
        self.assertGreaterEqual(tags.get("low-key", 0.0), 0.5)
        self.assertLess(result["scene"]["strategy"]["lightnessDark"], 0.0)

    def test_high_key_image_lightens_the_strategy(self) -> None:
        image = Image.new("RGB", (256, 256), (228, 220, 210))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 210, 256, 256), fill=(70, 70, 70))
        result = vibrant.extract_image(image, scene_mode="heuristic")
        tags = {tag["name"]: tag["confidence"] for tag in result["scene"]["tags"]}
        self.assertGreaterEqual(tags.get("high-key", 0.0), 0.5)
        self.assertGreaterEqual(result["scene"]["strategy"]["lightnessDark"], 0.0)

    def test_seed_png_matches_the_seed_colour(self) -> None:
        image = sky_subject_image()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "seed.png"
            result = vibrant.extract_image(
                image, scene_mode="heuristic", seed_out=output
            )
            self.assertTrue(output.is_file())
            with Image.open(output) as seed:
                self.assertEqual(seed.size, (64, 64))
                self.assertEqual(
                    "#%02x%02x%02x" % seed.convert("RGB").getpixel((0, 0)),
                    result["seed"],
                )

    def test_region_weights_downweight_sky_and_ground(self) -> None:
        metrics = {"skyFraction": 0.5, "groundFraction": 0.5}
        rows = scene.row_weights(100, metrics)
        self.assertLess(rows[0], rows[50])
        self.assertLess(rows[-1], rows[50])
        columns = scene.column_weights(100)
        self.assertLess(columns[0], columns[50])
        self.assertLess(columns[-1], columns[50])

    def test_flat_image_attention_is_neutral(self) -> None:
        image = Image.new("RGB", (128, 128), (40, 60, 80))
        attention = scene.build_attention(image)
        self.assertEqual(len(attention), scene.ATTENTION_SIZE**2)
        self.assertTrue(all(value == 128 for value in attention))

    def test_non_rgb_images_are_accepted(self) -> None:
        attention = scene.build_attention(Image.new("L", (64, 64), 128))
        self.assertEqual(len(attention), scene.ATTENTION_SIZE**2)
        result = vibrant.extract_image(
            Image.new("L", (128, 128), 128), scene_mode="heuristic"
        )
        self.assertTrue(result["grayscale"])

    def test_loading_applies_exif_orientation(self) -> None:
        image = Image.new("RGB", (64, 32), (40, 80, 120))
        exif = Image.Exif()
        exif[274] = 6
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotated.jpg"
            image.save(path, exif=exif.tobytes())
            loaded = vibrant.load_image(path)
        self.assertEqual(loaded.size, (32, 64))


class ThemeGuardrailTests(unittest.TestCase):
    def test_scene_seed_aligns_surface_and_enforces_contrast(self) -> None:
        roles = {
            "surface": "#101820",
            "on_surface": "#8090a0",
            "on_surface_variant": "#506070",
            "outline": "#506070",
            "outline_variant": "#203040",
            "error": "#ff5555",
        }
        accents = {
            "grayscale": False,
            "seed": "#50c0a0",
            "accent": "#402020",
            "accent_soft": "#203040",
            "ansi": {},
            "scene": {
                "version": 3,
                "confidence": 1.0,
                "degraded": False,
                "tags": [{"name": "warm", "confidence": 1.0}],
                "strategy": {
                    "scheme": "scheme-fidelity",
                    "surfaceTint": 1.0,
                    "borderContrast": 0.8,
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            roles_path = Path(directory) / "roles.json"
            accents_path = Path(directory) / "accents.json"
            roles_path.write_text(json.dumps(roles), encoding="utf-8")
            accents_path.write_text(json.dumps(accents), encoding="utf-8")
            args = argparse.Namespace(
                roles=roles_path,
                accents=accents_path,
                wallpaper=Path("/tmp/wallpaper.jpg"),
                mtime=1,
                fallback="dark",
            )
            theme = build_theme.build(args)

        self.assertEqual(theme["scene"]["seed"], "#50c0a0")
        surface_hue = hue_of(theme["bg"])
        original_hue = hue_of("#101820")
        seed_hue = hue_of("#50c0a0")
        self.assertGreater(vibrant.hue_distance(surface_hue, original_hue), 1.0)
        self.assertLess(
            vibrant.hue_distance(surface_hue, seed_hue),
            vibrant.hue_distance(original_hue, seed_hue),
        )
        self.assertGreaterEqual(build_theme.contrast(theme["fg"], theme["bg"]), 7.0)
        self.assertGreaterEqual(build_theme.contrast(theme["muted"], theme["bg"]), 4.5)
        self.assertGreaterEqual(build_theme.contrast(theme["accent"], theme["bg"]), 4.5)
        self.assertGreaterEqual(
            build_theme.contrast(theme["accentSoft"], theme["bg"]), 4.0
        )

    def test_degraded_scene_marker_builds_a_valid_theme(self) -> None:
        roles = {
            "surface": "#101010",
            "on_surface": "#e0e0e0",
            "on_surface_variant": "#a0a0a0",
            "outline": "#808080",
            "outline_variant": "#303030",
            "error": "#ff5555",
        }
        accents = {
            "grayscale": False,
            "accent": "#d17e61",
            "accent_soft": "#5c96c1",
            "ansi": {},
            "scene": {
                "version": 3,
                "mode": "degraded",
                "confidence": 0.0,
                "degraded": True,
                "tags": [],
                "metrics": {},
                "strategy": {},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            roles_path = Path(directory) / "roles.json"
            accents_path = Path(directory) / "accents.json"
            roles_path.write_text(json.dumps(roles), encoding="utf-8")
            accents_path.write_text(json.dumps(accents), encoding="utf-8")
            args = argparse.Namespace(
                roles=roles_path,
                accents=accents_path,
                wallpaper=Path("/tmp/wallpaper.jpg"),
                mtime=1,
                fallback="dark",
            )
            theme = build_theme.build(args)

        self.assertEqual(theme["scene"]["mode"], "degraded")
        self.assertTrue(theme["scene"]["degraded"])
        self.assertIn("bg", theme)
        self.assertIn("accent", theme)
        self.assertIn("fg", theme)

    def test_invalid_scene_metadata_does_not_break_theme(self) -> None:
        roles = {
            "surface": "#101010",
            "on_surface": "#e0e0e0",
            "on_surface_variant": "#a0a0a0",
            "outline": "#808080",
            "outline_variant": "#303030",
            "error": "#ff5555",
        }
        accents = {
            "grayscale": False,
            "seed": "#cc7050",
            "accent": "#d17e61",
            "accent_soft": "#5c96c1",
            "ansi": {},
            "scene": {
                "version": "not-a-number",
                "confidence": "nan",
                "degraded": False,
                "tags": [],
                "strategy": {
                    "scheme": "scheme-fidelity",
                    "surfaceTint": "nan",
                    "borderContrast": "inf",
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            roles_path = Path(directory) / "roles.json"
            accents_path = Path(directory) / "accents.json"
            roles_path.write_text(json.dumps(roles), encoding="utf-8")
            accents_path.write_text(json.dumps(accents), encoding="utf-8")
            args = argparse.Namespace(
                roles=roles_path,
                accents=accents_path,
                wallpaper=Path("/tmp/wallpaper.jpg"),
                mtime=1,
                fallback="dark",
            )
            theme = build_theme.build(args)

        self.assertEqual(theme["scene"]["version"], 1)
        self.assertEqual(theme["scene"]["confidence"], 0.0)
        self.assertIn("bg", theme)
        self.assertIn("accent", theme)
        self.assertIn("fg", theme)


if __name__ == "__main__":
    unittest.main()
