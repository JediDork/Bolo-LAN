"""Pygame client for Bolo-LAN."""
import argparse
import json
import math
import os
import random
import select
import socket
import time

import pygame

from shared import PORT, WALLS, WORLD_H, WORLD_W
from effects import Effects, draw_details, draw_minimap

WIDTH, HEIGHT = 1200, 760
BG = (45, 82, 61)


def discover(port, timeout=1.4):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", 0))
    sock.setblocking(False)
    targets = [("255.255.255.255", port)]
    # Explicit loopback discovery also makes testing two clients on one PC easy.
    targets.append(("127.0.0.1", port))
    for target in targets:
        try:
            sock.sendto(b'{"type":"discover"}', target)
        except OSError:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([sock], [], [], 0.15)
        if ready:
            try:
                data, addr = sock.recvfrom(2048)
                message = json.loads(data)
                if message.get("type") == "offer":
                    sock.close()
                    return addr[0]
            except (OSError, ValueError):
                pass
    sock.close()
    return None


def send(sock, address, message):
    try:
        sock.sendto(json.dumps(message, separators=(",", ":")).encode(), address)
    except OSError:
        pass


def xy(world_x, world_y, camera):
    return int(world_x - camera[0]), int(world_y - camera[1])


def tank(surface, player, camera, font, local_id):
    if player.get("dead"):
        return
    x, y = xy(player["x"], player["y"], camera)
    color = tuple(player["color"])
    hull = float(player["a"])
    turret = float(player["t"])
    # Shadow
    pygame.draw.ellipse(surface, (24, 42, 33), (x - 23, y - 12, 48, 34))
    # Rotated rectangle tank hull
    ca, sa = math.cos(hull), math.sin(hull)
    points = []
    for forward, side in [(24, -15), (24, 15), (-22, 15), (-22, -15)]:
        points.append((int(x + ca * forward - sa * side),
                       int(y + sa * forward + ca * side)))
    pygame.draw.polygon(surface, (19, 29, 28), points)
    pygame.draw.polygon(surface, color, points, 0)
    pygame.draw.polygon(surface, (20, 32, 31), points, 2)
    # Two animated-looking tread rails, oriented with hull.
    for side in (-1, 1):
        rail = []
        for forward in (-17, 17):
            rail.append((int(x + ca * forward - sa * side * 13),
                         int(y + sa * forward + ca * side * 13)))
        pygame.draw.line(surface, (22, 36, 31), rail[0], rail[1], 6)
        for forward in (-14, -7, 0, 7, 14):
            tx = int(x + ca * forward - sa * side * 13)
            ty = int(y + sa * forward + ca * side * 13)
            pygame.draw.circle(surface, (78, 83, 70), (tx, ty), 2)
    # Independent turret and barrel
    end = (int(x + math.cos(turret) * 34), int(y + math.sin(turret) * 34))
    pygame.draw.line(surface, (23, 34, 32), (x, y), end, 11)
    pygame.draw.line(surface, (165, 176, 153), (x, y), end, 6)
    pygame.draw.circle(surface, (23, 34, 32), (x, y), 13)
    pygame.draw.circle(surface, color, (x, y), 10)
    if player["id"] == local_id:
        pygame.draw.circle(surface, (246, 244, 174), (x, y), 30, 2)
    label = font.render(f'{player["name"]}  {player["hp"]}%', True, (242, 242, 229))
    surface.blit(label, (x - label.get_width() // 2, y - 45))


def draw_ground(surface, camera):
    surface.fill(BG)
    grid = 100
    start_x = int(camera[0] // grid) * grid
    start_y = int(camera[1] // grid) * grid
    for wx in range(start_x, int(camera[0] + WIDTH) + grid, grid):
        x = int(wx - camera[0])
        pygame.draw.line(surface, (51, 91, 67), (x, 0), (x, HEIGHT), 1)
    for wy in range(start_y, int(camera[1] + HEIGHT) + grid, grid):
        y = int(wy - camera[1])
        pygame.draw.line(surface, (51, 91, 67), (0, y), (WIDTH, y), 1)
    draw_details(surface, camera, WIDTH, HEIGHT)
    for wx, wy, ww, wh in WALLS:
        rect = pygame.Rect(wx - camera[0], wy - camera[1], ww, wh)
        pygame.draw.rect(surface, (83, 83, 74), rect)
        pygame.draw.rect(surface, (127, 131, 111), rect.inflate(-8, -8))
        pygame.draw.rect(surface, (30, 46, 42), rect, 3)
    bounds = pygame.Rect(-camera[0], -camera[1], WORLD_W, WORLD_H)
    pygame.draw.rect(surface, (199, 208, 168), bounds, 5)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bolo-LAN multiplayer client")
    parser.add_argument("--host", help="Host LAN IP (auto-discover if omitted)")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--name", default=os.environ.get("USERNAME", "Tank")[:16])
    args = parser.parse_args(argv)

    host = args.host or discover(args.port)
    if not host:
        print("No LAN host found. Start server.py or specify --host HOST_IP.")
        return
    addr = (host, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", 0))
    sock.setblocking(False)
    print(f"Connecting to {addr[0]}:{addr[1]}")
    send(sock, addr, {"type": "join", "name": args.name})
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Bolo-LAN | Combat Prototype v0.2")
    font = pygame.font.SysFont("consolas", 16, bold=True)
    heading = pygame.font.SysFont("consolas", 23, bold=True)
    clock = pygame.time.Clock()
    local_id = None
    state = {"players": [], "bullets": [], "events": []}
    effects = Effects()
    visual_players = {}
    last_event_id = 0
    dust_timer = 0.0
    camera = [0.0, 0.0]
    previous_join = time.monotonic()
    previous_input = 0.0
    last_snapshot = time.monotonic()
    running = True

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
        for _ in range(96):
            try:
                data, incoming = sock.recvfrom(65535)
            except BlockingIOError:
                break
            if incoming[0] != addr[0] or incoming[1] != addr[1]:
                continue
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if message.get("type") == "welcome":
                local_id = message["id"]
            elif message.get("type") == "state":
                # Events retain IDs across snapshots, so duplicate packets never replay an explosion.
                events = message.get("events", [])
                for event in events:
                    if event["id"] > last_event_id:
                        effects.burst(event["type"], event["x"], event["y"],
                                      event.get("angle", 0))
                        last_event_id = event["id"]
                state = message
                last_snapshot = time.monotonic()
            elif message.get("type") == "error":
                print(message.get("message", "Connection rejected"))
                running = False
        now = time.monotonic()
        if local_id is None and now - previous_join > 1:
            send(sock, addr, {"type": "join", "name": args.name})
            previous_join = now
        # Presentation smoothing: no gameplay authority is moved to the client.
        blend = 1.0 - math.exp(-dt * 19.0)
        present_ids = set()
        for authoritative in state["players"]:
            pid = authoritative["id"]
            present_ids.add(pid)
            if pid not in visual_players or authoritative.get("dead"):
                visual_players[pid] = dict(authoritative)
                continue
            visual = visual_players[pid]
            delta = math.hypot(authoritative["x"] - visual["x"],
                               authoritative["y"] - visual["y"])
            if delta > 180:
                visual.update(authoritative)
                continue
            for key in ("x", "y"):
                visual[key] += (authoritative[key] - visual[key]) * blend
            for key in ("a", "t"):
                diff = (authoritative[key] - visual[key] + math.pi) % math.tau - math.pi
                visual[key] = (visual[key] + diff * blend) % math.tau
            for key in ("name", "hp", "score", "dead", "color"):
                visual[key] = authoritative[key]
        for pid in list(visual_players):
            if pid not in present_ids:
                del visual_players[pid]
        player = visual_players.get(local_id)
        if player:
            camera[0] += (player["x"] - WIDTH / 2 - camera[0]) * 0.15
            camera[1] += (player["y"] - HEIGHT / 2 - camera[1]) * 0.15
        camera[0] = max(0, min(WORLD_W - WIDTH, camera[0]))
        camera[1] = max(0, min(WORLD_H - HEIGHT, camera[1]))
        keys = pygame.key.get_pressed()
        movement = int(keys[pygame.K_w] or keys[pygame.K_UP]) - int(keys[pygame.K_s] or keys[pygame.K_DOWN])
        turn = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        mx, my = pygame.mouse.get_pos()
        aim = math.atan2(my + camera[1] - player["y"], mx + camera[0] - player["x"]) if player else 0.0
        firing = bool(pygame.mouse.get_pressed()[0] or keys[pygame.K_SPACE])
        if local_id is not None and now - previous_input > 1 / 30:
            send(sock, addr, {"type": "input", "move": movement, "turn": turn,
                              "aim": aim, "fire": firing})
            previous_input = now

        effects.update(dt)
        dust_timer -= dt
        if dust_timer <= 0:
            for moving in visual_players.values():
                if moving.get("dead"):
                    continue
                # Only emit track dust for tanks visibly changing position.
                original = next((p for p in state["players"] if p["id"] == moving["id"]), None)
                if original and math.hypot(moving["x"] - original["x"],
                                            moving["y"] - original["y"]) > 1.5:
                    a = moving["a"]
                    effects.dust(moving["x"] - math.cos(a) * 20,
                                 moving["y"] - math.sin(a) * 20)
            dust_timer = 0.08
        draw_ground(screen, camera)
        for bullet in state["bullets"]:
            bx, by = xy(bullet["x"], bullet["y"], camera)
            pygame.draw.circle(screen, (255, 170, 68), (bx, by), 6)
            pygame.draw.circle(screen, (255, 235, 164), (bx, by), 3)
        for item in visual_players.values():
            tank(screen, item, camera, font, local_id)
        effects.draw(screen, camera)
        draw_minimap(screen, list(visual_players.values()), local_id, camera, WIDTH, HEIGHT)
        pygame.draw.rect(screen, (16, 30, 29), (0, 0, WIDTH, 56))
        title = heading.render("BOLO-LAN  /  COMBAT PROTOTYPE v0.2", True, (235, 233, 208))
        screen.blit(title, (15, 8))
        info = font.render(f"HOST {host}:{args.port}  |  PLAYERS {len(state['players'])}  |  WASD MOVE  MOUSE AIM  CLICK FIRE",
                           True, (191, 208, 195))
        screen.blit(info, (16, 34))
        if player:
            health = font.render(f"ARMOUR {player['hp']:3d}%     KILLS {player['score']}", True, (252, 245, 205))
            screen.blit(health, (18, HEIGHT - 34))
        if local_id is None or now - last_snapshot > 3:
            status = "CONNECTING TO SERVER..." if local_id is None else "CONNECTION LOST"
            label = heading.render(status, True, (255, 203, 110))
            screen.blit(label, (WIDTH // 2 - label.get_width() // 2, HEIGHT // 2))
        pygame.display.flip()
    send(sock, addr, {"type": "leave"})
    sock.close()
    pygame.quit()


if __name__ == "__main__":
    main()
