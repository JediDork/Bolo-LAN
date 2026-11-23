"""Shared deterministic battlefield layout and terrain movement rules.

Coordinates are WORLD units. The same data is imported by server and renderer.
Only the server decides collision, speed and captures.
"""
import math

# Rectangles (x, y, width, height). Water is impassable, forest slows tanks.
WATER = (
    (950, 910, 380, 145),
    (2140, 915, 290, 160),
    (120, 760, 260, 140),
)
ROADS = (
    (85, 125, 2400, 72),
    (85, 1680, 2400, 70),
    (1260, 125, 75, 1625),
    (110, 935, 2390, 70),
)
FORESTS = (
    (380, 620, 360, 235),
    (1560, 270, 340, 210),
    (380, 1400, 290, 220),
    (1890, 1280, 310, 210),
)

# Each base has a refill and capture zone. Neutral until occupied.
BASE_SITES = (
    (180, 335), (2410, 1470), (2320, 260), (240, 1570),
    (1270, 430), (1270, 1540),
)
# Pillboxes begin neutral/hostile, and can be destroyed.
PILLBOX_SITES = (
    (770, 1050), (1690, 990), (1380, 740), (1060, 1280),
)


def in_rect(x, y, rect, margin=0):
    rx, ry, width, height = rect
    return rx - margin <= x <= rx + width + margin and ry - margin <= y <= ry + height + margin


def water_at(x, y, radius=0):
    """Conservative circle-vs-rectangle water collision."""
    for wx, wy, ww, wh in WATER:
        px = max(wx, min(wx + ww, x))
        py = max(wy, min(wy + wh, y))
        if (x - px) ** 2 + (y - py) ** 2 < radius ** 2:
            return True
        if radius == 0 and in_rect(x, y, (wx, wy, ww, wh)):
            return True
    return False


def terrain_at(x, y):
    if water_at(x, y):
        return "water"
    if any(in_rect(x, y, rect) for rect in FORESTS):
        return "forest"
    if any(in_rect(x, y, rect) for rect in ROADS):
        return "road"
    return "grass"


TERRAIN_SPEED = {"grass": 1.0, "road": 1.20, "forest": 0.65, "water": 0.0}
