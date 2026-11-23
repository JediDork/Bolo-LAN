"""Bolo-LAN authoritative UDP game server."""
import json
import math
import random
import select
import socket
import time

from shared import (COLORS, PORT, SPAWNS, TANK_RADIUS, TICK_RATE, WORLD_H,
                    WORLD_W, WALL_SECTIONS, WALL_MAX_HP, clamp, overlaps_wall, wall_at,
                    wrap_x, shortest_dx, wrapped_distance, nearest_x)
from terrain import (BASE_SITES, PILLBOX_SITES, TERRAIN_SPEED, terrain_at,
                     water_at, initial_wall_hp, RIVER_TILES, BRIDGE_TILES, ROAD_TILES,
                     LAKE_TILES, FOREST_TILES, tile_at)
from shared import GRID_SIZE, tile_to_world
from construction import (BUILD_RANGE, BUILD_COOLDOWN, BUILD_COSTS,
                          START_MATERIAL, MAX_MATERIAL, MATERIAL_REFILL,
                          valid_tile, in_build_range, blocked_build_terrain,
                          near_flag, nearby_forest)

MOVE_SPEED = 95.0
REVERSE_SPEED = 55.0
TURN_SPEED = 2.9
ACCELERATION = 115.0        # World units per second squared
BRAKE_ACCELERATION = 220.0  # Counter-throttle response
ROLLING_DRAG = 80.0        # Natural coasting resistance
TURN_ACCELERATION = 7.5
TURN_DRAG = 10.0
CAPTURE_TIME = 2.5
BASE_RADIUS = 54
PILLBOX_RANGE = 355  # Fire only once inside the visible vertical camera half-height
PILLBOX_DETECTION_RANGE = 465  # Wider warning/rotation radius
PILLBOX_TURN_SPEED = 1.7  # Radians per second, barrel traverses visibly
PILLBOX_AIM_TOLERANCE = 0.13
FOREST_PENETRATION_TILES = 2
TURRET_SPEED = 2.0  # radians/second; 180 degrees takes ~1.57 seconds
SHELL_SPEED = 680.0
SHELL_LIFE = 1.6
RELOAD = 1.25
RELOAD_SOUND_AT = 0.35  # Mechanical breech closes shortly before firing is available
SPAWN_SAFE_RADIUS = 550
SPAWN_PLAYER_DISTANCE = 450
SPAWN_GRACE = 3.0
CLIENT_TIMEOUT = 8.0
MAX_PLAYERS = 16


