"""High-resolution renderer with a constant competitive world viewport.

World units and camera bounds are fixed at 1200 x 760 for all players.
Only raster detail is supersampled; high-resolution monitors gain no vision.
"""
import math

import pygame

from effects import DETAILS
from shared import WALL_MAX_HP, WALL_SECTIONS, WORLD_H, WORLD_W

WORLD_VIEW_W, WORLD_VIEW_H = 1200, 760
SCALE = 2
RENDER_W, RENDER_H = WORLD_VIEW_W * SCALE, WORLD_VIEW_H * SCALE
BG = (45, 82, 61)


def point(wx, wy, camera):
    return round((wx - camera[0]) * SCALE), round((wy - camera[1]) * SCALE)


def dot(surface, color, x, y, radius):
    pygame.draw.circle(surface, color, (round(x), round(y)), max(1, round(radius)))


def ground(surface, camera, wall_hp):
    surface.fill(BG)
    sx, sy = camera
    for wx in range(int(sx // 100) * 100, int(sx + WORLD_VIEW_W) + 101, 100):
        x, _ = point(wx, 0, camera)
        pygame.draw.line(surface, (51, 91, 67), (x, 0), (x, RENDER_H), 1)
    for wy in range(int(sy // 100) * 100, int(sy + WORLD_VIEW_H) + 101, 100):
        _, y = point(0, wy, camera)
        pygame.draw.line(surface, (51, 91, 67), (0, y), (RENDER_W, y), 1)

    for wx, wy, size, kind in DETAILS:
        px, py = point(wx, wy, camera)
        if not (-22 <= px <= RENDER_W + 22 and -22 <= py <= RENDER_H + 22):
            continue
        size *= SCALE
        if kind == 0:
            pygame.draw.aaline(surface, (70, 111, 72),
                               (px - size, py + size), (px, py - size))
            pygame.draw.aaline(surface, (80, 119, 78),
                               (px, py + size), (px + size, py - size))
        elif kind == 1:
            dot(surface, (88, 112, 86), px, py, size / 2)
        else:
            dot(surface, (40, 94, 58), px + 4, py + 4, size)
            dot(surface, (57, 117, 67), px, py, size)

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
    bounds = pygame.Rect(x, y, WORLD_W * SCALE, WORLD_H * SCALE)
    pygame.draw.rect(surface, (199, 208, 168), bounds, 7)


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
    for side in (-1, 1):
        pygame.draw.line(surface, (22, 36, 31),
                         hull_point(-17, side * 13),
                         hull_point(17, side * 13), 12)
        for forward in (-14, -7, 0, 7, 14):
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
    label = font.render(f'{player["name"]}  {player["hp"]}%', True, (242, 242, 229))
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


def minimap(surface, players, local_id, camera):
    radar_scale = 0.10 * SCALE
    ww, hh = round(WORLD_W * radar_scale), round(WORLD_H * radar_scale)
    left, top = RENDER_W - ww - 36, 144
    panel = pygame.Rect(left - 10, top - 10, ww + 20, hh + 20)
    pygame.draw.rect(surface, (18, 37, 33), panel)
    pygame.draw.rect(surface, (133, 155, 126), panel, 4)
    rect = pygame.Rect(left + round(camera[0] * radar_scale),
                       top + round(camera[1] * radar_scale),
                       round(WORLD_VIEW_W * radar_scale),
                       round(WORLD_VIEW_H * radar_scale))
    pygame.draw.rect(surface, (92, 117, 106), rect, 2)
    for p in players:
        if not p.get("dead"):
            color = (245, 237, 170) if p["id"] == local_id else tuple(p["color"])
            dot(surface, color, left + p["x"] * radar_scale,
                top + p["y"] * radar_scale, 8 if p["id"] == local_id else 6)


def draw_frame(surface, camera, wall_hp, bullets, players, local_id, effects,
               fonts, host, port, connected, status):
    ground(surface, camera, wall_hp)
    for shell in bullets:
        x, y = point(shell["x"], shell["y"], camera)
        dot(surface, (255, 170, 68), x, y, 12)
        dot(surface, (255, 235, 164), x, y, 6)
    for p in players:
        tank(surface, p, camera, fonts["label"], local_id)
    particles(surface, camera, effects)
    minimap(surface, players, local_id, camera)

    panel = pygame.Surface((1430, 144), pygame.SRCALPHA)
    panel.fill((16, 30, 29, 208))
    surface.blit(panel, (16, RENDER_H - 162))
    surface.blit(fonts["heading"].render(
        "BOLO-LAN  /  FIELD TEST v0.5", True, (235, 233, 208)),
        (40, RENDER_H - 150))
    surface.blit(fonts["label"].render(
        f"HOST {host}:{port} | PLAYERS {len(players)} | WASD DRIVE | MOUSE AIM | CLICK FIRE | M MUTE",
        True, (191, 208, 195)), (40, RENDER_H - 92))
    local = next((p for p in players if p["id"] == local_id), None)
    if local:
        surface.blit(fonts["label"].render(
            f"ARMOUR {local['hp']:3d}%     KILLS {local['score']}",
            True, (252, 245, 205)), (40, RENDER_H - 50))
    if not connected:
        text = fonts["heading"].render(status, True, (255, 203, 110))
        surface.blit(text, ((RENDER_W - text.get_width()) // 2, RENDER_H // 2))
