"""Headless smoke tests for the LAN gameplay server."""
import json
import socket
import unittest

from server import (GameServer, TURRET_SPEED, MOVE_SPEED, REVERSE_SPEED,
                    ACCELERATION, PILLBOX_RANGE)
from shared import (GRID_SIZE, WALLS, WALL_SECTIONS, WALL_MAX_HP,
                    wall_at, overlaps_wall, world_to_tile, tile_to_world)
from display import viewport, to_logical
from terrain import (BASE_SITES, BASE_TILES, PILLBOX_SITES, TERRAIN_SPEED,
                     terrain_at, water_at, ROAD_TILES, LAKE_TILES,
                     FOREST_TILES, RIVER_TILES, neighbors)


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


    def test_acceleration_and_coasting(self):
        p = self.server.players[1]
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}', self.address1)
        self.server.step(1 / 30)
        first = p["speed"]
        self.assertGreater(first, 0)
        self.assertLess(first, 195)
        for _ in range(5):
            self.server.step(1 / 30)
        self.assertGreater(p["speed"], first)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        before = p["speed"]
        self.server.step(1 / 30)
        self.assertGreater(p["speed"], 0)
        self.assertLess(p["speed"], before)

    def test_terrain_effects_and_water_collision(self):
        self.assertEqual(terrain_at(*BASE_SITES[0]), "road")
        forest_tile = next(tile for tile in sorted(FOREST_TILES)
                           if tile not in ROAD_TILES)
        forest_x, forest_y = tile_to_world(*forest_tile)
        self.assertEqual(terrain_at(forest_x, forest_y), "forest")
        lake_tile = sorted(LAKE_TILES)[len(LAKE_TILES) // 2]
        lake_x, lake_y = tile_to_world(*lake_tile)
        self.assertEqual(terrain_at(lake_x, lake_y), "water")
        self.assertTrue(water_at(lake_x, lake_y, 18))
        self.assertTrue(self.server.blocked(lake_x, lake_y))
        self.assertGreater(TERRAIN_SPEED["road"], TERRAIN_SPEED["forest"])
        self.assertGreater(TERRAIN_SPEED["forest"], TERRAIN_SPEED["river"])
        self.assertGreater(TERRAIN_SPEED["river"], TERRAIN_SPEED["water"])

    def test_river_is_fordable_but_severely_slows_moving_tank(self):
        river_tile = next(tile for tile in sorted(RIVER_TILES)
                          if tile not in LAKE_TILES)
        x, y = tile_to_world(*river_tile)
        self.assertEqual(terrain_at(x, y), "river")
        self.assertFalse(water_at(x, y, 18))
        p = self.server.players[1]
        p.update(x=float(x), y=float(y), angle=0.0, speed=125.0)
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}', self.address1)
        self.server.step(1 / 30)
        self.assertLess(p["speed"], 125.0)
        for _ in range(35):
            # Hold the position in shallow river to isolate its traction
            # model from a route that might exit the river after 1 second.
            p["x"], p["y"] = float(x), float(y)
            self.server.step(1 / 30)
        self.assertLessEqual(abs(p["speed"]), 125.0 * TERRAIN_SPEED["river"] + 5.0)

    def test_base_capture_and_repair(self):
        p = self.server.players[1]
        bx, by = BASE_SITES[0]
        p.update(x=float(bx), y=float(by), speed=0.0, hp=50, ammo=12)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        for _ in range(85):
            self.server.step(1 / 30)
        self.assertEqual(self.server.bases[0]["owner"], p["id"])
        self.assertIn("capture", [e["type"] for e in self.server.events])
        for _ in range(40):
            self.server.step(1 / 30)
        self.assertGreater(p["hp"], 50)
        self.assertGreater(p["ammo"], 12)

    def test_reduced_drive_speed_and_acceleration(self):
        self.assertEqual(MOVE_SPEED, 125.0)
        self.assertEqual(REVERSE_SPEED, 75.0)
        self.assertEqual(ACCELERATION, 115.0)
        p = self.server.players[1]
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}', self.address1)
        self.server.step(1 / 30)
        self.assertAlmostEqual(p["speed"], ACCELERATION / 30.0)
        for _ in range(200):
            self.server.step(1 / 30)
        self.assertLessEqual(p["speed"], MOVE_SPEED * TERRAIN_SPEED["road"] + 0.01)

    def test_pillbox_engages_at_extended_distance(self):
        self.assertGreaterEqual(PILLBOX_RANGE, 800)
        box = self.server.pillboxes[0]
        x, y = PILLBOX_SITES[0]
        p = self.server.players[1]
        p.update(x=float(x + 650), y=float(y), speed=0.0)
        # Disable the other pillboxes so this assertion tests the intended turret.
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        for _ in range(25):
            self.server.step(1 / 30)
        self.assertTrue(any(event["type"] == "fire" and event["x"] == x
                            for event in self.server.events))

    def test_pillbox_targeting_and_destruction(self):
        box = self.server.pillboxes[0]
        x, y = PILLBOX_SITES[0]
        p = self.server.players[1]
        p.update(x=x + 105.0, y=float(y), speed=0.0)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        for _ in range(32):
            self.server.step(1 / 30)
        self.assertTrue(any(b["owner"] == -1 for b in self.server.bullets)
                        or any(e["type"] == "fire" and e["x"] == x for e in self.server.events))
        for _ in range(4):
            self.server.bullets.append({"x": x - 30.0, "y": float(y),
                                        "vx": 680.0, "vy": 0.0,
                                        "life": 1.0, "owner": 1})
            self.server.step(1 / 30)
        self.assertEqual(box["hp"], 0)


