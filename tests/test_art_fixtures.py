import base64
import hashlib
import json
import shutil
import struct
import unittest
import zlib
from pathlib import Path
from uuid import uuid4

from tools.mod_cli import tracked


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/art"


def decode_png(data):
    """Read the fixture format only: unfiltered, non-interlaced RGBA8 PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature")
    offset = 8
    compressed = bytearray()
    while offset < len(data):
        size, tag = struct.unpack_from(">I4s", data, offset)
        payload = data[offset + 8 : offset + 8 + size]
        (crc,) = struct.unpack_from(">I", data, offset + 8 + size)
        if zlib.crc32(tag + payload) != crc:
            raise ValueError(f"invalid PNG checksum: {tag!r}")
        offset += size + 12
        if tag == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise ValueError("expected non-interlaced RGBA8")
        elif tag == b"IDAT":
            compressed.extend(payload)
        elif tag == b"IEND":
            break
    stride = 1 + width * 4
    raw = zlib.decompress(compressed)
    if len(raw) != stride * height or any(raw[::stride]):
        raise ValueError("expected full unfiltered scanlines")
    pixels = {}
    for y in range(height):
        for x in range(width):
            start = y * stride + 1 + x * 4
            rgba = tuple(raw[start : start + 4])
            if rgba[3] != 0:
                pixels[x, y] = rgba
    return [width, height], pixels


def asset_bytes(asset):
    return base64.b64decode(asset["png_base64"], validate=True)


def composite(fixture, direction):
    assets = fixture["assets"]
    variant = fixture["directions"][direction]
    preview = variant["preview"]
    origin_x, origin_y = preview["origin"]
    _, body = decode_png(asset_bytes(assets[variant["body"]]))
    _, apparel = decode_png(asset_bytes(assets[preview["apparel"]["path"]]))
    transform = fixture["renderer"][direction]
    worn_x, worn_y = transform["worn_offset"]
    node_x, node_y = transform["node_offset"]
    scale = transform["scale"]
    placed = {}
    for (x, y), rgba in apparel.items():
        left = origin_x + (x - origin_x) * scale + worn_x + node_x
        top = origin_y + (y - origin_y) * scale + worn_y + node_y
        for dy in range(scale):
            for dx in range(scale):
                placed[left + dx, top + dy] = rgba
    layers = {"body": body, "apparel": placed}
    order = sorted(layers, key=transform["layer_rank"].__getitem__)
    drawn = {}
    for layer in order:
        drawn.update(layers[layer])
    return order, placed, drawn


def flight_command(fixture, frame):
    x, z = frame["logical_xz"]
    dx, dz = frame["visual_offset_xz"]
    screen_x, screen_z = fixture["screen_pixels_per_tile_xz"]
    px, py = (x + dx) * screen_x, (z + dz) * screen_z
    origin_x, origin_y = fixture["png_origin_xy"]
    layer = frame["layer"]
    altitude = fixture["altitude_y"][layer]
    sort_keys = fixture["scene_altitude_y"] | {"drone": altitude}
    return {
        "draw_xz": [x + dx, z + dz],
        "screen_xy": [px, py],
        "sprite_top_left_xy": [px - origin_x, py - origin_y],
        "screen_delta_xy": [dx * screen_x, dz * screen_z],
        "layer": layer,
        "altitude_y": altitude,
        "back_to_front": sorted(sort_keys, key=sort_keys.__getitem__),
        "shader": frame["shader"],
    }


class ArtFixtureTest(unittest.TestCase):
    def load_fixture(self, name):
        path = FIXTURES / name
        self.assertTrue(path.is_file(), f"Missing executable fixture: {name}")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_preview_reuses_exported_png_with_unchanged_canvas_and_origin(self):
        fixture = self.load_fixture("apparel-multidirection.json")
        self.assertEqual({"south", "east", "north"}, set(fixture["directions"]))
        template = fixture["template"]
        paths = set()
        hashes = set()
        for direction, variant in fixture["directions"].items():
            with self.subTest(direction=direction):
                path = variant["export"]
                asset = fixture["assets"][path]
                data = asset_bytes(asset)
                digest = hashlib.sha256(data).hexdigest()
                paths.add(path)
                hashes.add(digest)
                self.assertEqual(asset["sha256"], digest)
                self.assertEqual(
                    {"path": path, "sha256": digest}, variant["preview"]["apparel"]
                )
                canvas, pixels = decode_png(data)
                body = fixture["assets"][variant["body"]]
                body_bytes = asset_bytes(body)
                self.assertEqual(body["sha256"], hashlib.sha256(body_bytes).hexdigest())
                body_canvas, _ = decode_png(body_bytes)
                self.assertEqual(template["canvas"], canvas)
                self.assertEqual(canvas, body_canvas)
                self.assertEqual(canvas, variant["preview"]["canvas"])
                self.assertEqual(template["origin"], asset["origin"])
                self.assertEqual(template["origin"], variant["preview"]["origin"])
                self.assertEqual(
                    {tuple(point) for point in variant["export_opaque_xy"]},
                    pixels.keys(),
                )
                self.assertLess(len(pixels), canvas[0] * canvas[1])
        self.assertEqual(3, len(paths))
        self.assertEqual(3, len(hashes))

    def test_apparel_composite_applies_directional_renderer_transforms_and_order(self):
        fixture = self.load_fixture("apparel-multidirection.json")
        width, height = fixture["template"]["canvas"]
        palette = {
            symbol: tuple(rgba) for symbol, rgba in fixture["palette"].items()
        }
        orders = {}
        for direction, variant in fixture["directions"].items():
            with self.subTest(direction=direction):
                order, placed, drawn = composite(fixture, direction)
                expected = variant["expected_preview"]
                orders[direction] = order
                self.assertEqual(expected["back_to_front"], order)
                self.assertEqual(
                    {tuple(point) for point in expected["apparel_opaque_xy"]},
                    placed.keys(),
                )
                self.assertTrue(all(0 <= x < width and 0 <= y < height for x, y in drawn))
                golden = [
                    [palette[symbol] for symbol in row] for row in expected["rows"]
                ]
                actual = [
                    [drawn.get((x, y), palette["."]) for x in range(width)]
                    for y in range(height)
                ]
                self.assertEqual(golden, actual)
        self.assertNotEqual(orders.get("south"), orders.get("north"))

    def test_flight_frames_project_xz_and_sort_across_pawn_and_building(self):
        fixture = self.load_fixture("flight-render-space.json")
        self.assertEqual(
            ["takeoff", "cruise", "descent"],
            [frame["phase"] for frame in fixture["frames"]],
        )
        for frame in fixture["frames"]:
            with self.subTest(phase=frame["phase"]):
                self.assertEqual(frame["expected"], flight_command(fixture, frame))

    def test_flight_position_sorting_and_shader_can_change_independently(self):
        fixture = self.load_fixture("flight-render-space.json")
        cruise = fixture["frames"][1]
        cruise_command = flight_command(fixture, cruise)
        controls = fixture["cruise_controls"]
        self.assertCountEqual(
            [{"layer"}, {"visual_offset_xz"}, {"shader"}],
            [set(control["replace"]) for control in controls],
        )
        for variant in controls:
            with self.subTest(control=variant["name"]):
                observed = flight_command(fixture, cruise | variant["replace"])
                changes = {
                    key: value
                    for key, value in observed.items()
                    if value != cruise_command[key]
                }
                self.assertEqual(variant["expected_changes"], changes)

    def test_tracked_excludes_local_references_but_keeps_release_apparel(self):
        fixture = self.load_fixture("apparel-multidirection.json")
        reference = ".local/art-references/fixture-adult/body_south.png"
        apparel = "Textures/Things/Apparel/FixturePack_south.png"
        root = ROOT / f".test-art-package-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        for rel in (reference, apparel):
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_bytes(asset_bytes(fixture["assets"][rel]))
        self.assertEqual({apparel: fixture["assets"][apparel]["sha256"]}, tracked(root))


if __name__ == "__main__":
    unittest.main()
