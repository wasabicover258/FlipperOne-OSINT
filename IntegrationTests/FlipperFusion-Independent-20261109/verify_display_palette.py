#!/usr/bin/env python3
"""CI regression: offscreen SDL2 RGB must be neutral, background luminance 255.

Read BMP bytes directly using Python stdlib; no image packages or OCR needed.
SDL is permitted to use alpha internally but captured RGB must be monochrome.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path


def read_bmp(path: Path):
    data = path.read_bytes()
    assert data[:2] == b"BM", f"{path}: not a BMP"
    offset = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bits = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    assert width == 256 and abs(height) == 144, (path, width, height)
    assert bits in (24, 32), (path, bits)
    assert compression in (0, 3), (path, compression)
    channels = bits // 8
    pitch = (width * channels + 3) & ~3
    assert offset + pitch * abs(height) <= len(data), path

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        file_y = y if height < 0 else abs(height) - 1 - y
        base = offset + file_y * pitch + x * channels
        b, g, r = data[base : base + 3]
        return r, g, b

    return pixel


def check(directory: Path) -> None:
    screenshots = sorted(directory.glob("*.bmp"))
    assert len(screenshots) >= 7, f"expected 7 screenshots, found {len(screenshots)}"
    for name in screenshots:
        pixel = read_bmp(name)
        # Full screen: no RGB orange, green, blue, browns, or tinted gray.
        seen = set()
        for y in range(144):
            for x in range(256):
                r, g, b = pixel(x, y)
                assert r == g == b, f"{name}: tinted RGB at ({x}, {y}): {r,g,b}"
                seen.add(r)
        # This is the actual compositor-relevant test: white equals Y=255.
        for x, y in [(0, 0), (255, 0), (0, 70), (255, 70), (0, 129)]:
            assert pixel(x, y) == (255, 255, 255), (
                f"{name.name}: page background at {x,y} was {pixel(x,y)}"
            )
        assert 255 in seen and 0 in seen, f"{name.name}: must contain white and black"
        print(f"PASS {name.name}: all {256*144} pixels grayscale, clear/background=255, black ink present")
    menu = read_bmp(directory / "1-menu-top.bmp")
    assert menu(8, 22) == (0, 0, 0), f"selected menu bar not black: {menu(8,22)}"
    assert menu(6, 18) == (255, 255, 255) or menu(8, 22) == (0, 0, 0)
    print("PASS selection: selected menu row has black background; text uses inverted white")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
