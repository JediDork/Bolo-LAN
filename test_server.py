"""Headless smoke tests for the LAN gameplay server."""
import json
import math
import socket
import unittest

from server import (GameServer, TURRET_SPEED, MOVE_SPEED, REVERSE_SPEED,
                    SPAWN_PLAYER_DISTANCE, SPAWN_SAFE_RADIUS,
                    ACCELERATION, PILLBOX_RANGE, PILLBOX_DETECTION_RANGE,
                    PILLBOX_TURN_SPEED, FOREST_PENETRATION_TILES)
from shared import (GRID_SIZE, WALLS, WALL_SECTIONS, WALL_MAX_HP,
                    WORLD_W, WORLD_H, wrap_x, shortest_dx, nearest_x,
                    wrapped_distance,
                    wall_at, overlaps_wall, world_to_tile, tile_to_world)
from display import viewport, to_logical
from terrain import (BASE_SITES, BASE_TILES, PILLBOX_SITES, TERRAIN_SPEED,
                     terrain_at, water_at, ROAD_TILES, LAKE_TILES,
                     FOREST_TILES, RIVER_TILES, BRIDGE_TILES,
                     initial_wall_hp, neighbors, RIVER_PATHS, LAKE_PATCHES,
                     GRID_W, GRID_H, MAX_FLAGS_PER_MAP, MAP_FLAG_COUNT,
                     MAP_SEED, select_flag_tiles)
from construction import BUILD_RANGE, BUILD_COSTS, START_MATERIAL, MAX_MATERIAL


