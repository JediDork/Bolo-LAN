"""Headless smoke tests for the LAN gameplay server."""
import json
import socket
import unittest

from server import GameServer, TURRET_SPEED
from shared import WALL_SECTIONS, WALL_MAX_HP, wall_at, overlaps_wall
from display import viewport, to_logical


class GameServerTests(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(0)
        self.address1 = ("127.0.0.1", 51001)
        self.address2 = ("127.0.0.1", 51002)
        self.server.handle(b'{"type":"join","name":"Alpha"}', self.address1)
        self.server.handle(b'{"type":"join","name":"Bravo"}', self.address2)

    def tearDown(self):
        self.server.sock.close()

    def test_players_join_and_move(self):
        self.assertEqual(len(self.server.players), 2)
        p = self.server.players[1]
        initial_x = p["x"]
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        self.assertGreater(p["x"], initial_x)

    def test_firing_produces_bullet_and_event(self):
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":true}',
                           self.address1)
        self.server.step(1 / 30)
        self.assertEqual(len(self.server.bullets), 1)
        self.assertEqual(self.server.events[0]["type"], "fire")

    def test_no_client_position_teleport(self):
        before = (self.server.players[1]["x"], self.server.players[1]["y"])
        self.server.handle(b'{"type":"input","x":1200,"y":1300,"aim":0,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        after = (self.server.players[1]["x"], self.server.players[1]["y"])
        self.assertEqual(before, after)

    def test_duplicate_join_reuses_id(self):
        self.server.handle(b'{"type":"join","name":"Alpha"}', self.address1)
        self.assertEqual(len(self.server.players), 2)

    def test_invalid_payload_is_ignored(self):
        self.server.handle(b"not json", self.address1)
        self.server.handle(b'["wrong shape"]', self.address1)
        self.assertEqual(len(self.server.players), 2)

    def test_hit_and_destruction(self):
        target = self.server.players[2]
        target.update(x=500.0, y=500.0, hp=34)
        self.server.bullets.append({"x": 470.0, "y": 500.0,
                                    "vx": 680.0, "vy": 0.0,
                                    "life": 1.0, "owner": 1})
        self.server.step(1 / 30)
        self.assertTrue(target["respawn"] > 0)
        self.assertEqual(self.server.players[1]["score"], 1)
        self.assertIn("destroy", [e["type"] for e in self.server.events])


    def test_turret_cannot_snap_to_cursor(self):
        player = self.server.players[1]
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":3.141592653589793,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        delta = (player["turret"] + 3.141592653589793) % (2 * 3.141592653589793) - 3.141592653589793
        self.assertLessEqual(abs(delta), TURRET_SPEED / 30 + 1e-7)
        self.assertGreater(abs(delta), 0)

    def test_wall_requires_four_hits_then_passes_tank(self):
        wx, wy, ww, wh = WALL_SECTIONS[0]
        # Fire repeatedly into the same first wall section.
        for expected in (3, 2, 1, 0):
            self.server.bullets.append({"x": wx - 20.0, "y": wy + wh / 2,
                                        "vx": 680.0, "vy": 0.0,
                                        "life": 1.0, "owner": 1})
            self.server.step(1 / 30)
            self.assertEqual(self.server.wall_hp[0], expected)
            self.assertEqual(overlaps_wall(wx + 6, wy + wh / 2, 3,
                                            self.server.wall_hp), expected > 0)
        self.assertIn("wall_break", [e["type"] for e in self.server.events])

    def test_wall_damage_is_in_snapshot(self):
        self.assertEqual(len(self.server.wall_hp), len(WALL_SECTIONS))
        self.assertTrue(all(hp == WALL_MAX_HP for hp in self.server.wall_hp))


class ViewportTests(unittest.TestCase):
    def test_widescreen_letterboxes_without_extra_world(self):
        view = viewport(1920, 1080)
        self.assertEqual(view, (107, 0, 1705, 1080))
        self.assertAlmostEqual(to_logical((107 + 1705 / 2, 540), view)[0], 600)
        self.assertAlmostEqual(to_logical((107 + 1705 / 2, 540), view)[1], 380)

    def test_native_size_is_identity(self):
        view = viewport(1200, 760)
        self.assertEqual(view, (0, 0, 1200, 760))
        self.assertEqual(to_logical((900, 330), view), (900, 330))

    def test_taller_monitor_letterboxes(self):
        view = viewport(1280, 1024)
        self.assertEqual(view[2], 1280)
        self.assertGreater(view[1], 0)


if __name__ == "__main__":
    unittest.main()