class ConstructionGridTests(unittest.TestCase):
    def test_wall_segments_are_exact_grid_tiles(self):
        self.assertGreater(len(WALL_SECTIONS), 0)
        for x, y, w, h in WALL_SECTIONS:
            self.assertEqual((w, h), (GRID_SIZE, GRID_SIZE))
            self.assertEqual(x % GRID_SIZE, 0)
            self.assertEqual(y % GRID_SIZE, 0)

    def test_all_natural_terrain_is_grid_based(self):
        for kind, tiles in (("river", RIVER_TILES), ("lake", LAKE_TILES),
                            ("forest", FOREST_TILES), ("road", ROAD_TILES)):
            self.assertTrue(tiles, kind)
            for tx, ty in tiles:
                self.assertGreaterEqual(tx, 0)
                self.assertGreaterEqual(ty, 0)
                self.assertLess(tx, 52)
                self.assertLess(ty, 38)

    def test_flags_are_connected_by_routed_road_network(self):
        passable = ROAD_TILES | RIVER_TILES
        visited = {BASE_TILES[0]}
        queue = [BASE_TILES[0]]
        for tile in queue:
            for neighbor in neighbors(tile):
                if neighbor in passable and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        for base in BASE_TILES:
            self.assertIn(base, visited)

    def test_lakes_and_forests_have_irregular_edges(self):
        # Their tile-row widths change as the organic contour is traversed.
        for tiles in (LAKE_TILES, FOREST_TILES):
            widths = [len([1 for tx, ty in tiles if ty == row])
                      for row in {y for _, y in tiles}]
            self.assertGreater(len(set(widths)), 2)

    def test_base_and_pillbox_centres_share_grid(self):
        for x, y in BASE_SITES + PILLBOX_SITES:
            with self.subTest(site=(x, y)):
                self.assertEqual(x % GRID_SIZE, GRID_SIZE // 2)
                self.assertEqual(y % GRID_SIZE, GRID_SIZE // 2)
                self.assertEqual(tile_to_world(*world_to_tile(x, y)), (x, y))

    def test_destroyed_wall_still_clears_exactly_one_tile(self):
        x, y, w, h = WALL_SECTIONS[0]
        hp = [WALL_MAX_HP] * len(WALL_SECTIONS)
        hp[0] = 0
        self.assertFalse(overlaps_wall(x + 5, y + GRID_SIZE / 2, 3, hp))


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