class GameServerTests(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(0)
        self.address1 = ("127.0.0.1", 51001)
        self.address2 = ("127.0.0.1", 51002)
        self.server.handle(b'{"type":"join","name":"Alpha"}', self.address1)
        self.server.handle(b'{"type":"join","name":"Bravo"}', self.address2)
        # Existing movement/combat tests need a stable, unshielded baseline.
        # Spawn rules and grace are tested separately in SpawnAndReloadTests.
        self.server.players[1].update(
            x=170.0, y=170.0, angle=0.0, turret=0.0, speed=0.0,
            angular_speed=0.0, spawn_grace=0.0)
        self.server.players[2].update(
            x=float(WORLD_W - 170), y=float(WORLD_H - 170),
            angle=math.pi, turret=math.pi, speed=0.0,
            angular_speed=0.0, spawn_grace=0.0)

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

    def test_flags_seeded_selection_is_bounded_and_repeatable(self):
        self.assertEqual(len(BASE_TILES), 6)
        self.assertEqual(len(self.server.bases), 6)
        self.assertEqual(select_flag_tiles(MAP_SEED, 6), BASE_TILES)
        self.assertEqual(len(set(BASE_TILES)), 6)
        self.assertEqual(len(select_flag_tiles(MAP_SEED + 1, 3)), 3)
        with self.assertRaises(ValueError):
            select_flag_tiles(MAP_SEED, 7)
        with self.assertRaises(ValueError):
            select_flag_tiles(MAP_SEED, 0)

    def test_refill_sounds_are_local_rate_limited_and_full_once(self):
        p = self.server.players[1]
        bx, by = BASE_SITES[0]
        p.update(x=float(bx), y=float(by), speed=0,
                 ammo=20.0, material=27.0)
        self.server.players[2].update(x=4000.0, y=3400.0)
        self.server.bases[0]["owner"] = p["id"]
        self.server.events.clear()
        self.server.update_bases(0.1)
        kinds = [event["type"] for event in self.server.events]
        self.assertEqual(kinds.count("ammo_added"), 1)
        self.assertEqual(kinds.count("material_added"), 1)
        self.assertTrue(all(event["recipient"] == p["id"]
                            for event in self.server.events))
        self.server.update_bases(0.1)
        self.assertEqual(len(self.server.events), 2)
        p["ammo"] = 23.9
        p["material"] = MAX_MATERIAL - 0.05
        self.server.update_bases(0.1)
        kinds = [event["type"] for event in self.server.events]
        self.assertEqual(kinds.count("ammo_full"), 1)
        self.assertEqual(kinds.count("material_full"), 1)
        self.server.update_bases(2.0)
        kinds = [event["type"] for event in self.server.events]
        self.assertEqual(kinds.count("ammo_full"), 1)
        self.assertEqual(kinds.count("material_full"), 1)

    def test_flag_capture_notifies_both_new_and_previous_owners(self):
        p = self.server.players[1]
        previous = self.server.players[2]
        bx, by = BASE_SITES[0]
        p.update(x=float(bx), y=float(by), speed=0.0)
        previous.update(x=4000.0, y=3400.0)
        self.server.bases[0]["owner"] = previous["id"]
        self.server.events.clear()
        self.server.update_bases(2.6)
        taken = [e for e in self.server.events if e["type"] == "flag_taken"]
        lost = [e for e in self.server.events if e["type"] == "flag_lost"]
        self.assertEqual(len(taken), 1)
        self.assertEqual(len(lost), 1)
        self.assertEqual(taken[0]["recipient"], p["id"])
        self.assertEqual(lost[0]["recipient"], previous["id"])
        self.server.update_bases(0.1)
        self.assertEqual(len([e for e in self.server.events
                              if e["type"] == "flag_taken"]), 1)

    def test_reduced_drive_speed_and_acceleration(self):
        self.assertEqual(MOVE_SPEED, 95.0)
        self.assertEqual(REVERSE_SPEED, 55.0)
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
        box = self.server.pillboxes[0]
        box.update(x=250.0, y=350.0, angle=0.0)
        x, y = box["x"], box["y"]
        p = self.server.players[1]
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}', self.address1)
        # In the larger tracking range but beyond firing distance:
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

    def test_pillbox_tracks_before_firing_and_turn_rate_is_limited(self):
        box = self.server.pillboxes[0]
        box.update(x=250.0, y=350.0, angle=0.0, cooldown=0.0)
        p = self.server.players[1]
        p.update(x=250.0, y=350.0 + PILLBOX_RANGE + 28, speed=0.0)
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.assertLess(PILLBOX_RANGE, PILLBOX_DETECTION_RANGE)
        self.assertLess(PILLBOX_DETECTION_RANGE, 520)
        self.server.update_pillboxes(1 / 30)
        self.assertTrue(box["tracking"])
        self.assertGreater(box["angle"], 0.0)
        self.assertLessEqual(box["angle"], PILLBOX_TURN_SPEED / 30 + 1e-6)
        self.assertEqual(len(self.server.bullets), 0)
        for _ in range(70):
            self.server.update_pillboxes(1 / 30)
        self.assertEqual(len(self.server.bullets), 0)
        p["y"] = box["y"] + PILLBOX_RANGE - 30
        for _ in range(35):
            self.server.update_pillboxes(1 / 30)
        self.assertTrue(self.server.bullets)
        self.assertAlmostEqual(box["angle"], math.pi / 2, delta=0.14)

    def test_forest_blocks_after_two_distinct_tiles(self):
        # Find a clean three-cell forest corridor with no surviving walls.
        found = None
        for tx, ty in sorted(FOREST_TILES):
            cells = [(tx + i, ty) for i in range(3)]
            if all(cell in FOREST_TILES for cell in cells):
                x0, y0 = tile_to_world(tx, ty)
                x1, y1 = tile_to_world(tx + 2, ty)
                if not self.server.wall_obstruction_at(x0, y0) and not self.server.wall_obstruction_at(x1, y1):
                    found = (x0 - 12, y0, x1 + 12, y1)
                    break
        self.assertIsNotNone(found)
        x0, y0, x1, y1 = found
        self.assertEqual(FOREST_PENETRATION_TILES, 2)
        bullet = {"forest_depth": 0}
        obstruction = self.server.shell_obstruction(bullet, x0, y0, x1, y1)
        self.assertIsNotNone(obstruction)
        self.assertEqual(obstruction[0], "forest")
        self.assertFalse(self.server.can_see(x0, y0, x1, y1))

    def test_wall_blocks_pillbox_vision(self):
        # Use an actual intact wall section, never a hard-coded map location.
        index = next(i for i, hp in enumerate(self.server.wall_hp) if hp > 0)
        wx, wy, ww, wh = WALL_SECTIONS[index]
        x0, y0 = wx - 15.0, wy + wh / 2
        x1, y1 = wx + ww + 15.0, wy + wh / 2
        self.assertFalse(self.server.can_see(x0, y0, x1, y1))
        self.server.wall_hp[index] = 0
        # This may cross another wall, so verify direct obstruction is gone.
        self.assertIsNone(self.server.wall_obstruction_at(wx + ww / 2, wy + wh / 2))

    def test_reversing_inverts_hull_turn(self):
        p = self.server.players[1]
        p["speed"] = -30.0
        self.server.handle(b'{"type":"input","move":-1,"turn":1,"aim":0,"fire":false}',
                           self.address1)
        before = p["angle"]
        self.server.step(1 / 30)
        delta = (p["angle"] - before + math.pi) % (2 * math.pi) - math.pi
        self.assertLess(delta, 0)

    def test_tracking_pillbox_does_not_fire_first_beyond_inner_range(self):
        box = self.server.pillboxes[0]
        box.update(x=250.0, y=350.0, angle=math.pi / 2,
                   cooldown=0.0, retaliation_timer=0.0, retaliation_target=0)
        player = self.server.players[1]
        player.update(x=250.0, y=350.0 + PILLBOX_RANGE + 50,
                      turret=-math.pi / 2, speed=0.0)
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        for _ in range(65):
            self.server.update_pillboxes(1 / 30)
        self.assertTrue(box["tracking"])
        self.assertFalse(self.server.bullets)

    def test_aimed_shot_provokes_visible_pillbox(self):
        box = self.server.pillboxes[0]
        box.update(x=250.0, y=350.0, angle=math.pi / 2,
                   cooldown=0.0, retaliation_timer=0.0, retaliation_target=0)
        player = self.server.players[1]
        player.update(x=250.0, y=350.0 + PILLBOX_RANGE + 50,
                      turret=-math.pi / 2, speed=0.0)
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.assertTrue(self.server.can_see(box["x"], box["y"],
                                             player["x"], player["y"]))
        self.server.alert_pillboxes(player, -math.pi / 2)
        self.assertEqual(box["retaliation_target"], player["id"])
        self.assertGreater(box["retaliation_timer"], 0)
        for _ in range(80):
            self.server.update_pillboxes(1 / 30)
        self.assertTrue(self.server.bullets)

    def test_unrelated_shot_does_not_provoke_pillbox(self):
        box = self.server.pillboxes[0]
        box.update(x=250.0, y=350.0)
        player = self.server.players[1]
        player.update(x=250.0, y=350.0 + PILLBOX_RANGE + 40)
        self.server.alert_pillboxes(player, math.pi / 2)
        self.assertEqual(box["retaliation_timer"], 0.0)

    def test_walls_block_retaliation_and_target_detection(self):
        box = self.server.pillboxes[0]
        index = next(i for i, hp in enumerate(self.server.wall_hp) if hp > 0)
        wx, wy, ww, wh = WALL_SECTIONS[index]
        box.update(x=wx - 80.0, y=wy + wh / 2,
                   retaliation_timer=0.0, retaliation_target=0)
        player = self.server.players[1]
        player.update(x=wx + ww + 80.0, y=wy + wh / 2)
        self.assertFalse(self.server.can_see(box["x"], box["y"],
                                              player["x"], player["y"]))
        self.server.alert_pillboxes(player, math.pi)
        self.assertEqual(box["retaliation_timer"], 0.0)

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

    def test_ownership_prevents_enemy_dismantle(self):
        p = self.server.players[1]
        enemy = self.server.players[2]
        tile = next(t for t in sorted(RIVER_TILES) if t not in BRIDGE_TILES)
        x, y = tile_to_world(*tile)
        p.update(x=float(x + 75), y=float(y + 75), speed=0)
        enemy.update(x=float(x - 75), y=float(y + 75), speed=0)
        self.assertTrue(self.server.build(p, "bridge", *tile))
        self.assertEqual(self.server.bridge_owners[tile], p["id"])
        self.assertFalse(self.server.build(enemy, "remove", *tile))
        self.assertIn(tile, self.server.built_bridges)

    def test_build_pillbox_and_repair_it(self):
        p = self.server.players[1]
        p["material"] = MAX_MATERIAL
        chosen = None
        for tx in range(5, 45):
            for ty in range(5, 33):
                x, y = tile_to_world(tx, ty)
                p.update(x=float(x + 105), y=float(y + 80), speed=0)
                if self.server.build(p, "pillbox", tx, ty):
                    chosen = tx, ty
                    break
            if chosen:
                break
        self.assertIsNotNone(chosen)
        x, y = tile_to_world(*chosen)
        box = next(b for b in self.server.pillboxes
                   if b["x"] == x and b["y"] == y)
        self.assertEqual(box["owner"], p["id"])
        box["hp"] = 50
        p["build_timer"] = 0
        self.assertTrue(self.server.build(p, "repair", *chosen))
        self.assertEqual(box["hp"], 75)

    def test_road_building_driving_and_removal(self):
        player = self.server.players[1]
        chosen = None
        for tx in range(5, 47):
            for ty in range(5, 32):
                x, y = tile_to_world(tx, ty)
                player.update(x=float(x + 110), y=float(y), speed=0,
                              material=float(MAX_MATERIAL), build_timer=0)
                if self.server.build(player, "road", tx, ty):
                    chosen = (tx, ty)
                    break
            if chosen is not None:
                break
        self.assertIsNotNone(chosen)
        self.assertEqual(self.server.built_roads[chosen], player["id"])
        self.assertEqual(player["material"], MAX_MATERIAL - BUILD_COSTS["road"])
        x, y = tile_to_world(*chosen)
        player.update(x=float(x), y=float(y), speed=0)
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}',
                           self.address1)
        self.server.step(1 / 30)
        self.assertGreater(player["speed"], 0)
        self.assertIn(list(chosen), [list(t) for t in sorted(self.server.built_roads)])
        player["build_timer"] = 0
        self.assertTrue(self.server.build(player, "remove", *chosen))
        self.assertNotIn(chosen, self.server.built_roads)

    def test_roads_reject_water_and_existing_roads(self):
        player = self.server.players[1]
        player["material"] = MAX_MATERIAL
        for tile in (next(iter(LAKE_TILES)),
                     next(iter(RIVER_TILES - BRIDGE_TILES)),
                     next(iter(ROAD_TILES))):
            x, y = tile_to_world(*tile)
            player.update(x=float(x), y=float(y), build_timer=0)
            self.assertFalse(self.server.build(player, "road", *tile))

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
                self.assertLess(tx, GRID_W)
                self.assertLess(ty, GRID_H)

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

    def test_rivers_start_at_world_edge_and_finish_at_lake(self):
        self.assertGreaterEqual(len(RIVER_PATHS), 2)
        for path in RIVER_PATHS:
            self.assertGreater(len(path), 10)
            self.assertTrue(path[0][0] in (0, WORLD_W // GRID_SIZE - 1)
                            or path[0][1] in (0, WORLD_H // GRID_SIZE - 1))
            last = path[-1]
            self.assertTrue(any((last[0] + dx, last[1] + dy) in LAKE_TILES
                                for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))),
                            "River must flow directly into a lake")
            for a, b in zip(path, path[1:]):
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1,
                                 "River must remain one grid cell wide and continuous")

    def test_world_is_four_times_original_play_area(self):
        self.assertEqual((WORLD_W, WORLD_H), (5200, 3800))
        self.assertEqual(len(BASE_TILES), MAP_FLAG_COUNT)
        self.assertEqual(len(BASE_TILES), MAX_FLAGS_PER_MAP)
        self.assertGreaterEqual(len(PILLBOX_SITES), 16)

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


