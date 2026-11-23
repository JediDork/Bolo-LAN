"""Offline smoke tests for high-detail rendering and generated sounds."""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from audio import SAMPLE_RATE, _synth
from effects import Effects
from renderer import RENDER_H, RENDER_W, draw_frame
from shared import WALL_MAX_HP, WALL_SECTIONS


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()
        cls.surface = pygame.Surface((RENDER_W, RENDER_H))
        cls.fonts = {
            "label": pygame.font.SysFont("consolas", 32, bold=True),
            "heading": pygame.font.SysFont("consolas", 46, bold=True)
        }

    @classmethod
    def tearDownClass(cls):
        pygame.font.quit()
        pygame.display.quit()

    def test_high_resolution_uses_identical_world_view(self):
        self.assertEqual((RENDER_W, RENDER_H), (2400, 1520))
        self.assertEqual((RENDER_W / 2, RENDER_H / 2), (1200, 760))

    def test_draw_combat_scene(self):
        player = {"id": 1, "name": "Tester", "hp": 100, "score": 0,
                  "dead": False, "color": (70, 200, 120),
                  "x": 210, "y": 220, "a": 0.0, "t": 1.2}
        effects = Effects()
        effects.burst("fire", 230, 220, 0.0)
        draw_frame(self.surface, (0.0, 0.0),
                   [WALL_MAX_HP] * len(WALL_SECTIONS),
                   [{"x": 265, "y": 220}], [player], 1, effects,
                   self.fonts, "127.0.0.1", 50000, True, "")
        self.assertEqual(self.surface.get_size(), (2400, 1520))

    def test_terrain_and_structures_render_without_error(self):
        p = {"id": 1, "name": "Tester", "hp": 72.5, "ammo": 12,
             "speed": 95.0, "score": 0, "dead": False,
             "color": (70, 200, 120), "x": 180.0, "y": 335.0,
             "a": 1.0, "t": 1.5}
        bases = [{"id": 0, "x": 180.0, "y": 335.0,
                  "owner": 0, "capturing": 1, "progress": 1.5}]
        pillboxes = [{"id": 0, "x": 770.0, "y": 1050.0, "hp": 75}]
        draw_frame(self.surface, (0.0, 0.0),
                   [WALL_MAX_HP] * len(WALL_SECTIONS),
                   [], [p], 1, Effects(), self.fonts,
                   "localhost", 50000, True, "", bases, pillboxes)

    def test_audio_buffers_have_mono_16_bit_samples(self):
        for kind, length in (("fire", 0.19), ("impact", 0.14),
                             ("hit", 0.24), ("destroy", 0.75),
                             ("wall_break", 0.52)):
            with self.subTest(kind=kind):
                data = _synth(kind)
                self.assertEqual(len(data), int(SAMPLE_RATE * length) * 2)


if __name__ == "__main__":
    unittest.main()
