"""Deterministic battlefield detail and client-only combat particle effects."""
import math
import random

import pygame

from shared import WORLD_H, WORLD_W

_rng = random.Random(7319)
DETAILS = [(_rng.randrange(WORLD_W), _rng.randrange(WORLD_H),
            _rng.randrange(2, 7), _rng.randrange(3))
           for _ in range(1750)]


def draw_details(surface, camera, width, height):
    """Small procedural grass, stones and shrubs in world coordinates."""
    ox, oy = camera
    for wx, wy, size, kind in DETAILS:
        sx, sy = int(wx - ox), int(wy - oy)
        if sx < -12 or sy < 52 or sx >= width + 12 or sy >= height + 12:
            continue
        if kind == 0:
            pygame.draw.line(surface, (70, 111, 72),
                             (sx - size, sy + size), (sx, sy - size), 1)
            pygame.draw.line(surface, (80, 119, 78),
                             (sx, sy + size), (sx + size, sy - size), 1)
        elif kind == 1:
            pygame.draw.circle(surface, (88, 112, 86), (sx, sy), size // 2)
        else:
            pygame.draw.circle(surface, (40, 94, 58), (sx + 2, sy + 2), size)
            pygame.draw.circle(surface, (57, 117, 67), (sx, sy), size)


class Effects:
    def __init__(self):
        self.particles = []
        self.rings = []
        self.rng = random.Random()

    def burst(self, kind, x, y, angle=0):
        palette = {
            "fire": [(255, 228, 124), (255, 154, 67), (240, 238, 180)],
            "impact": [(222, 193, 114), (154, 153, 134), (91, 93, 79)],
            "hit": [(255, 220, 123), (245, 112, 60), (144, 139, 125)],
            "destroy": [(255, 191, 86), (245, 99, 53), (91, 92, 86)],
        }.get(kind, [(250, 200, 130)])
        count = {"fire": 10, "impact": 14, "hit": 20, "destroy": 60}.get(kind, 12)
        for _ in range(count):
            theta = angle + self.rng.uniform(-0.9, 0.9) if kind == "fire" else self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(55, 175 if kind != "destroy" else 270)
            life = self.rng.uniform(0.16, 0.4 if kind == "fire" else 0.75)
            self.particles.append([x, y, math.cos(theta) * speed,
                                   math.sin(theta) * speed, life, life,
                                   self.rng.choice(palette), self.rng.randint(2, 6)])
        if kind in ("hit", "destroy", "impact"):
            self.rings.append([x, y, 0.0, 0.45 if kind == "destroy" else 0.22,
                               95 if kind == "destroy" else 40])
        self.particles = self.particles[-600:]

    def dust(self, x, y):
        life = self.rng.uniform(0.2, 0.55)
        self.particles.append([x, y, self.rng.uniform(-18, 18),
                               self.rng.uniform(-18, 18), life, life,
                               (117, 128, 102), self.rng.randint(2, 5)])

    def update(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= max(0.0, 1.0 - 2.2 * dt)
            p[3] *= max(0.0, 1.0 - 2.2 * dt)
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for ring in self.rings:
            ring[2] += dt
        self.rings = [ring for ring in self.rings if ring[2] < ring[3]]

    def draw(self, surface, camera):
        ox, oy = camera
        for p in self.particles:
            ratio = max(0, p[4] / p[5])
            x, y = int(p[0] - ox), int(p[1] - oy)
            if -20 <= x <= surface.get_width() + 20 and -20 <= y <= surface.get_height() + 20:
                pygame.draw.circle(surface, tuple(int(c * ratio + 35 * (1 - ratio)) for c in p[6]),
                                   (x, y), max(1, int(p[7] * ratio)))
        for x, y, age, lifetime, max_radius in self.rings:
            ratio = age / lifetime
            pygame.draw.circle(surface, (240, 189, 112),
                               (int(x - ox), int(y - oy)),
                               max(1, int(max_radius * ratio)), max(1, int(3 * (1 - ratio))))


def draw_minimap(surface, players, local_id, camera, width, height):
    """Small high-contrast radar showing map bounds and player locations."""
    scale = 0.10
    ww, hh = int(WORLD_W * scale), int(WORLD_H * scale)
    left, top = width - ww - 18, 72
    panel = pygame.Rect(left - 5, top - 5, ww + 10, hh + 10)
    pygame.draw.rect(surface, (18, 37, 33), panel)
    pygame.draw.rect(surface, (133, 155, 126), panel, 2)
    # Camera viewport in world overview.
    view = pygame.Rect(left + int(camera[0] * scale),
                       top + int(camera[1] * scale),
                       int(width * scale), int(height * scale))
    pygame.draw.rect(surface, (92, 117, 106), view, 1)
    for p in players:
        if p.get("dead"):
            continue
        px = left + int(p["x"] * scale)
        py = top + int(p["y"] * scale)
        pygame.draw.circle(surface, (245, 237, 170) if p["id"] == local_id
                           else tuple(p["color"]), (px, py), 4 if p["id"] == local_id else 3)
