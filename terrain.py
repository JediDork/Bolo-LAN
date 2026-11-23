"""Deterministic large world: natural terrain, edge-fed rivers and routed roads.

All gameplay obstacles use the shared 50-unit grid. The visual shoreline
follows smooth analytic boundaries, but gameplay is always deterministic.
"""
import heapq
import math

from shared import GRID_SIZE, WALL_SECTIONS, WORLD_H, WORLD_W, tile_to_world

GRID_W = WORLD_W // GRID_SIZE
GRID_H = WORLD_H // GRID_SIZE

# Six bases per quadrant: 24 flags across four strategic sectors.
_LOCAL_BASE_TILES = ((3, 6), (48, 29), (46, 5),
                     (4, 31), (19, 8), (32, 30))
_LOCAL_PILLBOX_TILES = ((15, 21), (33, 19), (27, 14), (21, 25))
SECTOR_X, SECTOR_Y = GRID_W // 2, GRID_H // 2
BASE_TILES = tuple((x + ox, y + oy)
                   for ox in (0, SECTOR_X) for oy in (0, SECTOR_Y)
                   for x, y in _LOCAL_BASE_TILES)
PILLBOX_TILES = tuple((x + ox, y + oy)
                      for ox in (0, SECTOR_X) for oy in (0, SECTOR_Y)
                      for x, y in _LOCAL_PILLBOX_TILES)
BASE_SITES = tuple(tile_to_world(*tile) for tile in BASE_TILES)
PILLBOX_SITES = tuple(tile_to_world(*tile) for tile in PILLBOX_TILES)

