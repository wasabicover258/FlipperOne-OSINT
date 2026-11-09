#!/usr/bin/env python3
"""Validate the exact tiny Flipper app-shelf icon using Python stdlib only.

The Flipper UI treats PNG alpha as a mask, not as a colored picture.
The icon must be a non-opaque 14x14 RGBA PNG with binary alpha.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import zlib

WANTED_SHA256 = "50cd6f3d12c91bab53e77bda510412fcb6147ea4628d48449581417f19e0b167"

def check_icon(path: Path) -> None:
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == WANTED_SHA256, "PNG differs from the user-supplied 14x14 icon"
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), "Not a PNG file"
    off = 8
    packed = bytearray()
    width = height = None
    while off + 12 <= len(data):
        size = struct.unpack_from(">I", data, off)[0]
        kind = data[off + 4:off + 8]
        off += 8
        chunk = data[off:off + size]
        checksum = struct.unpack_from(">I", data, off + size)[0]
        assert zlib.crc32(kind + chunk) & 0xFFFFFFFF == checksum, "Corrupt PNG chunk"
        off += size + 4
        if kind == b"IHDR":
            width, height, depth, color, compress, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            assert (width, height) == (14, 14), f"Expected 14x14, got {width}x{height}"
            assert (depth, color, compress, filtering, interlace) == (8, 6, 0, 0, 0), "PNG must be RGBA, 8-bit, non-interlaced"
        elif kind == b"IDAT":
            packed.extend(chunk)
        elif kind == b"IEND":
            break
    assert width == 14 and height == 14 and packed, "Missing PNG pixel data"
    raw = zlib.decompress(packed)
    stride = width * 4
    assert len(raw) == height * (stride + 1), "Unexpected PNG pixel payload"

    row_before = bytearray(stride)
    opaque = clear = 0
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        assert filter_type in (0, 1, 2, 3, 4), f"Bad PNG scanline filter {filter_type}"
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            above = row_before[i]
            upper_left = row_before[i - 4] if i >= 4 else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 255
            elif filter_type == 2:
                row[i] = (row[i] + above) & 255
            elif filter_type == 3:
                row[i] = (row[i] + ((left + above) // 2)) & 255
            elif filter_type == 4:
                p = left + above - upper_left
                a, b, c = abs(p - left), abs(p - above), abs(p - upper_left)
                predictor = left if a <= b and a <= c else above if b <= c else upper_left
                row[i] = (row[i] + predictor) & 255
        for alpha in row[3::4]:
            assert alpha in (0, 255), f"Alpha={alpha}; antialiasing is forbidden"
            opaque += int(alpha == 255)
            clear += int(alpha == 0)
        row_before = row
    assert (opaque, clear) == (40, 156), f"Unexpected alpha mask: {opaque} filled, {clear} transparent"
    print(f"PASS: {path}: 14x14 RGBA with 40 opaque symbol pixels, 156 transparent pixels; no antialiasing")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_shelf_icon.py <appimage-root-or-AppDir>")
    directory = Path(sys.argv[1])
    assert 'name = "OSINT"' in (directory / "app.toml").read_text(), "Wrong shelf name"
    assert 'icon = "flipperone-osint.png"' in (directory / "app.toml").read_text(), "Wrong root icon reference"
    check_icon(directory / "flipperone-osint.png")
