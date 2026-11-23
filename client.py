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

from shared import (PORT, WALL_SECTIONS, WALL_MAX_HP, WORLD_H, WORLD_W,
                    wrap_x, shortest_dx, wrapped_distance, nearest_x)
from effects import Effects, draw_details, draw_minimap
from display import viewport, to_logical
from renderer import draw_frame, RENDER_W, RENDER_H
from terrain import initial_wall_hp
from audio import SoundBank, SAMPLE_RATE
from engine_audio import EngineAudio
from construction import BUILD_TOOLS

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
    # High contrast forward-direction chevron fixed to the HULL (not turret).
    # Its broad tip remains visible even when the turret points backwards.
    arrow = []
    for forward, side in ((25, 0), (9, -10), (13, 0), (9, 10)):
        arrow.append((int(x + ca * forward - sa * side),
                      int(y + sa * forward + ca * side)))
    pygame.draw.polygon(surface, (255, 227, 91), arrow)
    pygame.draw.polygon(surface, (35, 36, 24), arrow, 2)
    if player["id"] == local_id:
        pygame.draw.circle(surface, (246, 244, 174), (x, y), 30, 2)
    label = font.render(f'{player["name"]}  {player["hp"]}%', True, (242, 242, 229))
    surface.blit(label, (x - label.get_width() // 2, y - 45))


def draw_ground(surface, camera, wall_hp):
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
    for index, (wx, wy, ww, wh) in enumerate(WALL_SECTIONS):
        hp = wall_hp[index] if index < len(wall_hp) else WALL_MAX_HP
        if hp <= 0:
            continue
        rect = pygame.Rect(int(wx - camera[0]), int(wy - camera[1]), ww, wh)
        if not rect.colliderect(surface.get_rect()):
            continue
        damage = WALL_MAX_HP - hp
        # Increasingly dark/cracked masonry as each shell strikes.
        tones = ((121, 127, 112), (109, 110, 100),
                 (91, 88, 82), (72, 66, 62))
        pygame.draw.rect(surface, (38, 45, 41), rect)
        pygame.draw.rect(surface, tones[damage], rect.inflate(-5, -5))
        pygame.draw.rect(surface, (38, 47, 42), rect, 2)
        if damage:
            # Deterministic fracture patterns: all clients see the same cracks.
            center_x, center_y = rect.center
            crack_color = (42, 44, 43)
            for crack in range(damage * 3):
                offset = ((index * 17 + crack * 19) % 31) - 15
                cx = center_x + offset
                cy = center_y + ((index * 13 + crack * 23) % 27) - 13
                cx = max(rect.left + 4, min(rect.right - 4, cx))
                cy = max(rect.top + 4, min(rect.bottom - 4, cy))
                end_x = max(rect.left + 4, min(rect.right - 4, cx + (10 if crack % 2 else -11)))
                end_y = max(rect.top + 4, min(rect.bottom - 4, cy + (8 if crack % 3 else -9)))
                pygame.draw.line(surface, crack_color, (cx, cy),
                                 (end_x, end_y), 1 + (damage // 2))
            # Dark chipped area becomes larger with consecutive impacts.
            chip = pygame.Rect(center_x - 3 * damage, center_y - 3 * damage,
                               6 * damage, 6 * damage)
            pygame.draw.ellipse(surface, (52, 51, 48), chip)
    bounds = pygame.Rect(-camera[0], -camera[1], WORLD_W, WORLD_H)
    pygame.draw.rect(surface, (199, 208, 168), bounds, 5)


def main(argv=None, dev_token=None):
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
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    # Fullscreen uses monitor native resolution, but all gameplay is drawn into
    # the exact same logical 1200x760 viewport on every machine.
    display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    view = viewport(*display.get_size(), WIDTH, HEIGHT)
    # Render *new* detail at 2x, then filter to the monitor without zooming out.
    screen = pygame.Surface((RENDER_W, RENDER_H)).convert()
    pygame.display.set_caption("Bolo-LAN | Planet World v0.16")
    fonts = {"label": pygame.font.SysFont("consolas", 32, bold=True),
             "heading": pygame.font.SysFont("consolas", 46, bold=True)}
    audio = SoundBank()
    engine = EngineAudio(audio)
    clock = pygame.time.Clock()
    local_id = None
    state = {"players": [], "bullets": [], "events": [],
             "walls": initial_wall_hp(),
             "bases": [], "pillboxes": [], "built_walls": [], "built_bridges": [],
             "built_roads": []}
    effects = Effects()
    visual_players = {}
    last_event_id = 0
    dust_timer = 0.0
    camera = [0.0, 0.0]
    previous_join = time.monotonic()
    previous_input = 0.0
    last_snapshot = time.monotonic()
    running = True
    build_mode = False
    build_part = "wall"
    build_message = ""
    build_message_time = 0.0

    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                audio.toggle_mute()
            elif (event.type == pygame.KEYDOWN
                  and event.key == pygame.K_g
                  and (event.mod & pygame.KMOD_CTRL)
                  and (event.mod & pygame.KMOD_SHIFT)
                  and not getattr(event, "repeat", False)):
                # Host-only hidden testing shortcut. Server separately
                # authenticates the secret, never just the key combination.
                if local_id is not None and dev_token:
                    send(sock, addr, {"type": "god_mode",
                                      "dev_token": dev_token})
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_b and not getattr(event, "repeat", False):
                build_mode = not build_mode
                build_message = ""
            elif event.type == pygame.KEYDOWN and build_mode:
                chosen = BUILD_TOOLS.get(pygame.key.name(event.key))
                if chosen:
                    build_part = chosen
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and build_mode and local_id is not None:
                mx, my = to_logical(event.pos, view, WIDTH, HEIGHT)
                tx = int(wrap_x(mx + camera[0]) // 50)
                ty = int((my + camera[1]) // 50)
                send(sock, addr, {"type": "build", "part": build_part, "tx": tx, "ty": ty})
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
                    if event["id"] <= last_event_id:
                        continue
                    # Targeted supply and flag notifications belong only to
                    # their owning player, not the entire LAN.
                    last_event_id = event["id"]
                    recipient = event.get("recipient")
                    if recipient is not None and recipient != local_id:
                        continue
                    kind = event["type"]
                    if kind not in ("material_added", "material_full",
                                    "ammo_added", "ammo_full", "reload",
                                    "flag_taken", "flag_lost"):
                        effects.burst(kind, event["x"], event["y"],
                                      event.get("angle", 0))
                    if local_id is not None:
                        if recipient is not None:
                            audio.play(kind, 0.0)
                        else:
                            listener = next((p for p in message.get("players", [])
                                             if p["id"] == local_id), None)
                            distance = (wrapped_distance(event["x"], event["y"],
                                                         listener["x"], listener["y"])
                                        if listener else 0.0)
                            audio.play(kind, distance)
                state = message
                last_snapshot = time.monotonic()
            elif message.get("type") == "build_result":
                build_message = message.get("message", "")[:60]
                build_message_time = time.monotonic()
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
            delta = wrapped_distance(visual["x"], visual["y"],
                                     authoritative["x"], authoritative["y"])
            if delta > 180:
                visual.update(authoritative)
                continue
            visual["x"] = wrap_x(visual["x"] +
                                 shortest_dx(visual["x"], authoritative["x"]) * blend)
            visual["y"] += (authoritative["y"] - visual["y"]) * blend
            for key in ("a", "t"):
                diff = (authoritative[key] - visual[key] + math.pi) % math.tau - math.pi
                visual[key] = (visual[key] + diff * blend) % math.tau
            for key in ("name", "hp", "score", "dead", "color", "speed", "ammo", "material", "god_mode", "reload", "reload_duration"):
                visual[key] = authoritative[key]
        for pid in list(visual_players):
            if pid not in present_ids:
                del visual_players[pid]
        player = visual_players.get(local_id)
        if player:
            target_x = wrap_x(player["x"] - WIDTH / 2)
            camera[0] = wrap_x(camera[0] + shortest_dx(camera[0], target_x) * 0.15)
            camera[1] += (player["y"] - HEIGHT / 2 - camera[1]) * 0.15
        camera[0] = wrap_x(camera[0])
        camera[1] = max(0, min(WORLD_H - HEIGHT, camera[1]))
        keys = pygame.key.get_pressed()
        movement = int(keys[pygame.K_w] or keys[pygame.K_UP]) - int(keys[pygame.K_s] or keys[pygame.K_DOWN])
        turn = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        mx, my = to_logical(pygame.mouse.get_pos(), view, WIDTH, HEIGHT)
        aim = (math.atan2(my + camera[1] - player["y"],
                          shortest_dx(player["x"], wrap_x(mx + camera[0])))
               if player else 0.0)
        firing = bool((not build_mode and pygame.mouse.get_pressed()[0]) or keys[pygame.K_SPACE])
        # Continuous local engine responds to authoritative velocity and input.
        # Mute also affects this layer without changing the multiplayer state.
        engine.update(dt, player.get("speed", 0.0) if player else 0.0,
                      movement if player else 0,
                      alive=bool(player and not player.get("dead")))
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
        connected = local_id is not None and now - last_snapshot <= 3
        if build_message and now - build_message_time > 3.0:
            build_message = ""
        hovered = None
        if build_mode:
            hx, hy = to_logical(pygame.mouse.get_pos(), view, WIDTH, HEIGHT)
            hovered = (int(wrap_x(hx + camera[0]) // 50),
                       int((hy + camera[1]) // 50))
        draw_frame(
            screen, camera, state.get("walls", []), state["bullets"],
            list(visual_players.values()), local_id, effects, fonts,
            host, args.port, connected,
            "CONNECTING TO SERVER..." if local_id is None else "CONNECTION LOST",
            state.get("bases", []), state.get("pillboxes", []),
            state.get("built_walls", []), state.get("built_bridges", []),
            build_mode, build_part, hovered, build_message,
            state.get("built_roads", []))
        # Keep the SAME world view on all displays, with filtered scaling.
        display.fill((0, 0, 0))
        left, top, draw_width, draw_height = view
        if (draw_width, draw_height) == screen.get_size():
            display.blit(screen, (left, top))
        else:
            scaled = pygame.transform.smoothscale(screen, (draw_width, draw_height))
            display.blit(scaled, (left, top))
        pygame.display.flip()
    engine.stop()
    send(sock, addr, {"type": "leave"})
    sock.close()
    pygame.quit()


if __name__ == "__main__":
    main()
