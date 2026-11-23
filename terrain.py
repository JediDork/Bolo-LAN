"""Deterministic tile-world with organic forests/lakes and routed roads.

The 50-unit GRID is the canonical collision/building coordinate system.
Natural terrain is a *connected mask of grid cells* with irregular outlines,
rather than the old four-sided rectangular zones. All clients and the host
derive exactly the same layout from this module, without network transfers.
"""
import heapq
import math

from shared import GRID_SIZE, WALL_SECTIONS, WORLD_H, WORLD_W, tile_to_world

GRID_W = WORLD_W // GRID_SIZE
GRID_H = WORLD_H // GRID_SIZE
BASE_TILES = ((3, 6), (48, 29), (46, 5), (4, 31), (19, 8), (32, 30))
PILLBOX_TILES = ((15, 21), (33, 19), (27, 14), (21, 25))
BASE_SITES = tuple(tile_to_world(*tile) for tile in BASE_TILES)
PILLBOX_SITES = tuple(tile_to_world(*tile) for tile in PILLBOX_TILES)

# Centre / average elliptical radii. Multi-frequency boundary variation
# creates bays, spurs and woodland fingers instead of rectangles.
FOREST_PATCHES = (
    (555, 715, 220, 140, 1.4),
    (1725, 345, 210, 135, 2.2),
    (545, 1500, 195, 150, 3.7),
    (2040, 1375, 205, 160, 5.0),
    (1000, 455, 170, 115, 3.1),
)
LAKE_PATCHES = (
    (1135, 973, 220, 100, 2.5),
    (2280, 1000, 165, 125, 0.6),
    (250, 825, 150, 95, 4.0),
)

# The river is exactly ONE construction tile wide per row.
# It meanders gradually (at most one cell sideways between rows).
def river_center(y):
    return (1260 + 220 * math.sin((y - 310) / 345.0)
            + 85 * math.sin(y / 127.0))


def river_tiles():
    tiles = set()
    last_x = None
    for ty in range(6, 32):
        desired_x = round((river_center(ty * GRID_SIZE + GRID_SIZE / 2)
                           - GRID_SIZE / 2) / GRID_SIZE)
        if last_x is not None:
            desired_x = max(last_x - 1, min(last_x + 1, desired_x))
        tiles.add((desired_x, ty))
        last_x = desired_x
    return tiles


def inside_blob(x, y, patch):
    cx, cy, rx, ry, phase = patch
    dx = x - cx
    dy = y - cy
    angle = math.atan2(dy / ry, dx / rx)
    ripple = (1.0 + 0.17 * math.sin(3 * angle + phase)
              + 0.115 * math.sin(5 * angle - phase * 1.7)
              + 0.07 * math.sin(9 * angle + phase * 2.8))
    distance = math.hypot(dx / rx, dy / ry)
    return distance <= ripple


def make_masks():
    forests, lakes = set(), set()
    river = river_tiles()
    for ty in range(GRID_H):
        for tx in range(GRID_W):
            x, y = tile_to_world(tx, ty)
            tile = (tx, ty)
            if any(inside_blob(x, y, patch) for patch in LAKE_PATCHES):
                lakes.add(tile)
                continue
            if tile in river:
                continue
            if any(inside_blob(x, y, patch) for patch in FOREST_PATCHES):
                forests.add(tile)
    # Fixed river path never overlaps lakes: lakes remain separate obstacles.
    river.difference_update(lakes)
    # Areas around bases must remain playable and clearly visible.
    for bx, by in BASE_TILES:
        for tx in range(bx - 1, bx + 2):
            for ty in range(by - 1, by + 2):
                forests.discard((tx, ty))
    return frozenset(forests), frozenset(lakes), frozenset(river)


