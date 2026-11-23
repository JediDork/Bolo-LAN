"""Bolo-LAN authoritative UDP game server."""
import json
import math
import select
import socket
import time

from shared import (COLORS, PORT, SPAWNS, TANK_RADIUS, TICK_RATE, WORLD_H,
                    WORLD_W, WALL_SECTIONS, WALL_MAX_HP, clamp, overlaps_wall, segment_hits_wall)
from terrain import (BASE_SITES, PILLBOX_SITES, TERRAIN_SPEED, terrain_at,
                     water_at)

MOVE_SPEED = 125.0
REVERSE_SPEED = 75.0
TURN_SPEED = 2.9
ACCELERATION = 115.0        # World units per second squared
BRAKE_ACCELERATION = 220.0  # Counter-throttle response
ROLLING_DRAG = 80.0        # Natural coasting resistance
TURN_ACCELERATION = 7.5
TURN_DRAG = 10.0
CAPTURE_TIME = 2.5
BASE_RADIUS = 54
PILLBOX_RANGE = 850
TURRET_SPEED = 2.0  # radians/second; 180 degrees takes ~1.57 seconds
SHELL_SPEED = 680.0
SHELL_LIFE = 1.6
RELOAD = 0.42
CLIENT_TIMEOUT = 8.0
MAX_PLAYERS = 16


