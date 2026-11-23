"""Shared protocol and deterministic world constants."""
import math
import random

PORT = 50000
TICK_RATE = 30
WORLD_W, WORLD_H = 2600, 1900
TANK_RADIUS = 18
WALL_MAX_HP = 4
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

# Wall runs are partitioned into individually destructible sections.
# IDs are deterministic across clients and the authoritative server.
def make_wall_sections():
    sections = []
    for x, y, w, h in WALLS:
        if w >= h:
            count = math.ceil(w / 55)
            for i in range(count):
                start = round(w * i / count)
                end = round(w * (i + 1) / count)
                sections.append((x + start, y, end - start, h))
        else:
            count = math.ceil(h / 55)
            for i in range(count):
                start = round(h * i / count)
                end = round(h * (i + 1) / count)
                sections.append((x, y + start, w, end - start))
    return tuple(sections)


WALL_SECTIONS = make_wall_sections()


def clamp(x, low, high):
    return max(low, min(high, x))


def wall_at(x, y, radius, hp=None):
    """Return the first surviving wall section ID intersecting a circle."""
    for index, (wx, wy, ww, wh) in enumerate(WALL_SECTIONS):
        if hp is not None and hp[index] <= 0:
            continue
        px = clamp(x, wx, wx + ww)
        py = clamp(y, wy, wy + wh)
        if (x - px) ** 2 + (y - py) ** 2 < radius ** 2:
            return index
    return None


def overlaps_wall(x, y, radius, hp=None):
    return wall_at(x, y, radius, hp) is not None


def segment_hits_wall(x0, y0, x1, y1, hp=None):
    """Return the first section hit by a swept projectile, or None."""
    distance = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(math.ceil(distance / 5)))
    for step in range(1, steps + 1):
        t = step / steps
        section = wall_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 3, hp)
        if section is not None:
            return section
    return None
