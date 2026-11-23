# Bolo-LAN

A modern, LAN-first, top-down tank combat prototype inspired by the strategy and mechanics of classic Bolo.

## Version 0.17 — Six flags and resupply/ownership audio

- The 5200 × 3800 planetary battlefield now has **six** strategic flags, down from 24.
- Flag count is a map setting: `MAX_FLAGS_PER_MAP = 6`, `MAP_FLAG_COUNT = 6`, and `MAP_SEED = 7319` in `terrain.py`. `select_flag_tiles(seed, count)` deterministically spreads chosen flags across the map while respecting east/west wrapping. A future seeded-map generator can reuse this selector.
- **Six new sounds** (procedural; no sound assets required): **material added** (light mechanical click), **materials full** (two-tone chime), **ammo added** (heavy loader clunk), **ammo full** (confirmation chime), **flag taken** (rising victory tone), and **flag lost** (falling warning tone).
- Resupply audio plays only for the tank receiving materials/ammo and is rate-limited while loading, with a **single full-capacity cue** each time the resource reaches its maximum. Spending and replenishing resources allows the full cue to play again.
- Taking a flag plays the victory sound for the new owner. Capturing an opponent's flag plays a separate loss notification for its previous owner. Neutral flags have no previous owner to notify.
- All sounds respect **M (mute)** and operate on the authoritative server's state transitions.
- Update every LAN client and the host together; the reduced flag arrangement changes road routing and initial map layout.

## Version 0.16 — Planet-style horizontal world wrapping

- **East joins west:** the map now behaves like a cylinder/planet's longitude: drive right through the eastern map edge and emerge seamlessly at the western edge, and vice versa. There is no east/west boundary wall.
- **North and south are still the poles:** the upper/lower edges remain solid, with no vertical wrap. The world is still 5200 × 3800 units and keeps its existing map layout and construction grid.
- **Seamless camera:** the camera follows the shortest horizontal route, preventing a sudden jump across the entire map. The terrain renderer repeats the same cached map chunks at the wrap, including the shorter final chunk, so both sides stay visible together.
- **Full multiplayer physics:** tanks, shells, impacts, collisions, pillbox detection/aiming, forest line of sight and base captures all use the nearest longitude rather than treating the joined edges as distant.
- **Builder and aiming:** mouse targeting and grid building work over the join; construction range accounts for the wrapped distance. The minimap retains a single overview and splits its viewport indicator when the camera crosses the seam.
- **Balanced visibility:** no changes to the fixed 1200 × 760 player camera or the existing top/bottom boundaries.

**Testing:** try driving through both horizontal edges, firing across the seam at another tank, capturing a base near an edge, and building while the camera straddles the join. All LAN clients and the host must use the same version.

## Version 0.15 — Continuous roads and buildable tracks

- **Road rendering fixed:** straight runs and intersections are now painted as continuous earth tracks, not overlapping circles. Outer shoulders and roadbed are drawn in separate passes, preventing the dark semicircle seams seen in the screenshot. Only true dead ends have rounded caps.
- **Construct roads:** enter build mode with **B**, choose **6 (ROAD)**, then left-click an empty 50-unit tile. Each road costs **1 construction material** and can connect to existing roads or other new road tiles.
- Player-built roads grant the same **20% tank-speed bonus** as existing roads, appear on every client's battlefield and minimap, and can be removed by their owner using **5 (REMOVE)**.
- Placement stays server-authoritative: no roads on rivers (use bridges), lakes, forests, flags, existing roads, walls, or pillboxes. Builders must be within the normal 175-unit placement range.
- Player-built road tracks are drawn dynamically using the same visual treatment as the terrain roads. This doesn't affect the fixed player viewing area or any existing construction tools.
- Added automated road-building and rendering regression tests.

## Version 0.14 — Larger strategic world, real lakes and defensive retaliation