class SpawnAndReloadTests(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(0)
        self.first_addr = ("127.0.0.1", 51101)
        self.second_addr = ("127.0.0.1", 51102)
        self.server.handle(b'{"type":"join","name":"First"}', self.first_addr)

    def tearDown(self):
        self.server.sock.close()

    def test_new_players_start_on_available_neutral_flag(self):
        player = self.server.players[1]
        self.assertIn((player["x"], player["y"]),
                      {(b["x"], b["y"]) for b in self.server.bases if b["owner"] == 0})
        self.assertEqual(player["spawn_kind"], "flag")
        self.assertGreater(player["spawn_grace"], 0)

    def test_joining_player_does_not_spawn_on_existing_tank(self):
        first = self.server.players[1]
        self.server.handle(b'{"type":"join","name":"Second"}', self.second_addr)
        second = self.server.players[2]
        self.assertGreaterEqual(
            wrapped_distance(first["x"], first["y"],
                             second["x"], second["y"]), SPAWN_PLAYER_DISTANCE)

    def test_respawn_uses_owned_flag_not_unclaimed_flag(self):
        player = self.server.players[1]
        owned = self.server.bases[0]
        owned["owner"] = player["id"]
        # Other neutral flags still exist; respawn must not take one.
        self.assertTrue(any(base["owner"] == 0 for base in self.server.bases))
        player.update(x=2300.0, y=2300.0, respawn=0.0)
        self.server.spawn(player)
        self.assertEqual(player["spawn_kind"], "owned_flag")
        self.assertEqual((player["x"], player["y"]),
                         (owned["x"], owned["y"]))

    def test_all_flags_claimed_but_player_owns_one_respawns_at_it(self):
        player = self.server.players[1]
        for base in self.server.bases:
            base["owner"] = 2
        owned = self.server.bases[2]
        owned["owner"] = player["id"]
        self.server.spawn(player)
        self.assertEqual(player["spawn_kind"], "owned_flag")
        self.assertEqual((player["x"], player["y"]),
                         (owned["x"], owned["y"]))

    def test_player_with_no_flags_falls_back_to_unclaimed_flag(self):
        player = self.server.players[1]
        self.server.bases[0]["owner"] = 2
        self.server.spawn(player)
        self.assertEqual(player["spawn_kind"], "flag")
        self.assertIn((player["x"], player["y"]),
                      {(b["x"], b["y"]) for b in self.server.bases
                       if b["owner"] == 0})

    def test_blocked_owned_flag_never_sends_player_to_neutral_flag(self):
        player = self.server.players[1]
        base = self.server.bases[0]
        base["owner"] = player["id"]
        self.server.handle(b'{"type":"join","name":"Second"}', self.second_addr)
        opponent = self.server.players[2]
        opponent.update(x=base["x"], y=base["y"], respawn=0.0)
        player.update(x=2300.0, y=2300.0, respawn=0.0)
        self.server.spawn(player)
        self.assertEqual(player["spawn_kind"], "owned_flag")
        self.assertLessEqual(
            wrapped_distance(player["x"], player["y"],
                             base["x"], base["y"]), 55)
        self.assertGreaterEqual(
            wrapped_distance(player["x"], player["y"],
                             opponent["x"], opponent["y"]), 46)

    def test_all_flags_owned_uses_safe_random_ground(self):
        for base in self.server.bases:
            base["owner"] = 1
        self.server.handle(b'{"type":"join","name":"Second"}', self.second_addr)
        second = self.server.players[2]
        self.assertEqual(second["spawn_kind"], "safe")
        self.assertIn(terrain_at(second["x"], second["y"]), ("grass", "road"))
        self.assertFalse(self.server.blocked(second["x"], second["y"]))
        self.assertGreaterEqual(
            self.server.spawn_clearance(second["x"], second["y"], second["id"]),
            SPAWN_SAFE_RADIUS)
        self.assertGreater(second["spawn_grace"], 0)

    def test_reload_sound_happens_between_shots(self):
        from server import RELOAD, RELOAD_SOUND_AT
        self.assertEqual(RELOAD, 1.25)
        self.assertGreater(RELOAD, RELOAD_SOUND_AT)
        player = self.server.players[1]
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":true}',
                           self.first_addr)
        self.server.step(1 / 30)
        self.assertEqual(sum(e["type"] == "fire" for e in self.server.events), 1)
        self.assertFalse(any(e["type"] == "reload" for e in self.server.events))
        self.server.step(0.92)
        sounds = [e for e in self.server.events if e["type"] == "reload"]
        self.assertEqual(len(sounds), 1)
        self.assertEqual(sounds[0]["recipient"], player["id"])
        self.assertEqual(sum(e["type"] == "fire" for e in self.server.events), 1)
        self.server.step(0.36)
        self.assertEqual(sum(e["type"] == "fire" for e in self.server.events), 2)

    def test_reload_timer_is_in_player_snapshots(self):
        from server import RELOAD
        p = self.server.players[1]
        p["reload"] = 0.75
        # Capture the payload without requiring a running client.
        captured = []
        old_transmit = self.server.transmit
        self.server.transmit = lambda address, packet: captured.append(packet)
        try:
            self.server.snapshot()
        finally:
            self.server.transmit = old_transmit
        self.assertTrue(captured)
        player = next(item for item in captured[0]["players"]
                      if item["id"] == p["id"])
        self.assertEqual(player["reload"], 0.75)
        self.assertEqual(player["reload_duration"], RELOAD)

    def test_cannon_does_not_fire_during_long_reload(self):
        from server import RELOAD
        self.assertGreaterEqual(RELOAD, 1.1)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":true}',
                           self.first_addr)
        self.server.step(0.03)
        first = sum(e["type"] == "fire" for e in self.server.events)
        self.assertEqual(first, 1)
        self.server.step(0.7)
        self.assertEqual(sum(e["type"] == "fire" for e in self.server.events), first)
        self.server.step(0.58)
        self.assertEqual(sum(e["type"] == "fire" for e in self.server.events), 2)

    def test_spawn_grace_prevents_turret_targeting_and_damage(self):
        player = self.server.players[1]
        player.update(x=200.0, y=350.0, spawn_grace=2.0)
        box = self.server.pillboxes[0]
        box.update(x=200.0, y=530.0, cooldown=0.0)
        for other in self.server.pillboxes[1:]:
            other["hp"] = 0
        self.server.update_pillboxes(0.1)
        self.assertFalse(box["tracking"])

