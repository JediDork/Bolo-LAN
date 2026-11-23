"""Bolo-LAN authoritative UDP game server."""
import json
import math
import select
import socket
import time

from shared import (COLORS, PORT, SPAWNS, TANK_RADIUS, TICK_RATE, WORLD_H,
                    WORLD_W, clamp, overlaps_wall, segment_hits_wall)

MOVE_SPEED = 195.0
REVERSE_SPEED = 125.0
TURN_SPEED = 2.9
SHELL_SPEED = 680.0
SHELL_LIFE = 1.6
RELOAD = 0.42
CLIENT_TIMEOUT = 8.0
MAX_PLAYERS = 16


class GameServer:
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))
        self.sock.setblocking(False)
        self.players = {}
        self.addresses = {}
        self.bullets = []
        self.next_id = 1
        self.tick = 0
        print(f"Bolo-LAN server listening on UDP {port} (Ctrl+C to stop)")

    def transmit(self, address, message):
        try:
            self.sock.sendto(json.dumps(message, separators=(",", ":")).encode(), address)
        except OSError:
            pass

    def spawn(self, player):
        i = (player["id"] - 1) % len(SPAWNS)
        player.update(x=float(SPAWNS[i][0]), y=float(SPAWNS[i][1]),
                      angle=0.0 if i % 2 == 0 else math.pi,
                      turret=0.0, hp=100, reload=0.0, respawn=0.0)

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
            player["angle"] = (player["angle"] + command.get("turn", 0) * TURN_SPEED * dt) % (2 * math.pi)
            player["turret"] = command.get("aim", player["turret"])
            throttle = command.get("move", 0)
            speed = MOVE_SPEED if throttle > 0 else REVERSE_SPEED
            vx = math.cos(player["angle"]) * throttle * speed * dt
            vy = math.sin(player["angle"]) * throttle * speed * dt
            nx = clamp(player["x"] + vx, TANK_RADIUS, WORLD_W - TANK_RADIUS)
            ny = clamp(player["y"] + vy, TANK_RADIUS, WORLD_H - TANK_RADIUS)
            if not overlaps_wall(nx, player["y"], TANK_RADIUS):
                player["x"] = nx
            if not overlaps_wall(player["x"], ny, TANK_RADIUS):
                player["y"] = ny
            player["reload"] = max(0.0, player["reload"] - dt)
            if command.get("fire") and player["reload"] <= 0:
                angle = player["turret"]
                self.bullets.append({"x": player["x"] + math.cos(angle) * 29,
                                     "y": player["y"] + math.sin(angle) * 29,
                                     "vx": math.cos(angle) * SHELL_SPEED,
                                     "vy": math.sin(angle) * SHELL_SPEED,
                                     "life": SHELL_LIFE, "owner": player_id})
                player["reload"] = RELOAD
        remaining = []
        for bullet in self.bullets:
            old_x, old_y = bullet["x"], bullet["y"]
            bullet["x"] += bullet["vx"] * dt
            bullet["y"] += bullet["vy"] * dt
            bullet["life"] -= dt
            if (bullet["life"] <= 0 or not 0 <= bullet["x"] <= WORLD_W
                    or not 0 <= bullet["y"] <= WORLD_H
                    or segment_hits_wall(old_x, old_y, bullet["x"], bullet["y"])):
                continue
            hit = False
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
                    player["hp"] -= 34
                    if player["hp"] <= 0:
                        player["hp"] = 0
                        player["respawn"] = 2.3
                        attacker = self.players.get(bullet["owner"])
                        if attacker:
                            attacker["score"] += 1
                    hit = True
                    break
            if not hit:
                remaining.append(bullet)
        self.bullets = remaining

    def snapshot(self):
        players = [{"id": p["id"], "name": p["name"], "x": round(p["x"], 1),
                    "y": round(p["y"], 1), "a": round(p["angle"], 3),
                    "t": round(p["turret"], 3), "hp": p["hp"], "score": p["score"],
                    "dead": p["respawn"] > 0, "color": p["color"]}
                   for p in self.players.values()]
        bullets = [{"x": round(b["x"], 1), "y": round(b["y"], 1)}
                   for b in self.bullets]
        message = {"type": "state", "tick": self.tick, "players": players,
                   "bullets": bullets}
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