class GameServer:
    def __init__(self, port, dev_token=None):
        # Developer controls require a per-host unpredictable secret. No
        # client can grant itself access by simply knowing a keyboard shortcut.
        self.dev_token = dev_token
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Require a unique port owner on each machine to prevent two hosts.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.sock.bind(("", port))
        self.sock.setblocking(False)
        self.players = {}
        self.addresses = {}
        self.bullets = []
        self.bases = [{"id": i, "x": float(x), "y": float(y),
                       "owner": 0, "capturing": 0, "progress": 0.0}
                      for i, (x, y) in enumerate(BASE_SITES)]
        self.pillboxes = [{"id": i, "x": float(x), "y": float(y),
                           "hp": 100, "cooldown": 0.7, "owner": 0,
                           "angle": 0.0, "tracking": False,
                           "retaliation_target": 0, "retaliation_timer": 0.0}
                          for i, (x, y) in enumerate(PILLBOX_SITES)]
        self.wall_hp = initial_wall_hp()
        self.wall_tile_index = {(wx // GRID_SIZE, wy // GRID_SIZE): index
                                for index, (wx, wy, _, _) in enumerate(WALL_SECTIONS)}
        self.built_walls = {}  # (tile_x, tile_y) -> {hp, owner}
        self.built_bridges = set()
        self.built_roads = {}  # (tx, ty) -> builder player id
        self.bridge_owners = {}
        self.next_id = 1
        self.spawn_rng = random.Random(20261123)
        self.tick = 0
        self.events = []
        self.next_event = 1
        print(f"Bolo-LAN server listening on UDP {port} (Ctrl+C to stop)")

    def event(self, kind, x, y, **extra):
        entry = {"id": self.next_event, "type": kind, "x": round(x, 1),
                 "y": round(y, 1), "tick": self.tick}
        entry.update(extra)
        self.next_event += 1
        self.events.append(entry)
        self.events = self.events[-48:]

    def transmit(self, address, message):
        try:
            self.sock.sendto(json.dumps(message, separators=(",", ":")).encode(), address)
        except OSError:
            pass

    def spawn_clearance(self, x, y, player_id):
        """Minimum distance from another tank or live hostile pillbox."""
        distance = WORLD_W
        for other in self.players.values():
            if other["id"] != player_id and other.get("respawn", 0) <= 0:
                distance = min(distance, wrapped_distance(
                    x, y, other["x"], other["y"]))
        for box in self.pillboxes:
            if box["hp"] > 0 and box["owner"] != player_id:
                distance = min(distance, wrapped_distance(
                    x, y, box["x"], box["y"]))
        return distance

    def is_safe_spawn(self, x, y, player_id, strict=True):
        if not TANK_RADIUS + 25 <= y <= WORLD_H - TANK_RADIUS - 25:
            return False
        if self.blocked(x, y):
            return False
        clearance = self.spawn_clearance(x, y, player_id)
        if strict and clearance < SPAWN_SAFE_RADIUS:
            return False
        for other in self.players.values():
            if other["id"] != player_id and other.get("respawn", 0) <= 0:
                if wrapped_distance(x, y, other["x"], other["y"]) < SPAWN_PLAYER_DISTANCE:
                    return False
        return True

    def choose_spawn(self, player):
        """Respawn on your own claimed flag; new/unlanded players use neutral.

        Claimed territory takes precedence over expansion, including when all
        flags are owned. A player without any flags may start on an unclaimed
        objective, or on safe random ground when none are available.
        """
        player_id = player["id"]
        owned = [base for base in self.bases if base["owner"] == player_id]
        self.spawn_rng.shuffle(owned)
        if owned:
            for base in owned:
                if self.is_safe_spawn(base["x"], base["y"], player_id,
                                      strict=False):
                    return base["x"], base["y"], "owned_flag"
            # Keep a respawning player inside their OWN territory even if
            # the flag centre is occupied. A safe nearby offset is preferable
            # to stacking tanks on the same tile.
            for base in owned:
                for dx, dy in ((50, 0), (-50, 0), (0, 50), (0, -50),
                               (38, 38), (-38, 38), (38, -38), (-38, -38)):
                    x, y = wrap_x(base["x"] + dx), base["y"] + dy
                    # A contested claim may have players nearby. Require
                    # physical separation rather than the 450-unit
                    # open-world safety radius: we MUST stay on our flag.
                    if (not self.blocked(x, y)
                            and TANK_RADIUS + 25 <= y <= WORLD_H - TANK_RADIUS - 25
                            and all(other["id"] == player_id
                                    or other.get("respawn", 0) > 0
                                    or wrapped_distance(x, y, other["x"], other["y"])
                                    >= 2 * TANK_RADIUS + 10
                                    for other in self.players.values())):
                        return x, y, "owned_flag"
            # In a fully contested base a guaranteed respawn on owned land
            # is still preferable to spawning at a neutral/enemy objective.
            # Existing spawn grace protects the tank briefly.
            base = owned[0]
            return base["x"], base["y"], "owned_flag"

        neutral = [base for base in self.bases if base["owner"] == 0]
        self.spawn_rng.shuffle(neutral)
        for base in neutral:
            if self.is_safe_spawn(base["x"], base["y"], player_id, strict=False):
                return base["x"], base["y"], "flag"
        # No free usable flag: try many independent locations, excluding
        # forest, water, river, walls and the polar edges.
        best = None
        for _ in range(850):
            x = self.spawn_rng.randrange(GRID_SIZE, WORLD_W - GRID_SIZE, GRID_SIZE) + GRID_SIZE / 2
            y = self.spawn_rng.randrange(GRID_SIZE, WORLD_H - GRID_SIZE, GRID_SIZE) + GRID_SIZE / 2
            if terrain_at(x, y) not in ("grass", "road"):
                continue
            if not self.is_safe_spawn(x, y, player_id, strict=False):
                continue
            clearance = self.spawn_clearance(x, y, player_id)
            if clearance >= SPAWN_SAFE_RADIUS:
                return x, y, "safe"
            if best is None or clearance > best[0]:
                best = (clearance, x, y)
        if best is not None:
            return best[1], best[2], "fallback"
        # Emergency fallback: retain the original known spawn sites; the
        # initial spawn grace prevents immediate camping in difficult maps.
        for x, y in SPAWNS:
            if self.is_safe_spawn(x, y, player_id, strict=False):
                return x, y, "fallback"
        return float(SPAWNS[0][0]), float(SPAWNS[0][1]), "fallback"

    def spawn(self, player):
        x, y, spawn_kind = self.choose_spawn(player)
        angle = self.spawn_rng.random() * math.tau
        player.update(x=float(x), y=float(y),
                      angle=angle, turret=angle, hp=100,
                      ammo=24, speed=0.0, angular_speed=0.0,
                      reload=0.0, reload_sound_pending=False,
                      respawn=0.0, spawn_grace=SPAWN_GRACE,
                      spawn_kind=spawn_kind)

    def handle(self, data, address):
        if len(data) > 1024:
            return
        try:
            message = json.loads(data)
            if not isinstance(message, dict):
                return
        except (ValueError, UnicodeDecodeError):
            return
        kind = message.get("type")
        if kind == "discover":
            self.transmit(address, {"type": "offer", "name": "Bolo-LAN",
                                    "players": len(self.players)})
            return
        if kind == "join":
            if address in self.addresses:
                player = self.players[self.addresses[address]]
            else:
                if len(self.players) >= MAX_PLAYERS:
                    self.transmit(address, {"type": "error", "message": "Server full"})
                    return
                player_id = self.next_id
                self.next_id += 1
                player = {"id": player_id, "name": str(message.get("name", "Tank"))[:16],
                          "color": COLORS[(player_id - 1) % len(COLORS)],
                          "input": {}, "last": time.monotonic(), "score": 0,
                          "god_mode": False, "material": START_MATERIAL,
                          "build_timer": 0.0}
                self.spawn(player)
                self.players[player_id] = player
                self.addresses[address] = player_id
                print(f"Player {player_id} joined from {address}")
            player["last"] = time.monotonic()
            self.transmit(address, {"type": "welcome", "id": player["id"],
                                    "width": WORLD_W, "height": WORLD_H})
            return
        player_id = self.addresses.get(address)
        if player_id is None:
            return
        player = self.players[player_id]
        player["last"] = time.monotonic()
        if kind == "leave":
            self.remove(player_id)
        elif kind == "god_mode":
            # Developer-only: regular LAN players cannot activate god mode
            # even if they manually send the packet or modify their client.
            if (not self.dev_token
                    or message.get("dev_token") != self.dev_token):
                return
            player["god_mode"] = not player["god_mode"]
            if player["god_mode"]:
                player["hp"] = 100
                player["respawn"] = 0.0
            self.transmit(address, {"type": "god_mode",
                                    "enabled": player["god_mode"]})
        elif kind == "build":
            kind_name = message.get("part")
            tx, ty = message.get("tx"), message.get("ty")
            self.build(player, kind_name, tx, ty, address)
        elif kind == "input":
            # Only input intent is accepted. Never trust client positions/hit reports.
            def axis(key):
                value = message.get(key, 0)
                return int(clamp(value, -1, 1)) if isinstance(value, (int, float)) else 0
            angle = message.get("aim", player["turret"])
            if not isinstance(angle, (int, float)) or not math.isfinite(angle):
                angle = player["turret"]
            player["input"] = {"move": axis("move"), "turn": axis("turn"),
                               "aim": float(angle) % (2 * math.pi),
                               "fire": message.get("fire") is True}

    def remove(self, player_id):
        self.players.pop(player_id, None)
        for addr, pid in list(self.addresses.items()):
            if pid == player_id:
                self.addresses.pop(addr, None)
        print(f"Player {player_id} disconnected")

    def step(self, dt):
        now = time.monotonic()
        for player_id, player in list(self.players.items()):
            if now - player["last"] > CLIENT_TIMEOUT:
                self.remove(player_id)
                continue
            if player["respawn"] > 0:
                player["respawn"] -= dt
                if player["respawn"] <= 0:
                    self.spawn(player)
                continue
            player["spawn_grace"] = max(0.0,
                                         player.get("spawn_grace", 0.0) - dt)
            for resource in ("ammo", "material"):
                timer = resource + "_sound_timer"
                player[timer] = max(0.0, player.get(timer, 0.0) - dt)
            command = player["input"]
            # Realistic tracked-tank drive: acceleration, braking, coasting,
            # and turn inertia are simulated ONLY on the authoritative host.
            throttle = command.get("move", 0)
            turning = command.get("turn", 0)
            ground = terrain_at(player["x"], player["y"])
            tile_under_tank = tile_at(player["x"], player["y"])
            if tile_under_tank in self.built_bridges:
                ground = "bridge"
            elif tile_under_tank in self.built_roads:
                ground = "road"
            multiplier = TERRAIN_SPEED[ground]
            target_speed = (MOVE_SPEED if throttle > 0 else REVERSE_SPEED) * multiplier * throttle
            speed = player["speed"]
            # Fording a river imposes heavy water drag immediately, not just
            # a lower eventual top speed. Otherwise a fast tank could coast
            # across a short ford before slowing.
            if ground == "river" and abs(speed) > MOVE_SPEED * multiplier:
                speed += clamp(math.copysign(MOVE_SPEED * multiplier, speed) - speed,
                               -400.0 * dt, 400.0 * dt)
                player["speed"] = speed
            if throttle == 0:
                change = ROLLING_DRAG * dt
            else:
                change = (BRAKE_ACCELERATION if speed * throttle < 0 else ACCELERATION) * dt
            player["speed"] += clamp(target_speed - speed, -change, change)
            # Turning is slightly less responsive at maximum speed.
            turn_limit = TURN_SPEED * (0.76 if abs(player["speed"]) > 105 else 1.0)
            target_turn = turning * turn_limit * (-1 if throttle < 0 else 1)
            step_turn = (TURN_ACCELERATION if turning else TURN_DRAG) * dt
            player["angular_speed"] += clamp(target_turn - player["angular_speed"],
                                              -step_turn, step_turn)
            player["angle"] = (player["angle"] + player["angular_speed"] * dt) % (2 * math.pi)
            desired = command.get("aim", player["turret"])
            difference = (desired - player["turret"] + math.pi) % (2 * math.pi) - math.pi
            player["turret"] = (player["turret"] +
                                clamp(difference, -TURRET_SPEED * dt, TURRET_SPEED * dt)) % (2 * math.pi)
            dx = math.cos(player["angle"]) * player["speed"] * dt
            dy = math.sin(player["angle"]) * player["speed"] * dt
            nx = wrap_x(player["x"] + dx)
            ny = clamp(player["y"] + dy, TANK_RADIUS, WORLD_H - TANK_RADIUS)
            if not self.blocked(nx, player["y"]):
                player["x"] = wrap_x(nx)
            else:
                player["speed"] = 0.0
            if not self.blocked(player["x"], ny):
                player["y"] = ny
            else:
                player["speed"] = 0.0
            player["build_timer"] = max(0.0, player["build_timer"] - dt)
            player["reload"] = max(0.0, player["reload"] - dt)
            if (player.get("reload_sound_pending") and
                    player["reload"] <= RELOAD_SOUND_AT):
                self.event("reload", player["x"], player["y"],
                           recipient=player_id)
                player["reload_sound_pending"] = False
            if command.get("fire") and player["reload"] <= 0 and player["ammo"] >= 1:
                angle = player["turret"]
                self.alert_pillboxes(player, angle)
                self.bullets.append({"x": wrap_x(player["x"] + math.cos(angle) * 29),
                                     "y": player["y"] + math.sin(angle) * 29,
                                     "vx": math.cos(angle) * SHELL_SPEED,
                                     "vy": math.sin(angle) * SHELL_SPEED,
                                     "life": SHELL_LIFE, "owner": player_id})
                self.event("fire", wrap_x(player["x"] + math.cos(angle) * 34),
                           player["y"] + math.sin(angle) * 34, angle=angle)
                player["reload"] = RELOAD
                player["ammo"] -= 1
                player["reload_sound_pending"] = player["ammo"] >= 1
        self.update_bases(dt)
        self.update_pillboxes(dt)
        remaining = []
        for bullet in self.bullets:
            old_x, old_y = bullet["x"], bullet["y"]
            bullet["x"] = wrap_x(bullet["x"] + bullet["vx"] * dt)
            bullet["y"] += bullet["vy"] * dt
            bullet["life"] -= dt
            if bullet["life"] <= 0 or not 0 <= bullet["y"] <= WORLD_H:
                continue
            # Swept obstruction checks run in *travel order*, so a nearer
            # wall always blocks before deeper vegetation can absorb the shell.
            end_x = old_x + shortest_dx(old_x, bullet["x"])
            obstruction = self.shell_obstruction(bullet, old_x, old_y,
                                                  end_x, bullet["y"])
            if obstruction is not None:
                kind, value, hit_x, hit_y = obstruction
                if kind == "wall":
                    self.wall_hp[value] -= 1
                    self.event("impact", wrap_x(hit_x), hit_y)
                    if self.wall_hp[value] == 0:
                        wx, wy, ww, wh = WALL_SECTIONS[value]
                        self.event("wall_break", wx + ww / 2, wy + wh / 2)
                elif kind == "built":
                    wall = self.built_walls[value]
                    wall["hp"] -= 1
                    self.event("impact", wrap_x(hit_x), hit_y)
                    if wall["hp"] <= 0:
                        del self.built_walls[value]
                        wx, wy = tile_to_world(*value)
                        self.event("wall_break", wx, wy)
                else:
                    self.event("impact", hit_x, hit_y)
                continue
            hit = False
            if bullet["owner"] > 0:
                for box in self.pillboxes:
                    if box["hp"] <= 0:
                        continue
                    dx = shortest_dx(old_x, bullet["x"])
                    dy = bullet["y"] - old_y
                    t = clamp((shortest_dx(old_x, box["x"]) * dx + (box["y"] - old_y) * dy)
                              / max(0.0001, dx * dx + dy * dy), 0, 1)
                    if ((shortest_dx(box["x"], wrap_x(old_x + t * dx))) ** 2 +
                            (old_y + t * dy - box["y"]) ** 2) <= 23 ** 2:
                        box["hp"] = max(0, box["hp"] - 25)
                        self.event("hit", box["x"], box["y"])
                        if box["hp"] == 0:
                            self.event("wall_break", box["x"], box["y"])
                        hit = True
                        break
            if hit:
                continue
            for player in self.players.values():
                if player["id"] == bullet["owner"] or player["respawn"] > 0:
                    continue
                # Swept segment-circle closest point.
                dx, dy = shortest_dx(old_x, bullet["x"]), bullet["y"] - old_y
                length2 = dx * dx + dy * dy
                t = clamp((shortest_dx(old_x, player["x"]) * dx + (player["y"] - old_y) * dy)
                          / max(length2, 0.0001), 0, 1)
                dist2 = shortest_dx(player["x"], wrap_x(old_x + t * dx)) ** 2 + (old_y + t * dy - player["y"]) ** 2
                if dist2 <= (TANK_RADIUS + 4) ** 2:
                    self.event("hit", player["x"], player["y"])
                    if (not player["god_mode"] and
                            player.get("spawn_grace", 0.0) <= 0):
                        player["hp"] -= bullet.get("damage", 34)
                    if player["hp"] <= 0:
                        player["hp"] = 0
                        player["respawn"] = 2.3
                        self.event("destroy", player["x"], player["y"])
                        attacker = self.players.get(bullet["owner"])
                        if attacker:
                            attacker["score"] += 1
                    hit = True
                    break
            if not hit:
                remaining.append(bullet)
        self.bullets = remaining

    @staticmethod
    def sample_segment(x0, y0, x1, y1, spacing=4.0):
        # Dense, deterministic sweep avoids tunnelling through narrow tiles.
        length = math.hypot(x1 - x0, y1 - y0)
        count = max(1, math.ceil(length / spacing))
        for step in range(1, count + 1):
            fraction = step / count
            yield (x0 + (x1 - x0) * fraction,
                   y0 + (y1 - y0) * fraction)

    def wall_obstruction_at(self, x, y, radius=3):
        # Indexed grid lookup keeps frequent bullet and pillbox raycasts
        # inexpensive on the larger map (avoids scanning all wall sections).
        tx, ty = tile_at(x, y)
        for ix in (tx - 1, tx, tx + 1):
            for iy in (ty - 1, ty, ty + 1):
                index = self.wall_tile_index.get((ix % (WORLD_W // GRID_SIZE), iy))
                if index is not None and self.wall_hp[index] > 0:
                    left, top = ix * GRID_SIZE, iy * GRID_SIZE
                    near_x = nearest_x(wrap_x(x), left + GRID_SIZE / 2)
                    px = clamp(near_x, left, left + GRID_SIZE)
                    py = clamp(y, top, top + GRID_SIZE)
                    if (near_x - px) ** 2 + (y - py) ** 2 < radius ** 2:
                        return "wall", index
        if (tx, ty) in self.built_walls:
            return "built", (tx, ty)
        return None

    def alert_pillboxes(self, player, angle):
        """An aimed shot provokes a tracking turret outside firing range.

        A pillbox still cannot shoot through obstructing walls or heavy forest.
        Merely being seen by a turret does not cause it to fire at long range.
        """
        for box in self.pillboxes:
            if box["hp"] <= 0 or box["owner"] == player["id"]:
                continue
            dx, dy = shortest_dx(player["x"], box["x"]), box["y"] - player["y"]
            distance = math.hypot(dx, dy)
            if not PILLBOX_RANGE <= distance < PILLBOX_DETECTION_RANGE:
                continue
            direction = math.atan2(dy, dx)
            deviation = (direction - angle + math.pi) % (2 * math.pi) - math.pi
            if abs(deviation) > 0.24:
                continue
            if self.can_see(box["x"], box["y"], player["x"], player["y"]):
                box["retaliation_target"] = player["id"]
                box["retaliation_timer"] = 6.0

    def shell_obstruction(self, bullet, x0, y0, x1, y1):
        # A shell can penetrate up to two *distinct* forest cells during its
        # entire lifetime. Adjacent samples in the same tile count once.
        previous = bullet.get("forest_last_tile")
        depth = bullet.get("forest_depth", 0)
        for x, y in self.sample_segment(x0, y0, x1, y1):
            obstruction = self.wall_obstruction_at(wrap_x(x), y)
            if obstruction:
                return obstruction[0], obstruction[1], x, y
            tile = tile_at(x, y)
            if tile in FOREST_TILES and tile != previous:
                depth += 1
                if depth > FOREST_PENETRATION_TILES:
                    return "forest", tile, x, y
            previous = tile
        bullet["forest_last_tile"] = previous
        bullet["forest_depth"] = depth
        return None

    def can_see(self, x0, y0, x1, y1):
        """Solid masonry and more than two forest cells break turret LOS."""
        x1 = x0 + shortest_dx(x0, x1)
        previous = None
        depth = 0
        for x, y in self.sample_segment(x0, y0, x1, y1):
            if self.wall_obstruction_at(wrap_x(x), y):
                return False
            tile = tile_at(x, y)
            if tile in FOREST_TILES and tile != previous:
                depth += 1
                if depth > FOREST_PENETRATION_TILES:
                    return False
            previous = tile
        return True

    def built_wall_hit(self, x0, y0, x1, y1):
        x1 = x0 + shortest_dx(x0, x1)
        # Same swept collision granularity as pre-existing walls.
        distance = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, math.ceil(distance / 5))
        for step in range(1, steps + 1):
            fraction = step / steps
            x, y = x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction
            for tile in self.built_walls:
                left, top = tile[0] * GRID_SIZE, tile[1] * GRID_SIZE
                px = clamp(x, left, left + GRID_SIZE)
                py = clamp(y, top, top + GRID_SIZE)
                if (shortest_dx(x, px)) ** 2 + (y - py) ** 2 < 9:
                    return tile
        return None

    def build(self, player, part, tx, ty, address=None):
        def respond(ok, reason):
            if address is not None:
                self.transmit(address, {"type": "build_result", "ok": ok,
                                        "message": reason})
            return ok
        if part not in BUILD_COSTS or not valid_tile(tx, ty):
            return respond(False, "INVALID BUILD REQUEST")
        if player["respawn"] > 0 or player["build_timer"] > 0:
            return respond(False, "BUILDER NOT READY")
        if not in_build_range(player, tx, ty):
            return respond(False, "MOVE CLOSER TO BUILD")
        if player["material"] + 1e-6 < BUILD_COSTS[part]:
            return respond(False, "NOT ENOUGH MATERIAL")
        tile = (tx, ty)
        x, y = tile_to_world(tx, ty)
        wall_indices = [i for i, (wx, wy, _, _) in enumerate(WALL_SECTIONS)
                        if wx == tx * GRID_SIZE and wy == ty * GRID_SIZE]
        original_wall = next((i for i in wall_indices if self.wall_hp[i] > 0), None)
        built_wall = self.built_walls.get(tile)
        box = next((b for b in self.pillboxes if b["hp"] > 0
                    and shortest_dx(x, b["x"]) ** 2 + (b["y"] - y) ** 2 < 25 ** 2), None)
        player_occupies = any(p["respawn"] <= 0
                             and abs(shortest_dx(x, p["x"])) < 40 and abs(p["y"] - y) < 40
                             for p in self.players.values())
        if part in ("wall", "pillbox"):
            if (blocked_build_terrain(tile, part) or nearby_forest(tile)
                    or near_flag(tile) or original_wall is not None or built_wall
                    or box or player_occupies or tile in self.built_bridges
                    or tile in BRIDGE_TILES or tile in self.built_roads):
                return respond(False, "TILE OCCUPIED OR UNSUITABLE")
            if part == "wall":
                self.built_walls[tile] = {"hp": WALL_MAX_HP, "owner": player["id"]}
            else:
                self.pillboxes.append({"id": len(self.pillboxes), "x": float(x),
                                       "y": float(y), "hp": 100, "cooldown": 0.8,
                                       "owner": player["id"], "angle": 0.0,
                                       "tracking": False,
                                       "retaliation_target": 0,
                                       "retaliation_timer": 0.0})
        elif part == "road":
            if (blocked_build_terrain(tile, part) or tile in ROAD_TILES
                    or tile in BRIDGE_TILES or tile in self.built_roads
                    or tile in self.built_bridges or near_flag(tile)
                    or original_wall is not None or built_wall is not None
                    or box is not None):
                return respond(False, "ROAD REQUIRES FREE DRY TERRAIN")
            self.built_roads[tile] = player["id"]
        elif part == "bridge":
            if tile not in RIVER_TILES or tile in BRIDGE_TILES or tile in self.built_bridges:
                return respond(False, "BRIDGES REQUIRE OPEN RIVER")
            # Bridges occupy a river tile and cannot be placed under a tank.
            if player_occupies or original_wall is not None or built_wall or box:
                return respond(False, "CROSSING BLOCKED")
            self.built_bridges.add(tile)
            self.bridge_owners[tile] = player["id"]
        elif part == "repair":
            if original_wall is not None and self.wall_hp[original_wall] < WALL_MAX_HP:
                self.wall_hp[original_wall] = min(WALL_MAX_HP, self.wall_hp[original_wall] + 1)
            elif (built_wall is not None and built_wall["owner"] == player["id"]
                  and built_wall["hp"] < WALL_MAX_HP):
                built_wall["hp"] += 1
            elif (box is not None and box["owner"] == player["id"]
                  and box["hp"] < 100):
                box["hp"] = min(100, box["hp"] + 25)
            else:
                return respond(False, "NOTHING DAMAGED HERE")
        elif part == "remove":
            if built_wall is not None and built_wall["owner"] == player["id"]:
                del self.built_walls[tile]
            elif tile in self.built_bridges and self.bridge_owners.get(tile) == player["id"]:
                self.built_bridges.remove(tile)
                self.bridge_owners.pop(tile, None)
            elif tile in self.built_roads and self.built_roads[tile] == player["id"]:
                del self.built_roads[tile]
            elif box is not None and box["owner"] == player["id"]:
                box["hp"] = 0
            else:
                return respond(False, "NO OWNED BUILDING HERE")
        player["material"] -= BUILD_COSTS[part]
        player["build_timer"] = BUILD_COOLDOWN
        self.event("build", x, y, part=part, owner=player["id"])
        return respond(True, part.upper() + " COMPLETE")

    def blocked(self, x, y):
        if (overlaps_wall(wrap_x(x), y, TANK_RADIUS, self.wall_hp)
                or water_at(x, y, TANK_RADIUS)):
            return True
        for (tx, ty), wall in self.built_walls.items():
            left, top = tx * GRID_SIZE, ty * GRID_SIZE
            px, py = clamp(x, left, left + GRID_SIZE), clamp(y, top, top + GRID_SIZE)
            if shortest_dx(px, x) ** 2 + (y - py) ** 2 < TANK_RADIUS ** 2:
                return True
        return any(box["hp"] > 0 and
                   shortest_dx(x, box["x"]) ** 2 + (box["y"] - y) ** 2 < (TANK_RADIUS + 22) ** 2
                   for box in self.pillboxes)

    def refill_sound(self, player, resource, before, after, maximum):
        """Report local resupply without playing a sound on every tick."""
        if after <= before + 1e-7:
            return
        if after >= maximum - 1e-7 and before < maximum - 1e-7:
            self.event(resource + "_full", player["x"], player["y"],
                       recipient=player["id"])
        else:
            timer = resource + "_sound_timer"
            if player.get(timer, 0.0) <= 0.0:
                self.event(resource + "_added", player["x"], player["y"],
                           recipient=player["id"])
                player[timer] = 0.70

    def update_bases(self, dt):
        for base in self.bases:
            nearby = [p for p in self.players.values()
                      if p["respawn"] <= 0 and
                      wrapped_distance(p["x"], p["y"], base["x"], base["y"]) <= BASE_RADIUS]
            # No captures when contested, and no instant ownership flips.
            if len(nearby) != 1:
                base["capturing"] = 0
                base["progress"] = 0.0
                continue
            player = nearby[0]
            pid = player["id"]
            if base["owner"] == pid:
                # One life point each ~0.13 seconds and one shell each 0.5 s.
                player["hp"] = min(100, player["hp"] + 7.5 * dt)
                old_ammo, old_material = player["ammo"], player["material"]
                player["ammo"] = min(24, old_ammo + 2.0 * dt)
                player["material"] = min(MAX_MATERIAL,
                                         old_material + MATERIAL_REFILL * dt)
                self.refill_sound(player, "ammo", old_ammo, player["ammo"], 24)
                self.refill_sound(player, "material", old_material,
                                  player["material"], MAX_MATERIAL)
                continue
            if base["capturing"] != pid:
                base["capturing"] = pid
                base["progress"] = 0.0
            base["progress"] += dt
            if base["progress"] >= CAPTURE_TIME:
                previous_owner = base["owner"]
                base["owner"] = pid
                base["capturing"] = 0
                base["progress"] = 0.0
                self.event("capture", base["x"], base["y"], owner=pid)
                self.event("flag_taken", base["x"], base["y"], recipient=pid)
                if previous_owner and previous_owner != pid:
                    self.event("flag_lost", base["x"], base["y"],
                               recipient=previous_owner)

    def update_pillboxes(self, dt):
        for box in self.pillboxes:
            if box["hp"] <= 0:
                continue
            box["cooldown"] = max(0.0, box["cooldown"] - dt)
            box["retaliation_timer"] = max(
                0.0, box.get("retaliation_timer", 0.0) - dt)
            visible = []
            for player in self.players.values():
                if (player["respawn"] > 0 or player["id"] == box["owner"]
                        or player.get("spawn_grace", 0.0) > 0):
                    continue
                distance = wrapped_distance(player["x"], player["y"],
                                            box["x"], box["y"])
                if (distance < PILLBOX_DETECTION_RANGE and
                        self.can_see(box["x"], box["y"],
                                     player["x"], player["y"])):
                    visible.append((distance, player))
            box["tracking"] = bool(visible)
            if not visible:
                continue
            # Once provoked, prefer the aggressor while they remain visible.
            retaliation = box.get("retaliation_target") if box["retaliation_timer"] > 0 else 0
            distance, target = min(
                visible, key=lambda match:
                (0 if match[1]["id"] == retaliation else 1, match[0]))
            desired = math.atan2(target["y"] - box["y"],
                                 shortest_dx(box["x"], target["x"]))
            current = box.get("angle", 0.0)
            difference = (desired - current + math.pi) % (2 * math.pi) - math.pi
            box["angle"] = (current + clamp(difference,
                                             -PILLBOX_TURN_SPEED * dt,
                                             PILLBOX_TURN_SPEED * dt)) % (2 * math.pi)
            # Rotate visibly throughout the outer detection area, but never
            # fire until the target is nearer AND the barrel is aligned.
            remaining = (desired - box["angle"] + math.pi) % (2 * math.pi) - math.pi
            provoked = (box["retaliation_timer"] > 0 and
                        target["id"] == box.get("retaliation_target"))
            if ((distance >= PILLBOX_RANGE and not provoked)
                    or box["cooldown"] > 0
                    or abs(remaining) > PILLBOX_AIM_TOLERANCE):
                continue
            angle = box["angle"]
            self.bullets.append({"x": wrap_x(box["x"] + math.cos(angle) * 24),
                                 "y": box["y"] + math.sin(angle) * 24,
                                 "vx": math.cos(angle) * SHELL_SPEED,
                                 "vy": math.sin(angle) * SHELL_SPEED,
                                 "life": 1.45, "owner": -1, "damage": 18})
            self.event("fire", box["x"], box["y"], angle=angle)
            box["cooldown"] = 1.0

    def snapshot(self):
        players = [{"id": p["id"], "name": p["name"], "x": round(p["x"], 1),
                    "y": round(p["y"], 1), "a": round(p["angle"], 3),
                    "t": round(p["turret"], 3), "hp": p["hp"], "score": p["score"],
                    "dead": p["respawn"] > 0, "color": p["color"],
                    "speed": round(p["speed"], 1), "ammo": int(p["ammo"]),
                    "reload": round(p["reload"], 3), "reload_duration": RELOAD,
                    "god_mode": p["god_mode"],
                    "material": round(p["material"], 1),
                    "spawn_grace": round(p.get("spawn_grace", 0), 1)}
                   for p in self.players.values()]
        bullets = [{"x": round(b["x"], 1), "y": round(b["y"], 1)}
                   for b in self.bullets]
        message = {"type": "state", "tick": self.tick, "players": players,
                   "bullets": bullets,
                   "walls": self.wall_hp,
                   "built_walls": [{"tx": tx, "ty": ty, **info}
                                   for (tx, ty), info in self.built_walls.items()],
                   "built_bridges": [list(tile) for tile in sorted(self.built_bridges)],
                   "built_roads": [list(tile) for tile in sorted(self.built_roads)],
                   "bases": [{k: (round(v, 2) if isinstance(v, float) else v)
                              for k, v in base.items()} for base in self.bases],
                   "pillboxes": [{k: v for k, v in box.items() if k != "cooldown"}
                                 for box in self.pillboxes],
                   "events": [e for e in self.events if self.tick - e["tick"] <= 30]}
        for address in list(self.addresses):
            self.transmit(address, message)

    def run(self):
        step = 1 / TICK_RATE
        next_tick = time.monotonic()
        try:
            while True:
                timeout = clamp(next_tick - time.monotonic(), 0.0, 0.05)
                ready, _, _ = select.select([self.sock], [], [], timeout)
                if ready:
                    for _ in range(128):
                        try:
                            data, address = self.sock.recvfrom(2048)
                        except BlockingIOError:
                            break
                        self.handle(data, address)
                now = time.monotonic()
                if now >= next_tick:
                    self.step(step)
                    self.tick += 1
                    if self.tick % 2 == 0:
                        self.snapshot()
                    next_tick += step
                    if now - next_tick > 0.25:
                        next_tick = now + step
        except KeyboardInterrupt:
            print("\nServer stopped.")
        finally:
            self.sock.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    GameServer(args.port).run()