class GameServer:
    def __init__(self, port):
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
                           "hp": 100, "cooldown": 0.7, "owner": 0}
                          for i, (x, y) in enumerate(PILLBOX_SITES)]
        self.wall_hp = [WALL_MAX_HP] * len(WALL_SECTIONS)
        self.next_id = 1
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

    def spawn(self, player):
        i = (player["id"] - 1) % len(SPAWNS)
        player.update(x=float(SPAWNS[i][0]), y=float(SPAWNS[i][1]),
                      angle=0.0 if i % 2 == 0 else math.pi,
                      turret=0.0 if i % 2 == 0 else math.pi, hp=100,
                      ammo=24, speed=0.0, angular_speed=0.0,
                      reload=0.0, respawn=0.0)

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
                          "input": {}, "last": time.monotonic(), "score": 0}
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
            command = player["input"]
            # Realistic tracked-tank drive: acceleration, braking, coasting,
            # and turn inertia are simulated ONLY on the authoritative host.
            throttle = command.get("move", 0)
            turning = command.get("turn", 0)
            ground = terrain_at(player["x"], player["y"])
            multiplier = TERRAIN_SPEED[ground]
            target_speed = (MOVE_SPEED if throttle > 0 else REVERSE_SPEED) * multiplier * throttle
            speed = player["speed"]
            if throttle == 0:
                change = ROLLING_DRAG * dt
            else:
                change = (BRAKE_ACCELERATION if speed * throttle < 0 else ACCELERATION) * dt
            player["speed"] += clamp(target_speed - speed, -change, change)
            # Turning is slightly less responsive at maximum speed.
            turn_limit = TURN_SPEED * (0.76 if abs(player["speed"]) > 105 else 1.0)
            target_turn = turning * turn_limit
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
            nx = clamp(player["x"] + dx, TANK_RADIUS, WORLD_W - TANK_RADIUS)
            ny = clamp(player["y"] + dy, TANK_RADIUS, WORLD_H - TANK_RADIUS)
            if not self.blocked(nx, player["y"]):
                player["x"] = nx
            else:
                player["speed"] = 0.0
            if not self.blocked(player["x"], ny):
                player["y"] = ny
            else:
                player["speed"] = 0.0
            player["reload"] = max(0.0, player["reload"] - dt)
            if command.get("fire") and player["reload"] <= 0 and player["ammo"] >= 1:
                angle = player["turret"]
                self.bullets.append({"x": player["x"] + math.cos(angle) * 29,
                                     "y": player["y"] + math.sin(angle) * 29,
                                     "vx": math.cos(angle) * SHELL_SPEED,
                                     "vy": math.sin(angle) * SHELL_SPEED,
                                     "life": SHELL_LIFE, "owner": player_id})
                self.event("fire", player["x"] + math.cos(angle) * 34,
                           player["y"] + math.sin(angle) * 34, angle=angle)
                player["reload"] = RELOAD
                player["ammo"] -= 1
        self.update_bases(dt)
        self.update_pillboxes(dt)
        remaining = []
        for bullet in self.bullets:
            old_x, old_y = bullet["x"], bullet["y"]
            bullet["x"] += bullet["vx"] * dt
            bullet["y"] += bullet["vy"] * dt
            bullet["life"] -= dt
            if (bullet["life"] <= 0 or not 0 <= bullet["x"] <= WORLD_W
                    or not 0 <= bullet["y"] <= WORLD_H):
                continue
            section = segment_hits_wall(old_x, old_y, bullet["x"], bullet["y"],
                                        self.wall_hp)
            if section is not None:
                self.wall_hp[section] -= 1
                self.event("impact", bullet["x"], bullet["y"])
                if self.wall_hp[section] == 0:
                    wx, wy, ww, wh = WALL_SECTIONS[section]
                    self.event("wall_break", wx + ww / 2, wy + wh / 2)
                continue
            hit = False
            if bullet["owner"] > 0:
                for box in self.pillboxes:
                    if box["hp"] <= 0:
                        continue
                    dx = bullet["x"] - old_x
                    dy = bullet["y"] - old_y
                    t = clamp(((box["x"] - old_x) * dx + (box["y"] - old_y) * dy)
                              / max(0.0001, dx * dx + dy * dy), 0, 1)
                    if ((old_x + t * dx - box["x"]) ** 2 +
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
                dx, dy = bullet["x"] - old_x, bullet["y"] - old_y
                length2 = dx * dx + dy * dy
                t = clamp(((player["x"] - old_x) * dx + (player["y"] - old_y) * dy)
                          / max(length2, 0.0001), 0, 1)
                dist2 = (old_x + t * dx - player["x"]) ** 2 + (old_y + t * dy - player["y"]) ** 2
                if dist2 <= (TANK_RADIUS + 4) ** 2:
                    self.event("hit", player["x"], player["y"])
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

    def blocked(self, x, y):
        if overlaps_wall(x, y, TANK_RADIUS, self.wall_hp) or water_at(x, y, TANK_RADIUS):
            return True
        return any(box["hp"] > 0 and
                   (box["x"] - x) ** 2 + (box["y"] - y) ** 2 < (TANK_RADIUS + 22) ** 2
                   for box in self.pillboxes)

    def update_bases(self, dt):
        for base in self.bases:
            nearby = [p for p in self.players.values()
                      if p["respawn"] <= 0 and
                      math.hypot(p["x"] - base["x"], p["y"] - base["y"]) <= BASE_RADIUS]
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
                player["ammo"] = min(24, player["ammo"] + 2.0 * dt)
                continue
            if base["capturing"] != pid:
                base["capturing"] = pid
                base["progress"] = 0.0
            base["progress"] += dt
            if base["progress"] >= CAPTURE_TIME:
                base["owner"] = pid
                base["capturing"] = 0
                base["progress"] = 0.0
                self.event("capture", base["x"], base["y"], owner=pid)

    def update_pillboxes(self, dt):
        for box in self.pillboxes:
            if box["hp"] <= 0:
                continue
            box["cooldown"] = max(0.0, box["cooldown"] - dt)
            if box["cooldown"] > 0:
                continue
            candidates = [p for p in self.players.values()
                          if p["respawn"] <= 0 and p["id"] != box["owner"]
                          and math.hypot(p["x"] - box["x"], p["y"] - box["y"]) < PILLBOX_RANGE]
            if not candidates:
                continue
            target = min(candidates, key=lambda p: (p["x"] - box["x"]) ** 2 +
                                                 (p["y"] - box["y"]) ** 2)
            angle = math.atan2(target["y"] - box["y"], target["x"] - box["x"])
            self.bullets.append({"x": box["x"] + math.cos(angle) * 24,
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
                    "speed": round(p["speed"], 1), "ammo": int(p["ammo"])}
                   for p in self.players.values()]
        bullets = [{"x": round(b["x"], 1), "y": round(b["y"], 1)}
                   for b in self.bullets]
        message = {"type": "state", "tick": self.tick, "players": players,
                   "bullets": bullets,
                   "walls": self.wall_hp,
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
