"""High-resolution renderer with a constant competitive world viewport.

World units and camera bounds are fixed at 1200 x 760 for all players.
Only raster detail is supersampled; high-resolution monitors gain no vision.
"""
import math

import pygame

from effects import DETAILS
from shared import GRID_SIZE, WALL_MAX_HP, WALL_SECTIONS, WORLD_H, WORLD_W
from terrain import (FOREST_TILES, LAKE_TILES, RIVER_TILES, ROAD_TILES, BRIDGE_TILES,
                     GRID_W, GRID_H, neighbors, terrain_at)

WORLD_VIEW_W, WORLD_VIEW_H = 1200, 760
SCALE = 2
RENDER_W, RENDER_H = WORLD_VIEW_W * SCALE, WORLD_VIEW_H * SCALE
BG = (45, 82, 61)


def point(wx, wy, camera):
    return round((wx - camera[0]) * SCALE), round((wy - camera[1]) * SCALE)


def dot(surface, color, x, y, radius):
    pygame.draw.circle(surface, color, (round(x), round(y)), max(1, round(radius)))


_TERRAIN_CACHE = None


def make_terrain_cache():
    """Paint the whole deterministic map once; scrolling then costs one blit.

    Irregular foliage and water are formed from overlapping rounded cells,
    not visible axis-aligned area rectangles. The tile mask remains canonical
    for terrain movement and the future bridge builder.
    """
    result = pygame.Surface((WORLD_W * SCALE, WORLD_H * SCALE))
    result.fill(BG)
    size = GRID_SIZE * SCALE

    # Stable ground variation at grid-cell granularity.
    for ty in range(GRID_H):
        for tx in range(GRID_W):
            x, y = tx * size, ty * size
            if (tx * 19 + ty * 31) % 9 < 3:
                pygame.draw.rect(result, (47, 85, 63), (x, y, size, size))

    # Forests have soft, lobed perimeters defined by many overlapping crowns.
    # The game logic uses tile occupancy, not the visible foliage silhouette.
    for tx, ty in sorted(FOREST_TILES):
        x, y = (tx * GRID_SIZE + GRID_SIZE / 2) * SCALE, (ty * GRID_SIZE + GRID_SIZE / 2) * SCALE
        colour = (39, 88, 54) if (tx + ty) % 3 else (43, 94, 57)
        pygame.draw.circle(result, (28, 69, 42), (round(x), round(y)), 37 * SCALE)
        pygame.draw.circle(result, colour, (round(x), round(y)), 32 * SCALE)
        if (tx * 7 + ty * 11) % 4:
            pygame.draw.circle(result, (24, 63, 39), (round(x + 9 * SCALE), round(y + 9 * SCALE)), 18 * SCALE)
            pygame.draw.circle(result, (58, 119, 68), (round(x - 5 * SCALE), round(y - 7 * SCALE)), 14 * SCALE)
            pygame.draw.circle(result, (82, 137, 80), (round(x - 10 * SCALE), round(y - 12 * SCALE)), 5 * SCALE)

    # Routes form continuous tracks between bases, bending to avoid lakes and
    # wall tiles. Rounded shoulders help intersections look less block-like.
    for tx, ty in sorted(ROAD_TILES):
        x, y = (tx * GRID_SIZE + GRID_SIZE / 2) * SCALE, (ty * GRID_SIZE + GRID_SIZE / 2) * SCALE
        pygame.draw.circle(result, (95, 83, 66), (round(x), round(y)), 27 * SCALE)
        pygame.draw.circle(result, (139, 122, 94), (round(x), round(y)), 22 * SCALE)
        for nx, ny in neighbors((tx, ty)):
            if (nx, ny) in ROAD_TILES:
                mid_x = round((x + (nx * GRID_SIZE + GRID_SIZE / 2) * SCALE) / 2)
                mid_y = round((y + (ny * GRID_SIZE + GRID_SIZE / 2) * SCALE) / 2)
                dx = abs(nx - tx)
                # Road joins use actual rectangles, but their outer shoulders
                # are circular so bends read like graded tracks, not squares.
                rect = pygame.Rect(
                    round(mid_x - (25 if dx else 22) * SCALE),
                    round(mid_y - (22 if dx else 25) * SCALE),
                    (50 if dx else 44) * SCALE,
                    (44 if dx else 50) * SCALE)
                pygame.draw.rect(result, (139, 122, 94), rect)

    # The river flows beneath raised bridge decking at crossings.
    for mask, deep, rim, radius in (
        (RIVER_TILES, (38, 103, 137), (76, 153, 171), 37),
        (LAKE_TILES, (29, 85, 127), (70, 149, 175), 39),
    ):
        for tx, ty in sorted(mask):
            px = (tx * GRID_SIZE + GRID_SIZE / 2) * SCALE
            py = (ty * GRID_SIZE + GRID_SIZE / 2) * SCALE
            center = (round(px), round(py))
            pygame.draw.circle(result, (75, 106, 95), center, (radius + 4) * SCALE)
            pygame.draw.circle(result, rim, center, radius * SCALE)
            pygame.draw.circle(result, deep, center, (radius - 5) * SCALE)
            if (tx * 13 + ty * 3) % 4 == 0:
                pygame.draw.arc(result, (106, 180, 188),
                                pygame.Rect(round(px - 19 * SCALE), round(py - 6 * SCALE),
                                            38 * SCALE, 16 * SCALE), 0.3, 2.7, 2)

    # Prebuilt bridges occupy the road/river intersection cells. These are
    # fast crossings; unbridged river tiles remain very slow for tanks.
    for tx, ty in sorted(BRIDGE_TILES):
        x = tx * GRID_SIZE * SCALE
        y = ty * GRID_SIZE * SCALE
        deck = pygame.Rect(x, y + 9 * SCALE,
                           GRID_SIZE * SCALE, 32 * SCALE)
        pygame.draw.rect(result, (62, 53, 44), deck.inflate(0, 12 * SCALE), border_radius=5)
        pygame.draw.rect(result, (155, 126, 88), deck, border_radius=4)
        for plank in range(5, GRID_SIZE, 9):
            line_x = x + plank * SCALE
            pygame.draw.line(result, (106, 83, 61),
                             (line_x, deck.top + 3), (line_x, deck.bottom - 3), 2)
        pygame.draw.line(result, (215, 187, 124),
                         (deck.left, deck.top), (deck.right, deck.top), 4)
        pygame.draw.line(result, (215, 187, 124),
                         (deck.left, deck.bottom), (deck.right, deck.bottom), 4)

    # Scatter only on uncovered grass. Tree foliage and water keep their own
    # detail, preventing dots on the banks that look like grid artefacts.
    for wx, wy, radius, kind in DETAILS:
        if terrain_at(wx, wy) != "grass":
            continue
        px, py = round(wx * SCALE), round(wy * SCALE)
        radius *= SCALE
        if kind == 0:
            pygame.draw.aaline(result, (70, 111, 72),
                               (px - radius, py + radius), (px, py - radius))
            pygame.draw.aaline(result, (80, 119, 78),
                               (px, py + radius), (px + radius, py - radius))
        elif kind == 1:
            dot(result, (91, 110, 85), px, py, radius / 2)
        else:
            dot(result, (43, 98, 60), px, py, radius)

    # Keep the construction grid available but subtle; natural silhouettes
    # should remain visible instead of being chopped into strong squares.
    grid_colour = (57, 91, 75)
    for x in range(0, WORLD_W * SCALE + 1, size):
        pygame.draw.line(result, grid_colour, (x, 0), (x, WORLD_H * SCALE), 1)
    for y in range(0, WORLD_H * SCALE + 1, size):
        pygame.draw.line(result, grid_colour, (0, y), (WORLD_W * SCALE, y), 1)
    return result