_LOCAL_FORESTS = (
    (555, 715, 220, 140, 1.4),
    (1725, 345, 210, 135, 2.2),
    (545, 1500, 195, 150, 3.7),
    (2040, 1375, 205, 160, 5.0),
    (1000, 455, 170, 115, 3.1),
)
_LOCAL_LAKES = (
    (1135, 973, 220, 100, 2.5),
    (2280, 1000, 165, 125, 0.6),
    (250, 825, 150, 95, 4.0),
)
FOREST_PATCHES = tuple((x + ox, y + oy, rx, ry, phase + ox / 1000)
                       for ox in (0, WORLD_W // 2)
                       for oy in (0, WORLD_H // 2)
                       for x, y, rx, ry, phase in _LOCAL_FORESTS)
LAKE_PATCHES = (
    tuple((x + ox, y + oy, rx, ry, phase + oy / 900)
          for ox in (0, WORLD_W // 2)
          for oy in (0, WORLD_H // 2)
          for x, y, rx, ry, phase in _LOCAL_LAKES)
    + ((2600, 1860, 335, 220, 1.65),  # Major inland lake / northern river mouth
       (1550, 2660, 310, 220, 3.4))  # Western lake / western river mouth
)


def blob_radius(angle, phase):
    return (1.0 + 0.17 * math.sin(3 * angle + phase)
            + 0.115 * math.sin(5 * angle - phase * 1.7)
            + 0.07 * math.sin(9 * angle + phase * 2.8))


def inside_blob(x, y, patch):
    cx, cy, rx, ry, phase = patch
    dx, dy = x - cx, y - cy
    angle = math.atan2(dy / ry, dx / rx)
    return math.hypot(dx / rx, dy / ry) <= blob_radius(angle, phase)


def lake_outline(patch, samples=96):
    """Smooth closed shoreline in world coordinates (not a circle per tile)."""
    cx, cy, rx, ry, phase = patch
    result = []
    for i in range(samples):
        angle = math.tau * i / samples
        radius = blob_radius(angle, phase)
        result.append((cx + math.cos(angle) * rx * radius,
                       cy + math.sin(angle) * ry * radius))
    return tuple(result)


def terrain_masks():
    forest, lakes = set(), set()
    for patch in FOREST_PATCHES:
        cx, cy, rx, ry, _ = patch
        for ty in range(max(0, int((cy - ry * 1.5) // GRID_SIZE)),
                        min(GRID_H, math.ceil((cy + ry * 1.5) / GRID_SIZE))):
            for tx in range(max(0, int((cx - rx * 1.5) // GRID_SIZE)),
                            min(GRID_W, math.ceil((cx + rx * 1.5) / GRID_SIZE))):
                if inside_blob(*tile_to_world(tx, ty), patch):
                    forest.add((tx, ty))
    for patch in LAKE_PATCHES:
        cx, cy, rx, ry, _ = patch
        for ty in range(max(0, int((cy - ry * 1.5) // GRID_SIZE)),
                        min(GRID_H, math.ceil((cy + ry * 1.5) / GRID_SIZE))):
            for tx in range(max(0, int((cx - rx * 1.5) // GRID_SIZE)),
                            min(GRID_W, math.ceil((cx + rx * 1.5) / GRID_SIZE))):
                if inside_blob(*tile_to_world(tx, ty), patch):
                    lakes.add((tx, ty))
    forest.difference_update(lakes)
    for bx, by in BASE_TILES:
        for tx in range(bx - 1, bx + 2):
            for ty in range(by - 1, by + 2):
                forest.discard((tx, ty))
    return frozenset(forest), frozenset(lakes)


FOREST_TILES, LAKE_TILES = terrain_masks()


def edge_river(source, destination, axis):
    """One-cell-wide four-connected path from world edge into a lake.

    axis='y' steps down from north, axis='x' steps right from west.
    Sideways adjustment is bounded to one tile per primary step.
    """
    sx, sy = source
    gx, gy = destination
    primary_start = sy if axis == "y" else sx
    primary_goal = gy if axis == "y" else gx
    cross_start = sx if axis == "y" else sy
    cross_goal = gx if axis == "y" else gy
    cross = cross_start
    path = []
    for primary in range(primary_start, primary_goal + 1):
        progress = (primary - primary_start) / max(1, primary_goal - primary_start)
        sway = 3 * math.sin(math.pi * progress) * math.sin(4.5 * math.pi * progress)
        desired = round(cross_start + (cross_goal - cross_start) * progress + sway)
        cross += max(-1, min(1, desired - cross))
        tile = (cross, primary) if axis == "y" else (primary, cross)
        if tile in LAKE_TILES:
            # At the mouth, a diagonal landing still needs a dry-to-water
            # elbow; otherwise the last river tile only touches lake corner.
            if path and abs(tile[0] - path[-1][0]) + abs(tile[1] - path[-1][1]) == 2:
                elbow = (tile[0], path[-1][1]) if axis == "y" else (path[-1][0], tile[1])
                if elbow not in LAKE_TILES:
                    path.append(elbow)
            break
        # Diagonal steps need a corner square so the narrow watercourse stays
        # four-connected for tanks, bridges and the underlying grid.
        if path and abs(tile[0] - path[-1][0]) + abs(tile[1] - path[-1][1]) == 2:
            elbow = (tile[0], path[-1][1]) if axis == "y" else (path[-1][0], tile[1])
            if elbow not in LAKE_TILES:
                path.append(elbow)
        path.append(tile)
    else:
        # A river must never end in nowhere. Routes are chosen to intersect a
        # destination lake and tests guard against accidental layout edits.
        raise ValueError("Edge-fed river failed to reach a lake")
    if not path:
        raise ValueError("River must contain passable water before its lake")
    return tuple(path)


# North edge to central lake, west edge to western lake. Both are navigable
# only at river speed except where roads create existing bridges.
RIVER_PATHS = (
    edge_river((52, 0), (52, 37), "y"),
    edge_river((0, 64), (31, 53), "x"),
)
RIVER_TILES = frozenset(tile for path in RIVER_PATHS for tile in path)
# Rivers cut through forest, but do not alter the lake collision footprint.
FOREST_TILES = frozenset(FOREST_TILES - RIVER_TILES)
WALL_TILES = frozenset((x // GRID_SIZE, y // GRID_SIZE)
                       for x, y, _, _ in WALL_SECTIONS)
ACTIVE_WALL_TILES = frozenset(
    (tx, ty) for tx, ty in WALL_TILES
    if (tx, ty) not in LAKE_TILES and not any(
        (tx + dx, ty + dy) in FOREST_TILES
        for dx in (-1, 0, 1) for dy in (-1, 0, 1))
)


def neighbors(tile):
    x, y = tile
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
            yield nx, ny


def route_to(start, goal, existing):
    """A* shortest useful road to base, weighted for terrain and reuse."""
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
            return tuple(reversed(path))
        for nxt in neighbors(tile):
            if nxt in LAKE_TILES or nxt in ACTIVE_WALL_TILES:
                continue
            weight = (2.8 if nxt in RIVER_TILES else
                      2.2 if nxt in FOREST_TILES else
                      0.35 if nxt in existing else 1.0)
            next_cost = cost[tile] + weight
            if next_cost < cost.get(nxt, float("inf")):
                cost[nxt] = next_cost
                previous[nxt] = tile
                serial += 1
                distance = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
                heapq.heappush(frontier, (next_cost + 0.35 * distance, serial, nxt))
    raise ValueError(f"No road route from {start} to {goal}")


def make_roads():
    roads = set(BASE_TILES)
    # First establish crossing links across both rivers so road bridges are
    # useful strategic objectives even on a large map.
    crossing_targets = [(52, 22), (20, 53)]
    for ideal in crossing_targets:
        crossing = min(RIVER_TILES,
                       key=lambda p: abs(p[0] - ideal[0]) + abs(p[1] - ideal[1]))
        cx, cy = crossing
        # Add approaches on both sides of the narrow water.
        if crossing in RIVER_PATHS[0]:
            approach = [(cx - 2, cy), (cx + 2, cy)]
        else:
            approach = [(cx, cy - 2), (cx, cy + 2)]
        roads.add(crossing)
        for bank in approach:
            roads.update(route_to(bank, BASE_TILES[0], roads))
    # Connect every flag to the existing road spine.
    for site in BASE_TILES[1:]:
        roads.update(route_to(site, BASE_TILES[0], roads))
    roads.update(BASE_TILES)
    return frozenset(roads), frozenset(roads & RIVER_TILES)


ROAD_TILES, BRIDGE_TILES = make_roads()
FORESTS = FOREST_TILES
WATER = LAKE_TILES
RIVERS = RIVER_TILES
ROADS = ROAD_TILES


def tile_at(x, y):
    return int(x // GRID_SIZE), int(y // GRID_SIZE)


def water_at(x, y, radius=0):
    """Deep lake tiles block tanks; narrow rivers remain fordable."""
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


TERRAIN_SPEED = {"grass": 1.0, "road": 1.20, "forest": 0.65,
                 "river": 0.18, "bridge": 1.20, "water": 0.0}


def initial_wall_hp():
    """Retire prebuilt walls intersecting tree canopy or lakes."""
    return [0 if (x // GRID_SIZE, y // GRID_SIZE) not in ACTIVE_WALL_TILES
            else 4 for x, y, _, _ in WALL_SECTIONS]
