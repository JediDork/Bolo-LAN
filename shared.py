"""Shared protocol and deterministic world constants."""
import math

PORT = 50000
TICK_RATE = 30
WORLD_W, WORLD_H = 2600, 1900
TANK_RADIUS = 18
GRID_SIZE = 50
WALL_MAX_HP = 4
# All static construction footprints start on the 50-unit tile grid.
# Each wall section occupies exactly one 50x50 tile.
WALLS = [
    (300, 250, 350, 50), (600, 500, 50, 350),
    (850, 200, 450, 50), (1150, 550, 50, 400),
    (1500, 200, 50, 450), (1750, 550, 400, 50),
    (350, 1100, 400, 50), (850, 1400, 50, 350),
    (1200, 1150, 400, 50), (1800, 1150, 50, 400),
    (2100, 350, 50, 400), (2050, 1600, 300, 50),
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
        assert all(value % GRID_SIZE == 0 for value in (x, y, w, h))
        if w > h:
            sections.extend((x + offset, y, GRID_SIZE, GRID_SIZE)
                            for offset in range(0, w, GRID_SIZE))
        else:
            sections.extend((x, y + offset, GRID_SIZE, GRID_SIZE)
                            for offset in range(0, h, GRID_SIZE))
    return tuple(sections)


def grid_center(tile):
    """Centre coordinate of a grid-aligned tile (for turrets, bases, etc)."""
    return tile * GRID_SIZE + GRID_SIZE // 2


def world_to_tile(x, y):
    return int(x // GRID_SIZE), int(y // GRID_SIZE)


def tile_to_world(tile_x, tile_y):
    return grid_center(tile_x), grid_center(tile_y)


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
