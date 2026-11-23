# Bolo-LAN

A modern, LAN-first, top-down tank combat prototype inspired by the strategy and mechanics of classic Bolo.

## Version 0.4 — Combat and fair fullscreen

- **True fullscreen, fixed gameplay viewport:** every machine sees exactly 1200x760 logical pixels; higher resolutions scale the same picture rather than revealing more terrain. Aspect-ratio differences are black-letterboxed. Mouse aiming compensates for scaling and letterboxing.
- **Clear driving direction:** a bright yellow chevron marks the tank hull's front even when the turret is pointing backwards.
- **Physical turret traverse:** the server limits rotation to 2 radians/second (~115 degrees/second) instead of snapping instantly to the cursor. Projectiles always fire in the actual turret direction.
- **Unobstructed north edge:** the status HUD moved to a semi-transparent bottom panel.
- **Destructible wall segments:** each wall is divided into sections that take **four shell hits** each. Every hit increases visible cracks and chips; the fourth destroys that section, generates debris, and creates a navigable gap. Damage and collision are authoritative on the host and synchronized to clients.
- Automated tests cover wall durability, turret limits, fullscreen mapping and existing combat.

Run `Start-BoloLAN.ps1` again to pull the update, or download the latest successful Windows distribution from GitHub Actions. **Update every player and host:** older protocol versions lack wall state.

## Version 0.3 — One-click LAN hosting

Every game client can host. Run `python launcher.py` (or the packaged `BoloLAN.exe`): it checks for an existing LAN server, joins if found, and otherwise starts a server in the same process before joining locally. The first player acts as host, so closing that game ends the hosted session. Players on other computers can join while the host remains running. If several machines start at exactly the same time, a rare split-lobby race is possible; try restarting the later instances if they do not see each other. A dedicated `server.py` / `BoloLAN-Server.exe` is still available.

On Windows you can use `Start-BoloLAN.ps1` to pull or clone the latest GitHub sources, install the Python dependencies in an isolated `.venv`, and start the game. Run: `powershell -ExecutionPolicy Bypass -File .\\Start-BoloLAN.ps1`. Optional: `-HostIP 192.168.1.20 -PlayerName Tank1`. Git and Python 3.11+ are needed for the script, but **not** for the packaged executable.

## Version 0.2 — LAN combat polish

- Smooth interpolation of networked tank positions and independently aimed turrets.
- Procedural terrain detail, improved treads and a live minimap.
- Server-generated synchronized muzzle flashes, impacts, hits and destruction effects.
- Particle-based explosions and moving-tank dust.
- Headless multiplayer smoke tests run during each Windows executable build.
- Original 0.1 combat and LAN discovery remain intact.

**Important:** both host and clients must use the latest build together for consistent combat effects. This remains a prototype; bases, pillboxes, builders and resources are planned next.

## Milestone 1

- Dedicated authoritative UDP game server (30 ticks/s).
- Two or more tanks moving and aiming independently.
- Mouse-targeted turret, WASD movement, left-click firing.
- Scrolling camera, obstacles, projectile collision and respawns.
- Automatic LAN discovery via UDP broadcast plus manual server address.
- No accounts, cloud service or internet needed for gameplay.

**This is a first playable prototype, not yet the full Bolo rule set.** Bases, pillboxes, builders, resources and destruction are planned.

## Setup (Windows / Linux / macOS)

Python 3.11+ recommended.

```powershell
python -m pip install -r requirements.txt
```

On **every** PC, run the same launcher. It auto-joins the first existing game or hosts a new one if none is found:

```powershell
python launcher.py
```

For a dedicated always-on host instead, run `python server.py`, and start players with `python launcher.py`.

The client broadcasts to discover an active LAN host; alternatively use `python client.py --host 192.168.1.20` (replace with the host PC's LAN IP).

Windows Firewall: allow inbound **UDP 50000** on the host. Client discovery uses UDP broadcast to port 50000. Different subnets or restrictive Wi-Fi settings may require `--host`.

### Controls
- **W/S**: forward/reverse
- **A/D**: rotate hull
- **Mouse**: aim turret
- **Left mouse** or **Space**: fire
- **Esc**: quit

### Architecture

`shared.py`: constants and deterministic destructible wall sections. `display.py`: fixed 1200x760 logical viewport mapping. `server.py`: fixed timestep authoritative simulation and discovery. `client.py`: rendering and input. All combat outcomes are computed by the server. The client sends only movement/aim/fire intentions; server validates rate and handles hits.

Networking currently uses compact JSON snapshots over UDP for simplicity. Later milestones will add interpolation/prediction, more robust protocols, server browser, teams, and gameplay systems.

### Roadmap

1. **First LAN battle** — implemented initial prototype.
2. Client prediction/interpolation, sound, animations, effects and map variety.
3. Bolo bases/pillboxes/builders/terrain destruction and resources.
4. Teams, game browser, map editor, bot opponents and packaging.

## License

Project license to be decided. Original Bolo names/assets are not included.
