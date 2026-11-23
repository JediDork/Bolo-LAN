"""Shared protocol and deterministic world constants."""
import math
import random

PORT = 50000
TICK_RATE = 30
WORLD_W, WORLD_H = 2600, 1900
TANK_RADIUS = 18
WALLS = [
    (300, 270, 360, 55), (600, 480, 55, 380),
    (870, 220, 420, 55), (1150, 560, 60, 390),
    (1490, 210, 55, 460), (1770, 570, 390, 55),
    (350, 1120, 420, 55), (850, 1400, 55, 330),
    (1200, 1150, 420, 55), (1800, 1150, 55, 410),
    (2080, 340, 55, 420), (2030, 1580, 300, 55),
]
SPAWNS = [(170, 170), (2430, 1730), (2400, 170), (170, 1730),
          (1300, 170), (1300, 1730), (170, 960), (2430, 960)]
COLORS = [(70, 200, 120), (235, 105, 90), (95, 170, 240), (238, 205, 90),
          (200, 125, 225), (80, 220, 215), (235, 150, 90), (165, 190, 100)]


def clamp(x, low, high):
    return max(low, min(high, x))


def overlaps_wall(x, y, radius):
    for wx, wy, ww, wh in WALLS:
        px = clamp(x, wx, wx + ww)
        py = clamp(y, wy, wy + wh)
        if (x - px) ** 2 + (y - py) ** 2 < radius ** 2:
            return True
    return False


def segment_hits_wall(x0, y0, x1, y1):
    """Simple swept projectile wall test to prevent tunneling."""
    distance = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(math.ceil(distance / 8)))
    for step in range(1, steps + 1):
        t = step / steps
        if overlaps_wall(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 3):
            return True
    return False
