# Bolo-LAN

A modern, LAN-first, top-down tank combat prototype inspired by the strategy and mechanics of classic Bolo.

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

On the host PC:

```powershell
python server.py
```

On each player's PC:

```powershell
python client.py
```

The client broadcasts to discover an active LAN host; alternatively use `python client.py --host 192.168.1.20` (replace with the host PC's LAN IP).

Windows Firewall: allow inbound **UDP 50000** on the host. Client discovery uses UDP broadcast to port 50000. Different subnets or restrictive Wi-Fi settings may require `--host`.

### Controls
- **W/S**: forward/reverse
- **A/D**: rotate hull
- **Mouse**: aim turret
- **Left mouse** or **Space**: fire
- **Esc**: quit

### Architecture

`shared.py`: constants and deterministic terrain. `server.py`: fixed timestep authoritative simulation and discovery. `client.py`: rendering and input. All combat outcomes are computed by the server. The client sends only movement/aim/fire intentions; server validates rate and handles hits.

Networking currently uses compact JSON snapshots over UDP for simplicity. Later milestones will add interpolation/prediction, more robust protocols, server browser, teams, and gameplay systems.

### Roadmap

1. **First LAN battle** — implemented initial prototype.
2. Client prediction/interpolation, sound, animations, effects and map variety.
3. Bolo bases/pillboxes/builders/terrain destruction and resources.
4. Teams, game browser, map editor, bot opponents and packaging.

## License

Project license to be decided. Original Bolo names/assets are not included.
