"""Shared deterministic battlefield layout and terrain movement rules.

Coordinates are WORLD units. The same data is imported by server and renderer.
Only the server decides collision, speed and captures.
"""
import math

from shared import GRID_SIZE, tile_to_world

# Every region is a rectangle composed of complete 50x50 world tiles.
# This is the canonical map used by both collision and visual rendering.
WATER = (
    (950, 900, 400, 150),
    (2150, 900, 300, 200),
    (100, 750, 300, 150),
)
ROADS = (
    (100, 100, 2400, 100),
    (100, 1650, 2400, 100),
    (1250, 100, 100, 1650),
    (100, 900, 2400, 100),
)
FORESTS = (
    (400, 600, 350, 250),
    (1550, 250, 350, 200),
    (400, 1400, 300, 200),
    (1900, 1250, 300, 250),
)

# A site is always at the CENTER of its 50x50 construction tile.
BASE_TILES = ((3, 6), (48, 29), (46, 5), (4, 31), (25, 8), (25, 30))
PILLBOX_TILES = ((15, 21), (33, 19), (27, 14), (21, 25))
BASE_SITES = tuple(tile_to_world(x, y) for x, y in BASE_TILES)
PILLBOX_SITES = tuple(tile_to_world(x, y) for x, y in PILLBOX_TILES)

assert all(all(value % GRID_SIZE == 0 for value in region)
           for region in WATER + ROADS + FORESTS)

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