- **Four times the playable terrain:** enlarged the world from **2600 × 1900** to **5200 × 3800** world units, without changing the fair **1200 × 760** viewport. Four map sectors now contain **24 capturable flags**, **16 starting pillboxes**, varied forests, lakes, roads and existing structures. Spawn locations are distributed across the larger area.
- **Lakes look like complete lakes:** organic smooth, filled shoreline polygons replace the disconnected circles. Water has a continuous interior, gently outlined banks and occasional subtle ripples. Deep lake collision still follows authoritative 50-unit tiles.
- **Rivers have destinations:** two narrow, connected waterways originate at the north and western world edges and flow directly into inland lakes. Each river uses one tile across its channel (with additional connecting elbow squares at turns) and remains fordable at 18% grass speed outside bridges.
- **Roads and bridges:** paths link flags across the expanded map. Whenever a routed road crosses a river its bridge is prebuilt, while player-built bridges still work as before.
- **Pillboxes respond to aggression:** turrets **track but do not fire** from **355–465 world units** until a player fires *towards* them. An aimed shot provokes the watching turret, which may retaliate across its full 465-unit detection area for 6 seconds. Inside 355 units, pillboxes still fire unprovoked. Sight is blocked by masonry and sufficiently deep forests, as before; pillboxes must rotate and align before firing.
- **Large-map performance:** terrain now renders in on-demand cached 500-unit chunks with a bounded cache rather than allocating a huge full-world render surface. The minimap automatically scales down to continue showing the entire battlefield.

**Multiplayer warning:** the map and server game rules changed substantially. Restart the host and update all connected clients before testing. Try exploring for several minutes in God Mode (G) and look for any seams, slow frames, or questionable shorelines.

## Version 0.13 — Forest ballistics, visible pillbox tracking and reverse steering

- **Forest absorbs cannon shells:** shells can travel through at most two distinct 50×50 forest tiles before dissipating in the third. The depth is tracked across server ticks, so splitting a shot between simulation frames cannot bypass the woodland cover. Bullets and forest blocking use the same authoritative grid.
- **Turrets watch before firing:** automated pillboxes now acquire and slowly rotate their visible barrel towards a tank within **465 world units**, but do not fire until the tank is inside **355 world units** and the barrel is aligned. A subtle amber acquisition ring indicates that a pillbox sees a target.
- **Real line of sight:** pillboxes cannot detect or shoot through intact pre-existing walls, newly built walls, or more than two forest tiles. If the view becomes blocked, they stop tracking and firing. Friendly pillboxes retain owner protection.
- **Reverse steering is mirrored:** pressing **S+D** while reversing rotates the hull in the opposite direction to forward **W+D**, so the rear moves to the right. **S+A** mirrors it to the left.
- Server-controlled tracking, hit detection and movement are synchronized to every player; HUD fairness and God Mode are unchanged.

Run the existing PowerShell updater or download the successful Windows artifact from GitHub Actions. All host and clients must use the same code version.

## Version 0.12 — Playable base builder

- Press **B** to enter or exit build mode. The tank remains driveable, but left-click now places selected construction; **Space** still fires its cannon.
- In build mode, press **1** to build one 50x50 masonry wall tile (**2 materials**), **2** for a wooden bridge over a non-bridged river tile (**5 materials**), **3** for an owned autonomous pillbox (**8 materials**), **4** to repair a damaged wall/owned pillbox (**1 material**), or **5** to dismantle your own structures (**free**). Then **left-click the target grid tile**.
- Buildings must be placed within **175 world units** of your tank; construction is restricted to suitable, unoccupied tiles. Walls and pillboxes cannot overlap forests, lakes, rivers, bases, existing defences, tanks or bridges. Bridges require an open river tile. The server checks all rules, preventing clients from placing remote/invalid structures.
- Start with **18 materials**, can hold up to **30**, and replenish at **1.2 materials/second** when standing at a base you own. Materials do not reset when you respawn.
- Built walls have **four hit points**, stop tanks and shells, display incremental damage and can be repaired or dismantled. Owned pillboxes automatically fire at enemy tanks. Newly built bridges appear for everyone and permit road-speed travel across the formerly slow river.
- A highlighted tile follows the cursor in build mode. Build confirmations and errors appear in the HUD, alongside the materials count. Assets persist for the duration of the host's game session; saving maps is planned for a later milestone.
- The initial prototype allows all participants to build. **G** remains an unrestricted developer/test god-mode toggle, not a competitive permission.

### Build controls

| Key | Action | Material cost |
| --- | --- | ---: |
| **B** | Toggle build mode | — |
| **1** | Select wall | 2 |
| **2** | Select bridge | 5 |
| **3** | Select pillbox | 8 |
| **4** | Select repair tool | 1 |
| **5** | Select remove tool | 0 |
| **6** | Select road | 1 |
| **Left-click** | Apply selected tool to grid tile | depends |
| **Space** | Fire while in build mode | ammo |

**Multiplayer:** everyone must update host and clients to v0.12 for matching state and build commands.

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
- **B**: toggle build mode; 1–5 select parts; click tile to build
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
