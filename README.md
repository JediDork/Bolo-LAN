# Bolo-LAN

A modern, LAN-first, top-down tank combat prototype inspired by the strategy and mechanics of classic Bolo.

## Version 0.11 — Visible-range defences and testing god mode

- Pillbox engagement reduced from **850 to 355 world units**. Since all players see exactly **1200 × 760 world units** at once, this is slightly inside the vertical half-screen of 380 units. Players approaching from above or below should see a pillbox shortly before it begins firing. (Visibility near the world boundary or behind the HUD will still vary.)
- **G toggles per-player GOD MODE** during testing. The authoritative server preserves tank armour at 100% while enabled, so hits still create effects but no damage or deaths. Press G again to return to normal. Movement, weapon ammunition, collisions and captures behave normally.
- A gold ring around an invulnerable tank and a prominent HUD label show when god mode is enabled. All players see who is invulnerable.
- This is a developer/test convenience and is **available to all players** in the current LAN prototype. It should be disabled or made host-controlled before competitive play.
- God mode is off by default and resets when a player reconnects.

Update host and clients together so the new test command and player status are supported.

## Version 0.10 — Narrow rivers, bridges, clean forests and transparent flags

- **One-grid-cell river:** the meandering river now occupies exactly one 50-unit tile in each row, rather than a broad multi-cell watercourse. Each consecutive section deviates at most one tile horizontally.
- **No wall/forest overlap:** pre-existing wall sections inside or immediately alongside wooded areas are removed from the initial map consistently for clients and server. Future wall building can apply the same placement constraints.
- **Bridges at road crossings:** roads continue across rivers on visible timber bridge decks. These crossings travel at road speed; the rest of the river remains slow but fordable (18% of grass speed). Bridge construction and demolition by players are future work.
- **Smaller flags, transparent ground:** capture sites now retain their coloured status ring and animated capture arc, but the oversized opaque circular ground has been removed. Only the small square flag base and compact pole/pennant obscure underlying terrain.
- The construction grid still governs solid structures and terrain collision; natural-looking shorelines and forests remain unchanged.
- Extra automated tests validate narrow continuous rivers, bridge placement and consistent wall/forest clearances.

Restart every client and host together to use the same deterministic map.

## Version 0.9 — Natural terrain, connected roads and river fords

- **Natural-shaped forests and lakes:** deterministic connected clusters of 50-unit terrain tiles now form irregular shorelines and forest boundaries rather than simple rectangles. Rounded overlapping visual edges keep the terrain organic while its gameplay footprint remains grid-based for future building.
- **Road network:** routes are planned between all six flagged base locations using grid-aware pathfinding, avoiding solid walls and deep lakes and preferring existing road segments. Roads look like connected tracks instead of isolated rectangular bands.
- **Fordable river:** a meandering, variable-width river crosses the battlefield. Tanks can enter it, but their target driving speed drops to **18%** of grass speed, with strong water drag on entry. Deep blue lakes remain completely impassable.
- **Bridges are intentionally NOT buildable yet:** the river provides the tactical crossing problem that bridges will solve when we implement the builder. In this version you can still cross slowly without a bridge.
- **Minimap:** shows forest, lake, river and roads to help plan routes and defensible choke points. Bases display raised capture flags.
- **Fixed grid and fairness unchanged:** walls, base locations and pillboxes stay aligned to the 50-unit construction grid; tanks move continuously, and all players retain the same world view.
- Engine audio remains as tuned in v0.8.

Update both LAN host and clients before testing. Check whether wooded areas and shorelines feel natural, whether roads form useful routes between flags, and how crossing speed affects combat.

## Version 0.8 — Construction grid and diesel engine

- **Unified 50 × 50 world-unit construction grid** for all static world content.
- Wall segments are now **exactly one grid cell** each; destroying one opens a predictable one-tile gap.
- Roads, forests and water use grid-aligned rectangular tile regions, consistent between server collision and client rendering.
- Base and pillbox origins sit on grid-cell centres, giving future builder placement and fortification planning a reliable coordinate system.
- Decorative trees, grass and rock positions also use deterministic tile centres; grid lines remain visible over terrain.
- **Tanks and projectiles remain continuously movable**; the grid constrains *construction and terrain*, not tank steering or ballistic movement.
- Kept the original idle sound while replacing the accelerating high-pitched tones with restrained low-frequency **diesel-like exhaust thumps** (21/22/24 Hz layers). Engine layers crossfade with load, and **M** still mutes.
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
- **G**: toggle testing god mode (invulnerability)
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
