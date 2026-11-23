"""Offline smoke tests for high-detail rendering and generated sounds."""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from audio import SAMPLE_RATE, _synth
from engine_audio import engine_loop, engine_mix, ENGINE_RATES
from effects import Effects
from renderer import RENDER_H, RENDER_W, draw_frame, draw_road_network, point, ground, tank
from shared import WALL_MAX_HP, WALL_SECTIONS, WORLD_W


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

    def test_roads_have_continuous_interiors_not_repeating_semicircles(self):
        # Reproduces the straight-road pattern shown in the gameplay image.
        tiles = {(0, 0), (1, 0), (2, 0), (3, 0)}
        surface = pygame.Surface((450, 140))
        surface.fill((45, 82, 61))
        draw_road_network(surface, tiles, lambda x, y: (round(x * 2), round(y * 2)))
        roadbed = (139, 122, 94)
        # Every adjoining grid boundary should be continuous road fill;
        # the old circle-per-tile renderer put dark semicircle seams here.
        for x in (100, 200, 300):
            self.assertEqual(tuple(surface.get_at((x, 50))[:3]), roadbed)
        for x in (50, 150, 250, 350):
            self.assertEqual(tuple(surface.get_at((x, 50))[:3]), roadbed)
        self.assertNotEqual(tuple(surface.get_at((200, 0))[:3]), roadbed)

    def test_built_roads_render_in_frame(self):
        self.surface.fill((0, 0, 0))
        draw_frame(self.surface, (0, 0), [0] * len(WALL_SECTIONS),
                   [], [], None, Effects(), self.fonts,
                   "localhost", 50000, True, "",
                   built_roads=((6, 5), (7, 5), (8, 5)))

    def test_player_roads_join_over_world_seam(self):
        from terrain import GRID_W
        surface = pygame.Surface((500, 140))
        surface.fill((45, 82, 61))
        tiles = {(GRID_W - 1, 0), (0, 0)}
        camera = (WORLD_W - 100, 0)
        draw_road_network(surface, tiles, lambda x, y: point(x, y, camera))
        # World longitude 5200 should be fully covered by a continuous
        # roadbed, not two disconnected rounded terminal caps.
        self.assertEqual(tuple(surface.get_at((200, 50))[:3]),
                         (139, 122, 94))

    def test_camera_displays_both_sides_of_wrapped_planet(self):
        camera = (WORLD_W - 220, 300)
        west, _ = point(45, 400, camera)
        east, _ = point(WORLD_W - 45, 400, camera)
        self.assertGreater(west, east)
        self.assertEqual(west - east, 90 * 2)
        ground(self.surface, camera, [0] * len(WALL_SECTIONS))
        # The terrain extends through the seam, with no black empty band.
        for sx in (50, 350, 650, 1250):
            self.assertNotEqual(tuple(self.surface.get_at((sx, 400))[:3]),
                                (0, 0, 0))

    def test_new_supply_and_flag_sounds_are_valid_distinct_buffers(self):
        cues = ("material_added", "material_full", "ammo_added",
                "ammo_full", "flag_taken", "flag_lost")
        buffers = [_synth(kind) for kind in cues]
        self.assertEqual(len(set(buffers)), 6)
        for cue, sound in zip(cues, buffers):
            with self.subTest(cue=cue):
                self.assertGreater(len(sound), SAMPLE_RATE // 10)
                self.assertEqual(len(sound) % 2, 0)
                self.assertTrue(any(sound))

    def test_local_tank_ring_indicates_ready_vs_reloading(self):
        player = {"id": 1, "name": "T", "x": 150.0, "y": 150.0,
                  "a": 0.0, "t": 0.0, "hp": 100, "dead": False,
                  "color": (77, 151, 112), "speed": 0.0,
                  "reload_duration": 1.25, "reload": 1.25}
        field = pygame.Surface((450, 450))
        field.fill((48, 80, 64))
        tank(field, player, (0, 0), self.fonts["label"], 1)
        ring_edge = (238, 300)
        reloading = tuple(field.get_at(ring_edge)[:3])
        player["reload"] = 0.0
        field.fill((48, 80, 64))
        tank(field, player, (0, 0), self.fonts["label"], 1)
        ready = tuple(field.get_at(ring_edge)[:3])
        self.assertNotEqual(reloading, ready)
        self.assertEqual(ready, (107, 226, 131))

    def test_reload_sound_is_a_valid_mono_buffer(self):
        raw = _synth("reload")
        self.assertEqual(len(raw), int(SAMPLE_RATE * 0.25) * 2)
        self.assertTrue(any(raw))

    def test_engine_layers_are_complete_loop_buffers(self):
        for hz in ENGINE_RATES:
            with self.subTest(hz=hz):
                raw = engine_loop(hz)
                self.assertEqual(len(raw), SAMPLE_RATE * 2)
                # The periodic waveform has no audible click at loop boundary.
                from array import array
                samples = array("h")
                samples.frombytes(raw)
                self.assertLess(abs(samples[0] - samples[-1]), 5000)

    def test_engine_stays_low_and_transitions_without_a_raised_whine(self):
        self.assertLessEqual(max(ENGINE_RATES), 25)
        idle = engine_mix(0, 0)
        cruising = engine_mix(65, 1)
        fast = engine_mix(125, 1)
        self.assertGreater(idle[0], 0)
        self.assertGreater(cruising[1], idle[1])
        self.assertGreater(fast[2], idle[2])
        for volumes in (idle, cruising, fast):
            self.assertTrue(all(0 <= volume <= 0.31 for volume in volumes))

    def test_audio_buffers_have_mono_16_bit_samples(self):
        for kind, length in (("fire", 0.19), ("impact", 0.14),
                             ("hit", 0.24), ("destroy", 0.75),
                             ("wall_break", 0.52)):
            with self.subTest(kind=kind):
                data = _synth(kind)
                self.assertEqual(len(data), int(SAMPLE_RATE * length) * 2)


if __name__ == "__main__":
    unittest.main()