class PlanetWrapTests(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(0)
        self.addr1 = ("127.0.0.1", 51001)
        self.addr2 = ("127.0.0.1", 51002)
        self.server.handle(b'{"type":"join","name":"East"}', self.addr1)
        self.server.handle(b'{"type":"join","name":"West"}', self.addr2)
        for player in self.server.players.values():
            player["spawn_grace"] = 0.0

    def tearDown(self):
        self.server.sock.close()

    def test_longitude_shortest_path_and_no_latitude_wrap(self):
        self.assertEqual(wrap_x(-10), WORLD_W - 10)
        self.assertEqual(wrap_x(WORLD_W + 10), 10)
        self.assertEqual(shortest_dx(WORLD_W - 10, 10), 20)
        self.assertEqual(shortest_dx(10, WORLD_W - 10), -20)
        self.assertAlmostEqual(nearest_x(10, WORLD_W - 10), WORLD_W + 10)

    def test_tank_drives_east_across_seam_without_bouncing(self):
        player = self.server.players[1]
        player.update(x=float(WORLD_W - 7), y=190.0,
                      angle=0.0, speed=95.0, angular_speed=0)
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":0,"fire":false}',
                           self.addr1)
        self.server.step(0.2)
        self.assertLess(player["x"], 45)
        self.assertGreaterEqual(player["x"], 0)

    def test_tank_drives_west_across_seam_without_bouncing(self):
        player = self.server.players[1]
        player.update(x=8.0, y=190.0, angle=math.pi,
                      turret=math.pi, speed=95.0, angular_speed=0)
        self.server.handle(b'{"type":"input","move":1,"turn":0,"aim":3.14,"fire":false}',
                           self.addr1)
        self.server.step(0.2)
        self.assertGreater(player["x"], WORLD_W - 45)

    def test_shell_crosses_seam_and_hits_other_tank(self):
        attacker = self.server.players[1]
        target = self.server.players[2]
        attacker.update(x=float(WORLD_W - 95), y=165.0,
                        angle=0.0, turret=0.0, speed=0.0)
        target.update(x=45.0, y=165.0, speed=0.0, hp=100)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":true}',
                           self.addr1)
        self.server.handle(b'{"type":"input","move":0,"turn":0,"aim":0,"fire":false}',
                           self.addr2)
        for _ in range(12):
            self.server.step(1 / 30)
        self.assertLess(target["hp"], 100)

    def test_pillbox_line_of_sight_uses_shortest_wrapped_path(self):
        # Clear empty longitude seam should be visible, not a 5200-unit ray.
        self.assertTrue(self.server.can_see(WORLD_W - 45, 170, 45, 170))

    def test_bases_are_capturable_from_opposite_edge(self):
        base = self.server.bases[0]
        base.update(x=25.0, y=200.0)
        p = self.server.players[1]
        p.update(x=float(WORLD_W - 20), y=200.0, speed=0.0)
        self.server.players[2].update(x=500.0, y=500.0)
        self.assertLess(shortest_dx(p["x"], base["x"]), 60)
        self.server.update_bases(2.6)
        self.assertEqual(base["owner"], p["id"])

    def test_build_range_works_across_east_west_seam(self):
        player = self.server.players[1]
        player.update(x=float(WORLD_W - 60), y=220.0,
                      material=MAX_MATERIAL, build_timer=0)
        # No client teleport: just a wrap-aware build distance check.
        from construction import in_build_range
        self.assertTrue(in_build_range(player, 1, 4))
        self.assertFalse(in_build_range(player, 15, 4))

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
