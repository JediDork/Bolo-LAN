"""High-resolution renderer with a constant competitive world viewport.

World units and camera bounds are fixed at 1200 x 760 for all players.
Only raster detail is supersampled; high-resolution monitors gain no vision.
"""
import math
from collections import OrderedDict

import pygame

from effects import DETAILS
from shared import GRID_SIZE, WALL_MAX_HP, WALL_SECTIONS, WORLD_H, WORLD_W, nearest_x
from construction import BUILD_COSTS, BUILD_LABELS, BUILD_RANGE
from terrain import (FOREST_TILES, LAKE_TILES, RIVER_TILES, ROAD_TILES, BRIDGE_TILES,
                     GRID_W, GRID_H, neighbors, terrain_at, LAKE_PATCHES,
                     lake_outline, RIVER_PATHS)

WORLD_VIEW_W, WORLD_VIEW_H = 1200, 760
SCALE = 2
RENDER_W, RENDER_H = WORLD_VIEW_W * SCALE, WORLD_VIEW_H * SCALE
BG = (45, 82, 61)


def point(wx, wy, camera):
    # Choose the closest copy of the planet to this camera viewpoint.
    visible_x = nearest_x(wx, camera[0] + WORLD_VIEW_W / 2)
    return round((visible_x - camera[0]) * SCALE), round((wy - camera[1]) * SCALE)


def dot(surface, color, x, y, radius):
    pygame.draw.circle(surface, color, (round(x), round(y)), max(1, round(radius)))


# Large worlds are drawn into small lazy chunks rather than one enormous
# full-map surface. Cache stays bounded even with 4x the previous map area.
CHUNK_WORLD = 500
CHUNK_PAD = 80
MAX_CHUNKS = 20
_TERRAIN_CHUNKS = OrderedDict()