FOREST_TILES, LAKE_TILES, RIVER_TILES = make_masks()
WALL_TILES = frozenset((x // GRID_SIZE, y // GRID_SIZE)
                       for x, y, _, _ in WALL_SECTIONS)


def neighbors(tile):
    x, y = tile
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
            yield nx, ny


def route_to(start, goal, existing):
    """A* grid roads from flag to flag, reusing established routes.

    The pathfinder can cross one-cell rivers; road crossings become bridges.
    """
    frontier = [(0.0, 0, start)]
    cost = {start: 0.0}
    previous = {}
    serial = 0
    while frontier:
        _, _, tile = heapq.heappop(frontier)
        if tile == goal:
            path = [tile]
            while path[-1] != start:
                path.append(previous[path[-1]])
            path.reverse()
            return path
        for nxt in neighbors(tile):
            if nxt in LAKE_TILES or nxt in WALL_TILES:
                continue
            weight = (2.3 if nxt in RIVER_TILES else
                      2.6 if nxt in FOREST_TILES else
                      0.35 if nxt in existing else 1.0)
            tentative = cost[tile] + weight
            if tentative < cost.get(nxt, float("inf")):
                cost[nxt] = tentative
                previous[nxt] = tile
                serial += 1
                distance = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
                heapq.heappush(frontier, (tentative + distance * 0.35, serial, nxt))
    raise ValueError(f"No road route from {start} to {goal}")


def choose_crossing(target_row):
    """Find a safe crossing with dry road approach on each bank."""
    for ty in sorted(range(6, 32), key=lambda row: abs(row - target_row)):
        tile = next((cell for cell in RIVER_TILES if cell[1] == ty), None)
        if tile is None:
            continue
        tx, _ = tile
        # Avoid pillboxes, walls and lakes in the immediate bridge corridor.
        approach = {(x, ty) for x in range(tx - 2, tx + 3)}
        if not (approach & (WALL_TILES | LAKE_TILES)) and all(
                0 <= x < GRID_W for x, _ in approach):
            return tile
    raise ValueError("No safe bridge corridor")


def make_roads():
    # Route flags on both banks through two explicit strategic crossings,
    # and preserve connectivity at every river intersection.
    bridges = (choose_crossing(12), choose_crossing(25))
    routes = set(BASE_TILES)
    anchor = BASE_TILES[0]
    for crossing in bridges:
        cx, cy = crossing
        # Physically connect roadbed both sides of the river.
        routes.update({(cx - 1, cy), crossing, (cx + 1, cy)})
        for approach in ((cx - 2, cy), (cx + 2, cy)):
            routes.update(route_to(approach, anchor, routes))
        anchor = (cx + 1, cy)
    for site in BASE_TILES:
        routes.update(route_to(site, anchor, routes))
    # Every road crossing a river is a working bridge, not a slow ford.
    return frozenset(routes), frozenset(routes & RIVER_TILES)


ROAD_TILES, BRIDGE_TILES = make_roads()

# Compatibility aliases for older code that imports these names. These are
# now grid tiles rather than rectangular bounds.
FORESTS = FOREST_TILES
WATER = LAKE_TILES
RIVERS = RIVER_TILES
ROADS = ROAD_TILES


def tile_at(x, y):
    return int(x // GRID_SIZE), int(y // GRID_SIZE)


def water_at(x, y, radius=0):
    """Lake collision tests against impassable lake tiles only."""
    cx, cy = tile_at(x, y)
    reach = max(0, math.ceil(radius / GRID_SIZE) + 1)
    for ty in range(cy - reach, cy + reach + 1):
        for tx in range(cx - reach, cx + reach + 1):
            if (tx, ty) not in LAKE_TILES:
                continue
            wx, wy = tx * GRID_SIZE, ty * GRID_SIZE
            px = max(wx, min(wx + GRID_SIZE, x))
            py = max(wy, min(wy + GRID_SIZE, y))
            if radius == 0:
                if wx <= x < wx + GRID_SIZE and wy <= y < wy + GRID_SIZE:
                    return True
            elif (x - px) ** 2 + (y - py) ** 2 < radius ** 2:
                return True
    return False


def terrain_at(x, y):
    tile = tile_at(x, y)
    if tile in LAKE_TILES:
        return "water"
    if tile in BRIDGE_TILES:
        return "bridge"
    if tile in RIVER_TILES:
        return "river"
    if tile in ROAD_TILES:
        return "road"
    if tile in FOREST_TILES:
        return "forest"
    return "grass"


TERRAIN_SPEED = {
    "grass": 1.0, "road": 1.20, "forest": 0.65,
    "river": 0.18, "bridge": 1.20, "water": 0.0,
}

# Existing static walls crossing woodland are retired (including those
# touching tree-canopy neighbours), leaving forest boundaries undisturbed.
# Clients and server derive the same wall HP array from the same map.
def initial_wall_hp():
    hp = []
    for x, y, _, _ in WALL_SECTIONS:
        tx, ty = x // GRID_SIZE, y // GRID_SIZE
        forest_nearby = any((tx + dx, ty + dy) in FOREST_TILES
                            for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        hp.append(0 if forest_nearby or (tx, ty) in LAKE_TILES else 4)
    return hp