def ground(surface, camera, wall_hp):
    global _TERRAIN_CACHE
    if _TERRAIN_CACHE is None:
        _TERRAIN_CACHE = make_terrain_cache()
    surface.blit(_TERRAIN_CACHE,
                 (-round(camera[0] * SCALE), -round(camera[1] * SCALE)))
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
    x, y = point(0, 0, camera)
    pygame.draw.rect(surface, (199, 208, 168),
                     pygame.Rect(x, y, WORLD_W * SCALE, WORLD_H * SCALE), 7)


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


def minimap(surface, players, local_id, camera, bases=(), pillboxes=()):
    radar_scale = 0.10 * SCALE
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
    rect = pygame.Rect(left + round(camera[0] * radar_scale),
                       top + round(camera[1] * radar_scale),
                       round(WORLD_VIEW_W * radar_scale),
                       round(WORLD_VIEW_H * radar_scale))
    pygame.draw.rect(surface, (92, 117, 106), rect, 2)
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
               fonts, host, port, connected, status, bases=(), pillboxes=()):
    ground(surface, camera, wall_hp)
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
        pygame.draw.circle(surface, (139, 102, 77), (x, y), 22 * SCALE)
        pygame.draw.circle(surface, (64, 65, 58), (x, y), 14 * SCALE)
        pygame.draw.line(surface, (234, 132, 81), (x, y), (x + 21 * SCALE, y), 8)
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
    minimap(surface, players, local_id, camera, bases, pillboxes)

    panel = pygame.Surface((1430, 144), pygame.SRCALPHA)
    panel.fill((16, 30, 29, 208))
    surface.blit(panel, (16, RENDER_H - 162))
    surface.blit(fonts["heading"].render(
        "BOLO-LAN  /  BRIDGE TEST v0.10", True, (235, 233, 208)),
        (40, RENDER_H - 150))
    surface.blit(fonts["label"].render(
        f"HOST {host}:{port} | PLAYERS {len(players)} | WASD DRIVE | MOUSE AIM | CLICK FIRE | M MUTE",
        True, (191, 208, 195)), (40, RENDER_H - 92))
    local = next((p for p in players if p["id"] == local_id), None)
    if local:
        surface.blit(fonts["label"].render(
            f"ARMOUR {int(local['hp']):3d}%  AMMO {local.get('ammo', 24):2d}/24  "
            f"SPEED {abs(local.get('speed', 0)):.0f}  TERRAIN {terrain_at(local['x'], local['y']).upper()}  "
            f"KILLS {local['score']}",
            True, (252, 245, 205)), (40, RENDER_H - 50))
    if not connected:
        text = fonts["heading"].render(status, True, (255, 203, 110))
        surface.blit(text, ((RENDER_W - text.get_width()) // 2, RENDER_H // 2))
