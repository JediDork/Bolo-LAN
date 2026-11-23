"""Shared building rules for the first playable Bolo-LAN base builder.

All construction is anchored to a 50x50 map tile. Server validates range,
resources, terrain, occupancy and cooldown; clients only send intent.
"""
import math
from shared import GRID_SIZE, WORLD_H, WORLD_W, tile_to_world
from terrain import (BASE_TILES, PILLBOX_TILES, FOREST_TILES,
                     LAKE_TILES, RIVER_TILES, BRIDGE_TILES)

BUILD_RANGE = 175
BUILD_COOLDOWN = 0.30
START_MATERIAL = 18
MAX_MATERIAL = 30
MATERIAL_REFILL = 1.2
WALL_COST = 2
BRIDGE_COST = 5
PILLBOX_COST = 8
REPAIR_COST = 1
BUILD_COSTS = {"wall": WALL_COST, "bridge": BRIDGE_COST,
               "pillbox": PILLBOX_COST, "repair": REPAIR_COST,
               "remove": 0}
BUILD_LABELS = {"wall": "WALL", "bridge": "BRIDGE", "pillbox": "PILLBOX",
                "repair": "REPAIR", "remove": "REMOVE"}
BUILD_TOOLS = {"1": "wall", "2": "bridge", "3": "pillbox",
               "4": "repair", "5": "remove"}


def valid_tile(tx, ty):
    return (isinstance(tx, int) and not isinstance(tx, bool)
            and isinstance(ty, int) and not isinstance(ty, bool)
            and 0 <= tx < WORLD_W // GRID_SIZE
            and 0 <= ty < WORLD_H // GRID_SIZE)


def in_build_range(player, tx, ty):
    x, y = tile_to_world(tx, ty)
    return math.hypot(player["x"] - x, player["y"] - y) <= BUILD_RANGE


def blocked_build_terrain(tile, kind):
    if kind == "bridge":
        return tile not in RIVER_TILES or tile in BRIDGE_TILES
    if kind in ("wall", "pillbox"):
        return tile in (FOREST_TILES | LAKE_TILES | RIVER_TILES)
    return False


def near_flag(tile):
    return tile in BASE_TILES


def nearby_forest(tile):
    tx, ty = tile
    return any((tx + dx, ty + dy) in FOREST_TILES
               for dx in (-1, 0, 1) for dy in (-1, 0, 1))
