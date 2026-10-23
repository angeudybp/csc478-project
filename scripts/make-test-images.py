#!/usr/bin/env python3
"""Write the test inputs for smoke.sh and evidence.sh into a directory.

Standard library only (PNG is written by hand with zlib), so it runs on any
machine with python3 -- including FABRIC VMs without Pillow -- and no binary
test files need to live in the repository.
"""
import os
import struct
import sys
import zlib
from pathlib import Path


def png(width: int, height: int, rows) -> bytes:
    """Encode an 8-bit RGB PNG; ``rows`` yields ``width * 3`` bytes per row."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + row for row in rows)  # Filter type 0 (None) on every row.
    level = 0 if len(raw) > 4_000_000 else 6  # Random data does not compress; skip the work.
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level))
            + chunk(b"IEND", b""))


def gradient_rows(width: int, height: int):
    for y in range(height):
        g = 80 + 150 * y // height
        yield bytes(v for x in range(width) for v in (255 * x // width, g, 255 - 255 * x // width))


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    # T1: an ordinary image.
    (out / "sample.png").write_bytes(png(640, 480, gradient_rows(640, 480)))
    # T3: ~7.5 MB, just under the 8 MB limit (random pixels so it cannot compress).
    side = 1580
    (out / "near-limit.png").write_bytes(png(side, side, (os.urandom(side * 3) for _ in range(side))))
    # T2: 12 MB that starts with JPEG magic bytes, so only the size check can reject it.
    (out / "too-large.jpg").write_bytes(b"\xff\xd8\xff" + os.urandom(12 * 1024 * 1024))
    # T4: a text file pretending to be a JPEG.
    (out / "not-an-image.jpg").write_text("this is a text file, not a JPEG\n")
    # T5: valid images in formats the pipeline does not accept.
    (out / "pixel.gif").write_bytes(bytes.fromhex(
        "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"))
    (out / "vector.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>\n')
    # T6: an empty file.
    (out / "empty.jpg").write_bytes(b"")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <output-dir>")
    main(Path(sys.argv[1]))
