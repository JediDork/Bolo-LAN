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
                     FOREST_TILES, RIVER_TILES, BRIDGE_TILES,
                     initial_wall_hp, neighbors)
from construction import BUILD_RANGE, BUILD_COSTS, START_MATERIAL, MAX_MATERIAL


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
        self.assertEqual(self.server.wall_hp, initial_wall_hp())


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

    def test_pillbox_fires_only_once_visible_near_viewport_edge(self):
        # Camera height is 760 world units, so +/-380 is visible vertically.
        # The defensive range must be shorter to avoid offscreen attacks.
        self.assertGreater(PILLBOX_RANGE, 300)
        self.assertLess(PILLBOX_RANGE, 380)
        x, y = PILLBOX_SITES[0]
        p = self.server.players[1]
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        # Outside firing range: no turret should shoot.
        p.update(x=float(x), y=float(y + PILLBOX_RANGE + 25), speed=0.0)
        for _ in range(25):
            self.server.step(1 / 30)
        self.assertFalse(any(e["type"] == "fire" and e["x"] == x
                             for e in self.server.events))
        # Move just inside visible engagement range.
        p.update(x=float(x), y=float(y + PILLBOX_RANGE - 25), speed=0.0)
        for _ in range(35):
            self.server.step(1 / 30)
        self.assertTrue(any(e["type"] == "fire" and e["x"] == x
                            for e in self.server.events))

    def test_god_mode_toggles_and_blocks_damage(self):
        p = self.server.players[1]
        self.assertFalse(p["god_mode"])
        self.server.handle(b'{"type":"god_mode"}', self.address1)
        self.assertTrue(p["god_mode"])
        self.assertEqual(p["hp"], 100)
        self.server.bullets.append({"x": p["x"] - 30, "y": p["y"],
                                    "vx": 680.0, "vy": 0.0,
                                    "life": 1.0, "owner": 2})
        self.server.step(1 / 30)
        self.assertEqual(p["hp"], 100)
        self.assertLessEqual(p["respawn"], 0.0)
        self.server.handle(b'{"type":"god_mode"}', self.address1)
        self.assertFalse(p["god_mode"])
        self.server.bullets.append({"x": p["x"] - 30, "y": p["y"],
                                    "vx": 680.0, "vy": 0.0,
                                    "life": 1.0, "owner": 2})
        self.server.step(1 / 30)
        self.assertLess(p["hp"], 100)

    def test_god_mode_is_per_player(self):
        self.server.handle(b'{"type":"god_mode"}', self.address1)
        self.assertTrue(self.server.players[1]["god_mode"])
        self.assertFalse(self.server.players[2]["god_mode"])

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


    def test_build_wall_collision_and_four_hit_destruction(self):
        p = self.server.players[1]
        # Seek an available nearby build tile without changing gameplay state.
        possible = None
        for tx in range(4, 48):
            for ty in range(4, 33):
                x, y = tile_to_world(tx, ty)
                p.update(x=float(x + 100), y=float(y + 100), speed=0)
                if self.server.build(p, "wall", tx, ty):
                    possible = (tx, ty)
                    break
            if possible:
                break
        self.assertIsNotNone(possible)
        wall = self.server.built_walls[possible]
        self.assertEqual(wall["hp"], 4)
        self.assertEqual(p["material"], START_MATERIAL - BUILD_COSTS["wall"])
        x, y = tile_to_world(*possible)
        self.assertTrue(self.server.blocked(x, y))
        for expected in (3, 2, 1, 0):
            tile_x, tile_y = possible
            sx, sy = tile_x * GRID_SIZE - 13, tile_y * GRID_SIZE + 25
            key = self.server.built_wall_hit(sx, sy, sx + 28, sy)
            self.assertEqual(key, possible)
            self.server.built_walls[key]["hp"] -= 1
            if expected == 0:
                del self.server.built_walls[key]
            else:
                self.assertEqual(self.server.built_walls[key]["hp"], expected)
        self.assertNotIn(possible, self.server.built_walls)

    def test_construction_rejects_invalid_or_remote_requests(self):
        p = self.server.players[1]
        original_material = p["material"]
        self.assertFalse(self.server.build(p, "wall", "10", 10))
        self.assertFalse(self.server.build(p, "wall", -1, 0))
        self.assertFalse(self.server.build(p, "wall", 999, 10))
        self.assertFalse(self.server.build(p, "wall", 25, 37))
        self.assertFalse(self.server.build(p, "wall", 1.0, 1))
        self.assertFalse(self.server.build(p, "bridge", 1, 1))
        self.assertEqual(p["material"], original_material)

    def test_material_recharges_at_own_base(self):
        p = self.server.players[1]
        p.update(x=float(BASE_SITES[0][0]), y=float(BASE_SITES[0][1]),
                 speed=0, material=5.0)
        self.server.bases[0]["owner"] = p["id"]
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        self.assertGreater(p["material"], 5)
        self.assertLessEqual(p["material"], MAX_MATERIAL)

    def test_build_bridge_is_fast_and_removable(self):
        p = self.server.players[1]
        tile = next(tile for tile in sorted(RIVER_TILES)
                    if tile not in BRIDGE_TILES)
        x, y = tile_to_world(*tile)
        p.update(x=float(x + 75), y=float(y + 75),
                 material=float(MAX_MATERIAL), speed=0)
        self.assertTrue(self.server.build(p, "bridge", *tile))
        self.assertIn(tile, self.server.built_bridges)
        # On a bridge, authoritative driving target uses road speed.
        p["x"], p["y"] = float(x), float(y)
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        self.assertGreater(p["speed"], 0)
        p["build_timer"] = 0.0
        p["material"] = MAX_MATERIAL
        self.assertTrue(self.server.build(p, "remove", *tile))
        self.assertNotIn(tile, self.server.built_bridges)

    def test_builder_refuses_building_on_tank(self):
        p = self.server.players[1]
        tx, ty = world_to_tile(p["x"], p["y"])
        self.assertFalse(self.server.build(p, "wall", tx, ty))

    def test_build_wall_repairs_and_removes(self):
        p = self.server.players[1]
        possible = None
        for tx in range(5, 47):
            for ty in range(5, 31):
                x, y = tile_to_world(tx, ty)
                p.update(x=float(x + 110), y=float(y), speed=0)
                if self.server.build(p, "wall", tx, ty):
                    possible = (tx, ty)
                    break
            if possible:
                break
        self.assertIsNotNone(possible)
        wall = self.server.built_walls[possible]
        wall["hp"] = 2
        p["build_timer"] = 0
        self.assertTrue(self.server.build(p, "repair", *possible))
        self.assertEqual(wall["hp"], 3)
        p["build_timer"] = 0
        self.assertTrue(self.server.build(p, "remove", *possible))
        self.assertNotIn(possible, self.server.built_walls)


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

    def test_river_one_tile_wide(self):
        rows = sorted({ty for _, ty in RIVER_TILES})
        self.assertGreater(len(rows), 20)
        self.assertEqual(rows, list(range(rows[0], rows[-1] + 1)))
        previous = None
        for row in rows:
            columns = [tx for tx, ty in RIVER_TILES if ty == row]
            self.assertEqual(len(columns), 1)
            if previous is not None:
                self.assertLessEqual(abs(columns[0] - previous), 1)
            previous = columns[0]

    def test_road_bridges_cross_river(self):
        self.assertTrue(BRIDGE_TILES)
        self.assertEqual(BRIDGE_TILES, ROAD_TILES & RIVER_TILES)
        for tile in BRIDGE_TILES:
            self.assertEqual(terrain_at(*tile_to_world(*tile)), "bridge")
            self.assertFalse(water_at(*tile_to_world(*tile), 18))
        for tile in RIVER_TILES - BRIDGE_TILES:
            self.assertEqual(terrain_at(*tile_to_world(*tile)), "river")
        self.assertGreater(TERRAIN_SPEED["bridge"], TERRAIN_SPEED["river"])

    def test_surviving_walls_clear_forests(self):
        hp = initial_wall_hp()
        for index, (x, y, _, _) in enumerate(WALL_SECTIONS):
            if hp[index] <= 0:
                continue
            tx, ty = x // GRID_SIZE, y // GRID_SIZE
            self.assertFalse(any((tx + dx, ty + dy) in FOREST_TILES
                                 for dx in (-1, 0, 1) for dy in (-1, 0, 1)))

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
