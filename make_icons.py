"""Generate the PNG app icons for the PWA manifest.

Pure standard library (no Pillow needed). Draws the same "attic" mark as
favicon.svg, supersamples it for smooth edges, and writes three PNGs:

    app/static/icons/icon-192.png
    app/static/icons/icon-512.png
    app/static/icons/icon-maskable-512.png

Run once from the project root:

    python make_icons.py
"""

import math
import struct
import sys
import zlib
from pathlib import Path

TEAL = (20, 184, 166, 255)
DARK = (4, 32, 29, 255)

# Shapes in 32-unit space (same geometry as favicon.svg).
OUTLINE = [
    (16.0, 5.5), (25.5, 13.9), (23.1, 13.9), (23.1, 25.0),
    (8.9, 25.0), (8.9, 13.9), (6.5, 13.9),
]
CIRCLE = (16.0, 18.2, 3.6)
CROSS = [((16.0, 14.7), (16.0, 21.7)), ((12.5, 18.2), (19.5, 18.2))]
STROKE_OUTLINE = 2.1
STROKE_RING = 1.1
STROKE_CROSS = 1.1
RADIUS = 7.0


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    abx, aby = bx - ax, by - ay
    length_sq = abx * abx + aby * aby
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / length_sq))
    return math.hypot(px - (ax + t * abx), py - (ay + t * aby))


def _polyline_dist(p, points):
    best = float("inf")
    for i in range(len(points)):
        best = min(best, _seg_dist(p, points[i], points[(i + 1) % len(points)]))
    return best


def _inside_rounded_rect(p, size, radius):
    px, py = p
    cx = cy = size / 2.0
    hw = size / 2.0 - radius
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hw, 0.0)
    return math.hypot(dx, dy) <= radius


def _sample(p, maskable):
    """Return RGBA at 32-space coordinate p (float tuple)."""
    stroke = _polyline_dist(p, OUTLINE) <= STROKE_OUTLINE / 2.0
    if not stroke:
        ring = abs(math.hypot(p[0] - CIRCLE[0], p[1] - CIRCLE[1]) - CIRCLE[2])
        stroke = ring <= STROKE_RING / 2.0
    if not stroke:
        for a, b in CROSS:
            if _seg_dist(p, a, b) <= STROKE_CROSS / 2.0:
                stroke = True
                break
    if stroke:
        return DARK
    if maskable or _inside_rounded_rect(p, 32.0, RADIUS):
        return TEAL
    return (0, 0, 0, 0)


def render(size, maskable=False, ss=4):
    """Render an icon, supersampling `ss`x`ss` per output pixel."""
    eff = size if not maskable else size * 0.66
    n32 = eff / 32.0
    off = (size - eff) / 2.0

    raw = bytearray()
    for y in range(size):
        row = bytearray(b"\x00")
        for x in range(size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss
                    py = y + (sy + 0.5) / ss
                    u = (px - off) / n32
                    v = (py - off) / n32
                    rgba = _sample((u, v), maskable)
                    r += rgba[0]
                    g += rgba[1]
                    b += rgba[2]
                    a += rgba[3]
            count = ss * ss
            row.extend((round(r / count), round(g / count), round(b / count), round(a / count)))
        raw += row
    return bytes(raw)


def _png(width, height, rows):
    """rows is the full scanline stream, each row beginning with filter byte 0."""
    def chunk(chunk_type, data):
        payload = chunk_type + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    body = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
    return body


def write_png(path, size, maskable=False):
    rows = render(size, maskable=maskable)  # already includes the filter byte per row
    with open(path, "wb") as f:
        f.write(_png(size, size, rows))
    print(f"wrote {path.name} ({size}x{size})")


def main():
    icons_dir = Path("app/static/icons")
    icons_dir.mkdir(parents=True, exist_ok=True)
    write_png(icons_dir / "icon-192.png", 192, maskable=False)
    write_png(icons_dir / "icon-512.png", 512, maskable=False)
    write_png(icons_dir / "icon-maskable-512.png", 512, maskable=True)
    print("done")


if __name__ == "__main__":
    sys.exit(main())