def draw_road_network(surface, road_tiles, to_screen, visible_tiles=None):
    """Paint continuous road lanes with caps ONLY at true dead ends.

    No circle is stamped onto every road cell. Drawing ALL border pieces
    before ALL roadbed pieces eliminates the internal semicircular seams
    that appeared when overlapping disk tiles were drawn individually.
    """
    if visible_tiles is None:
        visible_tiles = road_tiles
    visible_tiles = sorted(visible_tiles)
    for colour, width in (((95, 83, 66), 54),
                          ((139, 122, 94), 44)):
        thick = round(width * SCALE)
        for tx, ty in visible_tiles:
            x, y = to_screen((tx + 0.5) * GRID_SIZE,
                             (ty + 0.5) * GRID_SIZE)
            half = thick // 2
            pygame.draw.rect(surface, colour,
                             pygame.Rect(x - half, y - half, thick, thick))
            # Orthogonal edge joins form one uninterrupted road surface.
            for nx, ny in ((tx + 1, ty), (tx, ty + 1)):
                if (nx, ny) in road_tiles:
                    ex, ey = to_screen((nx + 0.5) * GRID_SIZE,
                                       (ny + 0.5) * GRID_SIZE)
                    if nx != tx:
                        pygame.draw.rect(surface, colour,
                                         (x, y - half, ex - x, thick))
                    else:
                        pygame.draw.rect(surface, colour,
                                         (x - half, y, thick, ey - y))
        # Only exposed terminal cells receive a round end.
        for tx, ty in visible_tiles:
            if sum((n in road_tiles) for n in neighbors((tx, ty))) <= 1:
                x, y = to_screen((tx + 0.5) * GRID_SIZE,
                                 (ty + 0.5) * GRID_SIZE)
                pygame.draw.circle(surface, colour, (x, y), thick // 2)


def make_terrain_chunk(cx, cy):
    """Draw the world region around one chunk at full 2x resolution.

    The padded border lets foliage/water overlap a chunk boundary seamlessly;
    only the unpadded centre is copied into the visible viewport.
    """
    start_x = cx * CHUNK_WORLD
    start_y = cy * CHUNK_WORLD
    side = (CHUNK_WORLD + 2 * CHUNK_PAD) * SCALE
    layer = pygame.Surface((side, side))
    layer.fill(BG)
    lo_x = start_x - CHUNK_PAD
    lo_y = start_y - CHUNK_PAD
    hi_x = start_x + CHUNK_WORLD + CHUNK_PAD
    hi_y = start_y + CHUNK_WORLD + CHUNK_PAD

    def local(wx, wy):
        return round((wx - lo_x) * SCALE), round((wy - lo_y) * SCALE)

    min_tx = max(0, int(lo_x // GRID_SIZE) - 1)
    min_ty = max(0, int(lo_y // GRID_SIZE) - 1)
    max_tx = min(GRID_W, int(hi_x // GRID_SIZE) + 2)
    max_ty = min(GRID_H, int(hi_y // GRID_SIZE) + 2)
    area = [(tx, ty) for ty in range(min_ty, max_ty)
            for tx in range(min_tx, max_tx)]

    for tx, ty in area:
        if (tx * 19 + ty * 31) % 9 < 3:
            px, py = local(tx * GRID_SIZE, ty * GRID_SIZE)
            pygame.draw.rect(layer, (47, 85, 63),
                             (px, py, GRID_SIZE * SCALE, GRID_SIZE * SCALE))

    # Dense woodland edges are irregular, but its terrain mask stays on grid.
    for tx, ty in area:
        if (tx, ty) not in FOREST_TILES:
            continue
        x, y = local((tx + 0.5) * GRID_SIZE, (ty + 0.5) * GRID_SIZE)
        colour = (39, 88, 54) if (tx + ty) % 3 else (43, 94, 57)
        pygame.draw.circle(layer, (28, 69, 42), (x, y), 37 * SCALE)
        pygame.draw.circle(layer, colour, (x, y), 32 * SCALE)
        if (tx * 7 + ty * 11) % 4:
            pygame.draw.circle(layer, (24, 63, 39),
                               (x + 9 * SCALE, y + 9 * SCALE), 18 * SCALE)
            pygame.draw.circle(layer, (58, 119, 68),
                               (x - 5 * SCALE, y - 7 * SCALE), 14 * SCALE)
            pygame.draw.circle(layer, (82, 137, 80),
                               (x - 10 * SCALE, y - 12 * SCALE), 5 * SCALE)

    # Two-pass continuous road drawing; no tiled semicircle artifacts.
    road_cells = [tile for tile in area if tile in ROAD_TILES]
    draw_road_network(layer, ROAD_TILES, local, road_cells)

    # Each river runs continuously from the outer map boundary into its lake.
    # No circle-by-circle lake artwork: lakes are ONE filled shoreline polygon.
    for path in RIVER_PATHS:
        points = [local((tx + 0.5) * GRID_SIZE, (ty + 0.5) * GRID_SIZE)
                  for tx, ty in path]
        for colour, width in (((74, 117, 120), 56),
                              ((73, 150, 170), 50),
                              ((38, 103, 137), 44)):
            if len(points) > 1:
                pygame.draw.lines(layer, colour, False, points, width * SCALE)
            for x, y in points:
                if 0 <= x <= side and 0 <= y <= side:
                    pygame.draw.circle(layer, colour, (x, y), width * SCALE // 2)

    # Analytic lake polygons create coherent irregular coastlines and broad
    # continuous water surfaces, not a disconnected chain of circles.
    for patch in LAKE_PATCHES:
        px, py, rx, ry, _ = patch
        if not (lo_x - rx * 1.5 <= px <= hi_x + rx * 1.5 and
                lo_y - ry * 1.5 <= py <= hi_y + ry * 1.5):
            continue
        vertices = [local(wx, wy) for wx, wy in lake_outline(patch)]
        pygame.draw.polygon(layer, (70, 143, 160), vertices)
        pygame.draw.polygon(layer, (34, 94, 132), vertices)
        pygame.draw.lines(layer, (87, 155, 168), True, vertices, 11 * SCALE)
        pygame.draw.lines(layer, (54, 116, 151), True, vertices, 5 * SCALE)

    for tx, ty in area:
        if (tx, ty) not in LAKE_TILES or (tx * 17 + ty * 3) % 5:
            continue
        x, y = local((tx + 0.5) * GRID_SIZE, (ty + 0.5) * GRID_SIZE)
        pygame.draw.arc(layer, (101, 178, 192),
                        pygame.Rect(x - 22, y - 9, 44, 19), 0.3, 2.7, 2)

    # Raised bridges go on top of the flowing river.
    for tx, ty in area:
        if (tx, ty) not in BRIDGE_TILES:
            continue
        x, y = local(tx * GRID_SIZE, ty * GRID_SIZE)
        vertical = ((tx, ty - 1) in ROAD_TILES and
                    (tx, ty + 1) in ROAD_TILES and
                    not ((tx - 1, ty) in ROAD_TILES and (tx + 1, ty) in ROAD_TILES))
        if vertical:
            deck = pygame.Rect(x + 9 * SCALE, y, 32 * SCALE, 50 * SCALE)
        else:
            deck = pygame.Rect(x, y + 9 * SCALE, 50 * SCALE, 32 * SCALE)
        pygame.draw.rect(layer, (61, 52, 42), deck.inflate(12 * SCALE, 12 * SCALE))
        pygame.draw.rect(layer, (155, 126, 88), deck)
        for plank in range(5, 50, 9):
            if vertical:
                pygame.draw.line(layer, (103, 80, 62),
                                 (deck.left + 3, y + plank * SCALE),
                                 (deck.right - 3, y + plank * SCALE), 2)
            else:
                pygame.draw.line(layer, (103, 80, 62),
                                 (x + plank * SCALE, deck.top + 3),
                                 (x + plank * SCALE, deck.bottom - 3), 2)

    for wx, wy, radius, kind in DETAILS:
        if not (lo_x <= wx <= hi_x and lo_y <= wy <= hi_y):
            continue
        if terrain_at(wx, wy) != "grass":
            continue
        x, y = local(wx, wy)
        size = radius * SCALE
        if kind == 0:
            pygame.draw.aaline(layer, (70, 111, 72),
                               (x - size, y + size), (x, y - size))
        elif kind == 1:
            dot(layer, (91, 110, 85), x, y, size / 2)
        else:
            dot(layer, (43, 98, 60), x, y, size)

    # Subtle build grid overlay, drawn after all terrain.
    start_tile_x = max(0, int(lo_x // GRID_SIZE))
    end_tile_x = min(GRID_W, int(hi_x // GRID_SIZE) + 1)
    start_tile_y = max(0, int(lo_y // GRID_SIZE))
    end_tile_y = min(GRID_H, int(hi_y // GRID_SIZE) + 1)
    for tx in range(start_tile_x, end_tile_x + 1):
        x, _ = local(tx * GRID_SIZE, 0)
        pygame.draw.line(layer, (57, 91, 75), (x, 0), (x, side), 1)
    for ty in range(start_tile_y, end_tile_y + 1):
        _, y = local(0, ty * GRID_SIZE)
        pygame.draw.line(layer, (57, 91, 75), (0, y), (side, y), 1)
    return layer


def ground(surface, camera, wall_hp, built_roads=()):
    surface.fill(BG)
    # Draw canonical world chunks under each visible longitude copy. The
    # final world chunk is only 200 units wide; the next copy of chunk zero
    # starts immediately at WORLD_W, without a blank strip or a hard border.
    chunk_columns = math.ceil(WORLD_W / CHUNK_WORLD)
    for cy in range(max(0, int(camera[1] // CHUNK_WORLD)),
                    min(math.ceil(WORLD_H / CHUNK_WORLD),
                        math.ceil((camera[1] + WORLD_VIEW_H) / CHUNK_WORLD) + 1)):
        for copy in (-1, 0, 1):
            for cx in range(chunk_columns):
                wx = cx * CHUNK_WORLD + copy * WORLD_W
                chunk_width = min(CHUNK_WORLD, WORLD_W - cx * CHUNK_WORLD)
                if wx + chunk_width <= camera[0] or wx >= camera[0] + WORLD_VIEW_W:
                    continue
                key = cx, cy
                chunk = _TERRAIN_CHUNKS.get(key)
                if chunk is None:
                    chunk = make_terrain_chunk(cx, cy)
                    _TERRAIN_CHUNKS[key] = chunk
                    if len(_TERRAIN_CHUNKS) > MAX_CHUNKS:
                        _TERRAIN_CHUNKS.popitem(last=False)
                else:
                    _TERRAIN_CHUNKS.move_to_end(key)
                dx = round((wx - camera[0]) * SCALE)
                dy = round((cy * CHUNK_WORLD - camera[1]) * SCALE)
                crop = pygame.Rect(CHUNK_PAD * SCALE, CHUNK_PAD * SCALE,
                                   chunk_width * SCALE, CHUNK_WORLD * SCALE)
                surface.blit(chunk, (dx, dy), crop)
    # User-built road sections appear instantly, using the same uninterrupted
    # geometry as the baked tracks. Redraw their immediate join neighbourhood
    # so road ends turn into smooth junctions rather than overlapping circles.
    if built_roads:
        dynamic = {tuple(tile) for tile in built_roads}
        connected = ROAD_TILES | dynamic
        touched = dynamic | {n for tile in dynamic for n in neighbors(tile)
                             if n in connected}
        draw_road_network(surface, connected,
                          lambda x, y: point(x, y, camera), touched)
    # Wall damage remains dynamic and never gets baked into terrain.
    tones = ((121, 127, 112), (109, 110, 100),
             (91, 88, 82), (72, 66, 62))
    for index, (wx, wy, ww, wh) in enumerate(WALL_SECTIONS):
        hp = wall_hp[index] if index < len(wall_hp) else WALL_MAX_HP
        if hp <= 0:
            continue
        x, y = point(wx, wy, camera)
        rect = pygame.Rect(x, y, round(ww * SCALE), round(wh * SCALE))
        if not rect.colliderect(surface.get_rect()):
            continue
        damage = WALL_MAX_HP - hp
        pygame.draw.rect(surface, (38, 45, 41), rect)
        pygame.draw.rect(surface, tones[damage], rect.inflate(-10, -10))
        pygame.draw.rect(surface, (38, 47, 42), rect, 4)
        if damage:
            cx0, cy0 = rect.center
            for crack in range(damage * 3):
                ox = ((index * 17 + crack * 19) % 31 - 15) * SCALE
                oy = ((index * 13 + crack * 23) % 27 - 13) * SCALE
                cx = max(rect.left + 8, min(rect.right - 8, cx0 + ox))
                cy = max(rect.top + 8, min(rect.bottom - 8, cy0 + oy))
                dx = (10 if crack % 2 else -11) * SCALE
                dy = (8 if crack % 3 else -9) * SCALE
                ex = max(rect.left + 8, min(rect.right - 8, cx + dx))
                ey = max(rect.top + 8, min(rect.bottom - 8, cy + dy))
                pygame.draw.line(surface, (42, 44, 43), (cx, cy),
                                 (ex, ey), max(1, (damage // 2 + 1) * SCALE))
            pygame.draw.ellipse(surface, (52, 51, 48),
                                pygame.Rect(cx0 - 6 * damage, cy0 - 6 * damage,
                                            12 * damage, 12 * damage))
    # No eastern/western borders: these longitude edges are joined.
    for pole_y in (0, WORLD_H):
        _, sy = point(0, pole_y, camera)
        pygame.draw.line(surface, (199, 208, 168), (0, sy),
                         (RENDER_W, sy), 7)


def tank(surface, player, camera, font, local_id):
    if player.get("dead"):
        return
    x, y = point(player["x"], player["y"], camera)
    color = tuple(player["color"])
    hull = player["a"]
    turret = player["t"]
    ca, sa = math.cos(hull), math.sin(hull)

    def hull_point(forward, sideways):
        return (round(x + SCALE * (ca * forward - sa * sideways)),
                round(y + SCALE * (sa * forward + ca * sideways)))

    pygame.draw.ellipse(surface, (24, 42, 33),
                        pygame.Rect(x - 46, y - 24, 96, 68))
    outline = [hull_point(f, s) for f, s in
               ((24, -15), (24, 15), (-22, 15), (-22, -15))]
    pygame.draw.polygon(surface, color, outline)
    pygame.draw.polygon(surface, (20, 32, 31), outline, 4)
    # Tread cleats advance with reported vehicle speed, including reverse.
    travel = player.get("speed", 0.0)
    track_phase = ((pygame.time.get_ticks() / 1000.0) * travel * 0.13) % 7.0
    for side in (-1, 1):
        pygame.draw.line(surface, (22, 36, 31),
                         hull_point(-17, side * 13),
                         hull_point(17, side * 13), 12)
        for slot in range(-4, 5):
            forward = slot * 7 + track_phase
            if -17 <= forward <= 17:
                dot(surface, (95, 102, 86), *hull_point(forward, side * 13), 4)
    barrel = (round(x + math.cos(turret) * 34 * SCALE),
              round(y + math.sin(turret) * 34 * SCALE))
    pygame.draw.line(surface, (23, 34, 32), (x, y), barrel, 22)
    pygame.draw.line(surface, (165, 176, 153), (x, y), barrel, 12)
    dot(surface, (23, 34, 32), x, y, 26)
    dot(surface, color, x, y, 20)
    arrow = [hull_point(f, s) for f, s in
             ((25, 0), (9, -10), (13, 0), (9, 10))]
    pygame.draw.polygon(surface, (255, 227, 91), arrow)
    pygame.draw.polygon(surface, (35, 36, 24), arrow, 3)
    if player["id"] == local_id:
        pygame.draw.circle(surface, (246, 244, 174), (x, y), 60, 4)
    if player.get("god_mode"):
        # Gold shield ring communicates invulnerability to all LAN players.
        pygame.draw.circle(surface, (255, 222, 90), (x, y), 38 * SCALE, 4)
    label = font.render(f'{player["name"]}  {int(player["hp"])}%', True, (242, 242, 229))
    surface.blit(label, (x - label.get_width() // 2, y - 90))


def particles(surface, camera, effects):
    ox, oy = camera
    for p in effects.particles:
        ratio = max(0, p[4] / p[5])
        x, y = point(p[0], p[1], camera)
        if -40 <= x <= RENDER_W + 40 and -40 <= y <= RENDER_H + 40:
            color = tuple(int(c * ratio + 35 * (1 - ratio)) for c in p[6])
            dot(surface, color, x, y, max(1, round(p[7] * SCALE * ratio)))
    for x, y, age, lifetime, radius in effects.rings:
        px, py = point(x, y, camera)
        ratio = age / lifetime
        pygame.draw.circle(surface, (240, 189, 112), (px, py),
                           max(1, round(SCALE * radius * ratio)),
                           max(1, round(SCALE * 3 * (1 - ratio))))


def minimap(surface, players, local_id, camera, bases=(), pillboxes=(),
            built_walls=(), built_bridges=(), built_roads=()):
    radar_scale = min(410 / WORLD_W, 285 / WORLD_H)
    ww, hh = round(WORLD_W * radar_scale), round(WORLD_H * radar_scale)
    left, top = RENDER_W - ww - 36, 144
    panel = pygame.Rect(left - 10, top - 10, ww + 20, hh + 20)
    pygame.draw.rect(surface, (18, 37, 33), panel)
    # Radar uses the same tile masks: the river/forest/roads are visible
    # before players commit to a crossing or a base assault.
    for mask, color in ((FOREST_TILES, (43, 87, 51)),
                        (ROAD_TILES, (127, 113, 88)),
                        (RIVER_TILES, (54, 118, 146)),
                        (LAKE_TILES, (38, 93, 139)),
                        (BRIDGE_TILES, (211, 182, 125))):
        for tx, ty in mask:
            pygame.draw.rect(surface, color,
                             (round(left + tx * GRID_SIZE * radar_scale),
                              round(top + ty * GRID_SIZE * radar_scale),
                              max(1, round(GRID_SIZE * radar_scale)),
                              max(1, round(GRID_SIZE * radar_scale))))
    pygame.draw.rect(surface, (133, 155, 126), panel, 4)
    # A seam-straddling camera draws two view rectangles on the overview.
    for copy in (0, -WORLD_W):
        rect = pygame.Rect(left + round((camera[0] + copy) * radar_scale),
                           top + round(camera[1] * radar_scale),
                           round(WORLD_VIEW_W * radar_scale),
                           round(WORLD_VIEW_H * radar_scale))
        clip_before = surface.get_clip()
        surface.set_clip(panel)
        pygame.draw.rect(surface, (92, 117, 106), rect, 2)
        surface.set_clip(clip_before)
    for tx, ty in built_roads:
        pygame.draw.rect(surface, (166, 138, 101),
                         (round(left + tx * GRID_SIZE * radar_scale),
                          round(top + ty * GRID_SIZE * radar_scale),
                          max(2, round(GRID_SIZE * radar_scale)),
                          max(2, round(GRID_SIZE * radar_scale))))
    for wall in built_walls:
        pygame.draw.rect(surface, (210, 176, 116),
                         (round(left + wall["tx"] * GRID_SIZE * radar_scale),
                          round(top + wall["ty"] * GRID_SIZE * radar_scale),
                          max(2, round(GRID_SIZE * radar_scale)),
                          max(2, round(GRID_SIZE * radar_scale))))
    for tx, ty in built_bridges:
        dot(surface, (235, 198, 109),
            left + (tx + 0.5) * GRID_SIZE * radar_scale,
            top + (ty + 0.5) * GRID_SIZE * radar_scale, 5)
    for b in bases:
        dot(surface, (208, 187, 95) if b["owner"] == 0 else (109, 232, 167),
            left + b["x"] * radar_scale, top + b["y"] * radar_scale, 7)
    for box in pillboxes:
        if box["hp"] > 0:
            dot(surface, (223, 107, 94),
                left + box["x"] * radar_scale, top + box["y"] * radar_scale, 5)
    for p in players:
        if not p.get("dead"):
            color = (245, 237, 170) if p["id"] == local_id else tuple(p["color"])
            dot(surface, color, left + p["x"] * radar_scale,
                top + p["y"] * radar_scale, 8 if p["id"] == local_id else 6)


def draw_frame(surface, camera, wall_hp, bullets, players, local_id, effects,
               fonts, host, port, connected, status, bases=(), pillboxes=(),
               built_walls=(), built_bridges=(), build_mode=False, build_part="wall",
               hovered_tile=None, build_message="", built_roads=()):
    ground(surface, camera, wall_hp, built_roads)
    # Dynamic structures are drawn above the static terrain.
    for tx, ty in built_bridges:
        x, y = point(tx * GRID_SIZE, ty * GRID_SIZE, camera)
        deck = pygame.Rect(x + 2, y + 13 * SCALE,
                           GRID_SIZE * SCALE - 4, 24 * SCALE)
        pygame.draw.rect(surface, (67, 57, 43), deck.inflate(0, 12 * SCALE), border_radius=4)
        pygame.draw.rect(surface, (172, 136, 91), deck, border_radius=4)
        for offset in range(6, GRID_SIZE, 10):
            px = x + offset * SCALE
            pygame.draw.line(surface, (99, 76, 55),
                             (px, deck.top + 2), (px, deck.bottom - 2), 3)
        pygame.draw.line(surface, (236, 198, 127),
                         (deck.left, deck.top), (deck.right, deck.top), 4)
        pygame.draw.line(surface, (236, 198, 127),
                         (deck.left, deck.bottom), (deck.right, deck.bottom), 4)
    for wall in built_walls:
        tx, ty, hp = wall["tx"], wall["ty"], wall["hp"]
        x, y = point(tx * GRID_SIZE, ty * GRID_SIZE, camera)
        rect = pygame.Rect(x, y, GRID_SIZE * SCALE, GRID_SIZE * SCALE)
        if not rect.colliderect(surface.get_rect()):
            continue
        base = ((128, 126, 108), (112, 107, 94),
                (91, 85, 80), (73, 66, 62))[max(0, min(3, 4 - hp))]
        pygame.draw.rect(surface, (30, 39, 37), rect)
        pygame.draw.rect(surface, base, rect.inflate(-10, -10))
        pygame.draw.rect(surface, (197, 175, 119), rect, 4)
        if hp < 4:
            pygame.draw.line(surface, (42, 42, 43), (x + 14, y + 10),
                             (x + 70, y + 82), 5)
    if build_mode and hovered_tile is not None:
        tx, ty = hovered_tile
        if 0 <= tx < WORLD_W // GRID_SIZE and 0 <= ty < WORLD_H // GRID_SIZE:
            x, y = point(tx * GRID_SIZE, ty * GRID_SIZE, camera)
            tile_rect = pygame.Rect(x, y, GRID_SIZE * SCALE, GRID_SIZE * SCALE)
            # Server decides placement validity. Amber preview means chosen
            # tile, not a promise that resources/terrain allow construction.
            overlay = pygame.Surface((tile_rect.w, tile_rect.h), pygame.SRCALPHA)
            overlay.fill((255, 218, 90, 74))
            surface.blit(overlay, tile_rect.topleft)
            pygame.draw.rect(surface, (255, 231, 118), tile_rect, 5)
            label = fonts["label"].render(BUILD_LABELS[build_part], True, (255, 241, 173))
            surface.blit(label, (x, y - 39))
    for base in bases:
        x, y = point(base["x"], base["y"], camera)
        owned = base["owner"] == local_id and local_id is not None
        color = (80, 195, 136) if owned else ((203, 115, 89) if base["owner"] else (206, 178, 84))
        # Open status ring: terrain remains visible beneath the base.
        pygame.draw.circle(surface, (21, 39, 36), (x, y), 49 * SCALE, 7)
        pygame.draw.circle(surface, color, (x, y), 47 * SCALE, 5)
        # Only the small square flag foundation is filled.
        flag_size = 34 * SCALE
        flag = pygame.Rect(x - flag_size // 2, y - flag_size // 2,
                           flag_size, flag_size)
        pygame.draw.rect(surface, (56, 60, 53), flag, border_radius=5)
        pygame.draw.rect(surface, color, flag, 4, border_radius=5)
        # Pole and pennant remain within the single flag tile.
        pygame.draw.line(surface, (26, 36, 33), (x + 2, y + 15 * SCALE),
                         (x + 2, y - 17 * SCALE), 4)
        pygame.draw.polygon(surface, color,
                            ((x + 4, y - 17 * SCALE),
                             (x + 23 * SCALE, y - 12 * SCALE),
                             (x + 4, y - 6 * SCALE)))
        if base.get("capturing"):
            progress = min(1.0, base.get("progress", 0) / 2.5)
            pygame.draw.arc(surface, (249, 231, 112),
                            pygame.Rect(x - 52 * SCALE, y - 52 * SCALE,
                                        104 * SCALE, 104 * SCALE),
                            -math.pi / 2, -math.pi / 2 + progress * math.tau, 8)
    for box in pillboxes:
        if box["hp"] <= 0:
            continue
        x, y = point(box["x"], box["y"], camera)
        pygame.draw.circle(surface, (23, 37, 36), (x, y), 29 * SCALE)
        body_color = ((78, 151, 118) if box.get("owner") == local_id
                      else (139, 102, 77))
        pygame.draw.circle(surface, body_color, (x, y), 22 * SCALE)
        # The barrel slews towards an enemy within detection distance,
        # long before the shorter firing range is reached.
        angle = box.get("angle", 0.0)
        muzzle = (round(x + math.cos(angle) * 34 * SCALE),
                  round(y + math.sin(angle) * 34 * SCALE))
        pygame.draw.line(surface, (24, 35, 35), (x, y), muzzle, 15)
        pygame.draw.line(surface, (173, 177, 158), (x, y), muzzle, 9)
        pygame.draw.circle(surface, (42, 46, 41), (x, y), 15 * SCALE)
        pygame.draw.circle(surface, body_color, (x, y), 11 * SCALE)
        if box.get("tracking"):
            pygame.draw.circle(surface, (244, 199, 95), (x, y),
                               30 * SCALE, 2)
        pygame.draw.rect(surface, (44, 43, 39),
                         (x - 27, y + 35, 54, 8))
        pygame.draw.rect(surface, (223, 114, 79),
                         (x - 27, y + 35, max(0, int(54 * box["hp"] / 100)), 8))
    for shell in bullets:
        x, y = point(shell["x"], shell["y"], camera)
        dot(surface, (255, 170, 68), x, y, 12)
        dot(surface, (255, 235, 164), x, y, 6)
    for p in players:
        tank(surface, p, camera, fonts["label"], local_id)
    particles(surface, camera, effects)
    minimap(surface, players, local_id, camera, bases, pillboxes,
            built_walls, built_bridges, built_roads)

    panel = pygame.Surface((1430, 144), pygame.SRCALPHA)
    panel.fill((16, 30, 29, 208))
    surface.blit(panel, (16, RENDER_H - 162))
    surface.blit(fonts["heading"].render(
        "BOLO-LAN  /  ROAD CONSTRUCTION v0.15", True, (235, 233, 208)),
        (40, RENDER_H - 150))
    surface.blit(fonts["label"].render(
        (f"BUILD MODE: 1 WALL  2 BRIDGE  3 PILLBOX  4 REPAIR  5 REMOVE  6 ROAD  |  CLICK PLACE  |  B EXIT"
         if build_mode else
         f"HOST {host}:{port} | PLAYERS {len(players)} | WASD | FIRE | B BUILD | G GOD | M MUTE"),
        True, (191, 208, 195)), (40, RENDER_H - 92))
    local = next((p for p in players if p["id"] == local_id), None)
    if local:
        surface.blit(fonts["label"].render(
            f"ARMOUR {int(local['hp']):3d}%  AMMO {local.get('ammo', 24):2d}/24  "
            f"SPEED {abs(local.get('speed', 0)):.0f}  TERRAIN {terrain_at(local['x'], local['y']).upper()}  "
            f"KILLS {local['score']}  "
            f"MATERIAL {local.get('material', 0):.0f}/30  "
            f"{'[GOD MODE ON]' if local.get('god_mode') else ''}",
            True, (252, 245, 205)), (40, RENDER_H - 50))
    if build_mode:
        chosen = f"{BUILD_LABELS[build_part]}  COST {BUILD_COSTS[build_part]}  RANGE {BUILD_RANGE}"
        tool = fonts["label"].render(chosen, True, (255, 232, 128))
        surface.blit(tool, (RENDER_W - tool.get_width() - 40, RENDER_H - 60))
    if build_message:
        msg = fonts["label"].render(build_message[:60], True, (255, 222, 122))
        surface.blit(msg, (40, RENDER_H - 213))

    if not connected:
        text = fonts["heading"].render(status, True, (255, 203, 110))
        surface.blit(text, ((RENDER_W - text.get_width()) // 2, RENDER_H // 2))
