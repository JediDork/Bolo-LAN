# Bolo-LAN

A modern, LAN-first, top-down tank combat prototype inspired by the strategy and mechanics of classic Bolo.

## Version 0.8 — Construction grid and diesel engine

- **Unified 50 × 50 world-unit construction grid** for all static world content.
- Wall segments are now **exactly one grid cell** each; destroying one opens a predictable one-tile gap.
- Roads, forests and water use grid-aligned rectangular tile regions, consistent between server collision and client rendering.
- Base and pillbox origins sit on grid-cell centres, giving future builder placement and fortification planning a reliable coordinate system.
- Decorative trees, grass and rock positions also use deterministic tile centres; grid lines remain visible over terrain.
- **Tanks and projectiles remain continuously movable**; the grid constrains *construction and terrain*, not tank steering or ballistic movement.
- Replaced the accelerating high-pitched engine sine tones with quieter, low-frequency **diesel-like exhaust thumps** (16/20/24 Hz) and subdued mechanical texture. Idle and rev layers crossfade with load, and **M** still mutes.
- Added automated tests checking exact tile dimensions/placement and low-register engine sound layer settings.

**Map compatibility:** The layout changes require all LAN clients and the host to use the new version. Existing match state is not migrated across executable restarts.

## Version 0.7 — Tank feel and defensive range tuning

Changes based on multiplayer playtesting:
- **Continuous tank engine audio:** three generated engine layers crossfade with tank speed/throttle. Hear a quiet idle rumble at rest and deeper, louder revving while driving. Press **M** to mute both engine and weapon effects; no audio files to download.
- **Lower vehicle speed:** maximum forward speed reduced from 195 to **125** world units/s (road speed up to 150), reverse reduced from 125 to **75**.
- **More gradual acceleration:** acceleration reduced from 245 to **115** units/s², braking reduced to 220, drag reduced to 80. This is a tuning baseline for feedback.
- **Pillbox defensive reach:** automated pillbox detection increased from 315 to **850** world units, and shell lifetime extended so shells can actually reach their targets. Cooldown tightened to 1.0 second. This reduces the ease of destroying them by staying at long range.
- Server owns all physics and turret logic. Update *every* client and host to the same version.

The standalone Windows build includes the new engine loop and its checks in GitHub Actions.

## Version 0.6 — Tank handling and territory playtest

**Tank handling**
- Tanks now accelerate up to cruising speed instead of moving instantly at full throttle.
- Releasing throttle produces coasting/rolling resistance; reversing while moving applies stronger braking.
- Hull turning accelerates and settles gradually, with slightly reduced turn speed at high forward velocity.
- Track cleats animate according to the server-reported tank speed.

**Terrain**
- Dirt roads increase target tank speed by 20%; forests reduce speed by 35%.
- Lakes are impassable and tanks slide against their edges.
- Roads, tree clusters and water are rendered at the established high-detail fullscreen resolution.
- World visibility stays fixed at 1200 x 760 units for all clients.

**Basic Bolo-inspired strategic systems**
- Six neutral bases. Drive into a base and hold it uncontested for **2.5 seconds** to capture.
- Owned bases restore armour and replenish ammunition (up to 24 shells).
- Capture progress is visible as a circular indicator; enemy presence contests a base.
- Four neutral automated pillboxes target nearby tanks, fire damaging shells and take **four hits** to destroy.
- The minimap shows supply bases and active pillboxes.
- These are early prototypes of territory mechanics, **not** yet the full classic builder/pillbox recovery or team victory rules.

**Testing:** launch with `Start-BoloLAN.ps1` or download the latest successful GitHub Actions Windows ZIP. All clients/hosts should run the same build because network snapshots now carry speed, ammo, bases and pillboxes. Test acceleration/coasting, braking, road/forest traction, lake boundaries, 2.5-second captures, repair/reload, and pillbox damage. Report gameplay feel and any network desync.

## Version 0.5 — Sharper fullscreen visuals and sound

- Battlefield visibility remains **exactly 1200 × 760 world units** on every machine, irrespective of screen resolution.
- The renderer now draws at **2400 × 1520 internal pixels** (2× detail per axis), with filtered fullscreen down/upscaling and aspect-ratio letterboxing. This improves fine tank, wall and terrain detail without exposing more map.
- Procedurally synthesized cannon shots, wall impacts, armour hits, tank explosions and masonry collapse sounds. No external sound files or internet dependency.
- Sound is distance-attenuated relative to the player; press **M** to toggle mute.
- When sound hardware is unavailable, gameplay continues silently.
- Press ESC to quit fullscreen.

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
- **M**: mute/unmute sounds
- **Esc**: quit

### Architecture

`shared.py`: constants and deterministic destructible wall sections. `terrain.py`: shared terrain and strategic structure locations. `display.py`: fixed 1200x760 logical viewport mapping. `server.py`: fixed timestep authoritative simulation and discovery. `client.py`: rendering and input. All combat outcomes are computed by the server. The client sends only movement/aim/fire intentions; server validates rate and handles hits.

Networking currently uses compact JSON snapshots over UDP for simplicity. Later milestones will add interpolation/prediction, more robust protocols, server browser, teams, and gameplay systems.

### Roadmap

1. **First LAN battle** — implemented initial prototype.
2. Client prediction/interpolation, sound, animations, effects and map variety.
3. Bolo bases/pillboxes/builders/terrain destruction and resources.
4. Teams, game browser, map editor, bot opponents and packaging.

## License

Project license to be decided. Original Bolo names/assets are not included.
