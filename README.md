# Panda3D Distributed Objects with Astron

A small runnable world using Panda Direct distributed objects, selected Toontown/Disney-style OTP game roles, and Astron services: two clients, an UberDOG, an AI, zones, and one database-backed object.

The login accepts a display name for local use; it is not account authentication.

## How this differs from Panda3D's built-in networking

**This is an Astron/OTP demo, not a CMU `ServerRepository` example.** It uses Panda3D Direct's distributed-object and DC-field model, with client/server messages routed through Astron's ClientAgent, Message Director, and State Server, alongside OTP AI and UberDOG roles.

Panda3D's CMU path demonstrates basic client/server DO networking. Disney's OTP architecture builds a scalable online game world around those same DOs, with separate object roles, services, and AI-owned shards.

Panda3D's CMU-derived `ClientRepository` / `ServerRepository` already supports distributed objects, DC fields, replication, and zone filtering. Its `ServerRepository` tracks which clients want each zone and relays an object's broadcasts to the other clients in that zone; when a client enters a zone, owners send their objects' generate data. It also has a server-side check for some client field updates. This already filters out clients with no interest in that zone.

Astron splits that work across services: the ClientAgent subscribes to parent/zone channels, the State Server holds live object state and supplies interest snapshots, and the Message Director routes channel messages to subscribers. The stock CMU pair has no separate ClientAgent, Message Director, State Server, OTP AI/UberDOG, or DBSS; its `ServerRepository` is the relay and sends directly to each client in a zone's interest set. Astron's separate interests can overlap, and an AI can change one through the ClientAgent. The grid example holds a District interest alongside a Cartesian-grid window. See [the interest guide](docs/interest.md#the-interest-models-differ) for the traffic path.

The backend responsibilities are split across services:

| Service | Responsibility in this demo |
|---|---|
| ClientAgent | Connects clients, handles their interests, and enforces DC field-send permissions, constraints, and configured client-interest rules. These protocol checks do not authorize account actions. |
| Message Director | Routes messages between clients and server processes. |
| State Server | Holds live object state, ownership, and parent/zone locations. |
| AI server / repository | Runs authoritative avatar movement and world logic. |
| UberDOG | Hosts global-object services; here it handles login and avatar/session setup. |
| Database Server + Database-State Server (DBSS) | The database stores `db` fields; DBSS activates persistent objects into live state for server-side work and writes changed `db` fields back, even without a player session. |

These are logical roles, not a required one-process-per-row layout. This demo runs the Message Director, ClientAgent, State Server, Database Server, and DBSS in one `astrond` daemon. A deployment can split them across hosts and assign different world shards to separate AI servers. The game's login or shard directory chooses an AI shard for each player; the Message Director routes messages among that AI, the State Server, ClientAgents, and other services. See [scaling and load distribution](docs/object-flow.md#scaling-and-load-distribution).

Direct defines the DO/DC contracts and object lifecycle; OTP-style code organizes those objects into game roles and a world; Astron supplies the backend services. This demo shows a small slice of that structure through Owner Views, login, interest, persistence, and an optional Cartesian grid. Its demo-scoped Astron protocol adapter is in [`demo/networking`](demo/networking); it builds on Direct's repository and interest classes and implements the flows this demo uses. The adapter is a slimmed-down port of selected networking code from the author's production projects, alongside separately credited MIT-licensed portions from `panda3d-astron`; see its [scope and source notes](demo/networking/README.md) and [third-party notice](demo/networking/THIRD_PARTY_NOTICES.md). The [object-flow guide](docs/object-flow.md#direct-otp-and-astron) explains how the layers fit together.

### Choosing a backend

CMU fits a compact game when one `ServerRepository` and a flat zone relay are enough. A custom subclass can add a bespoke handshake, validation, rate limits, or AI-input protocol in one server; for a narrow game protocol, that can be less machinery.

Astron is useful when you need parent-scoped overlapping interests (including AI-managed windows), State Server-held `ram` state and snapshots, or persistent `db` fields. Its Message Director routes subscribed location channels across services. Rebuilding that routing, state/snapshot lifecycle, and persistence around CMU means the game owns more code and operations. This demo shows AI-managed grid interest and a persistent beacon. Both stacks leave account rules and gameplay authorization to game code; with Astron, the game's shard selector assigns players and Astron routes the resulting service traffic.

## What to try

- Run Alice and Bob. Move an avatar with the arrow keys; both clients receive its AI-authored position.
- Cross **x = 4** to move the avatar from District zone 1 to zone 2. The State Server updates which clients receive it based on their interest.
- Press **Tab** to add or remove your interest in zone 2. The beacon and avatars in that zone enter or leave your view.
- Run `demo.inspect` to see live object IDs, parent and zone values, and generation or location changes.
- Restart Astron and the servers. The beacon keeps its ID and increments its saved activation count; session avatars are recreated.

## Run locally

The Windows launchers use the bundled x64 Astron build in `demo/astron`. To run services manually or on another platform, build Astron and put `astrond` on `PATH` (see the [Astron build guide](https://github.com/Astron/Astron/blob/master/docs/building/build-readme.md)). From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Windows, choose one mode launcher: `start-fixed-zones.bat` (`start-all.bat` is the same fixed-zone mode), `start-grid-client-local.bat` for client-led grid interest, or `start-grid-ai-managed.bat` for AI-managed grid interest. Each starts Astron, waits for its ports, starts UberDOG and waits for its login manager before starting AI, then opens Alice and Bob after the AI District is ready. Stop that stack before switching modes. If Panda3D is missing, the launcher offers to create `.venv` and install project requirements. `start-game.bat` and `start-game-dev-user2.bat` open extra fixed-zone clients.

The grid UI check launchers are optional development tools. Contract tests live under `tests/`; the normal mode launchers are for the two-client demo. With the matching services running, `python tests/fixed_zones_live.py` checks fixed-zone leave/re-entry with two clients, and `python tests/cartesian_grid_live.py` checks client-local grid interest. Use `--server-grid-interest` with the AI-managed grid mode. `python tests/database_live.py` verifies Database create/query/delete messages. `python tests/persistence_live.py --snapshot "$env:TEMP\panda-activation-count.txt"`, followed by a full service restart and the same command, checks that the beacon's activation count increases from its saved value.

The bundled Astron executable's third-party licenses and Windows runtime requirements are listed in [its notices](demo/astron/THIRD_PARTY_NOTICES.md). The demo uses Astron's YAML database backend; no MongoDB server is needed.

To run the services manually instead of using the Windows launchers, start them in separate terminals in this order. Wait for the UberDOG ready message before opening the AI terminal.

**Terminal 1 — Astron**

```powershell
astrond demo/astron/config/astron.yml
```

**Terminal 2 — UberDOG**

```powershell
python -m demo.ud_server
```

**Terminal 3 — AI**

```powershell
python -m demo.ai_server
```

Wait for the AI's District to be ready, then open one terminal for each client and one for the inspector. The inspector opens interest in zone 2 automatically.

```powershell
python -m demo.client --name Alice
```

```powershell
python -m demo.client --name Bob
```

```powershell
python -m demo.inspect --name Observer
```

Run the focused contract tests with `python -m unittest discover -s tests`. They do not start Astron. For the live grid check, see [the Cartesian grid guide](docs/cartesian-grid.md#verify-live-interest).

## Read by topic

- [Direct, OTP, login, ownership, and DC fields](docs/object-flow.md)
- [Zones, interest, and location changes](docs/interest.md)
- [Database persistence and object lifetime](docs/persistence.md)
- [Optional Cartesian grid module](docs/cartesian-grid.md)

## Code map

| System | Entry point | Networking support |
|---|---|---|
| Client and Owner View | [`demo/client.py`](demo/client.py) | [`client_repository.py`](demo/networking/client_repository.py) |
| UberDOG login | [`demo/ud_server.py`](demo/ud_server.py) | [`internal_repository.py`](demo/networking/internal_repository.py) |
| AI world and movement | [`demo/ai_server.py`](demo/ai_server.py), [`demo/objects.py`](demo/objects.py) | [`internal_repository.py`](demo/networking/internal_repository.py) |
| Grid interest | [`demo/cartesian_grid.py`](demo/cartesian_grid.py), [`demo/cartesian_grid_client.py`](demo/cartesian_grid_client.py) | ClientAgent interest messages in [`client_repository.py`](demo/networking/client_repository.py) |
| Persistence | [`demo/persistence.py`](demo/persistence.py) | [`database.py`](demo/networking/database.py) |

The fixed-zone walkthrough is the default. The optional Cartesian grid module demonstrates both client-local interest and AI-managed ClientAgent interest; its AI and client commands are separate so each path can be inspected on its own.

## Further reading and related projects

- [Forum introduction and discussion of this demo](https://discourse.panda3d.org/t/panda3d-direct-astron-networking-distributed-objects-interest-management-and-cartesian-grid-demo/)
- [Astron Panda3D fork comparison](https://github.com/panda3d/panda3d/compare/master...Astron:panda3d:master): compare Panda3D `master` with Astron's `panda3d` branch to inspect engine-side networking changes relevant to Astron connectivity.
- [Astron README](https://github.com/Astron/Astron/blob/master/README.md) and [documentation](https://github.com/Astron/Astron/tree/master/docs)

- [`panda3d-astron` SimpleExample](https://github.com/thetestgame/panda3d-astron/tree/v1.1.0/examples): the compact login, Owner View, and replication baseline. This repo links to the example; the demo runs its own adapter in [`demo/networking`](demo/networking).
- [Programmer's Quest](https://github.com/thetestgame/programmers-quest): a larger work-in-progress MMO reference, licensed [AGPL-3.0](https://github.com/thetestgame/programmers-quest/blob/develop/LICENSE). This demo links to it and includes none of its code.
- [Panda3D Distributed Networking manual](https://docs.panda3d.org/1.10/python/programming/networking/distributed/index)
- [Panda3D's CMU-derived `ClientRepository`](https://docs.panda3d.org/1.10/python/reference/direct.distributed.ClientRepository), which documents the built-in repository path this demo is compared with.
- [Panda3D's `ServerRepository` source](https://docs.panda3d.org/1.10/python/_modules/direct/distributed/ServerRepository), which shows how the stock server tracks zones and routes object updates.
- [Astron](https://github.com/Astron/Astron): message director, State Server, Client Agent, and database services for distributed-object networking.
- [Pirates Online (2013 recreation - Sunrise Games)](https://gitlab.com/sunrisemmos/pirates/game)
- [Disney Stable Panda3D source](https://gitlab.com/sunrisemmos/pirates/panda3d/-/tree/disney_stable?ref_type=heads): includes `GridChild` and related changes. [See the source notes](docs/disney_stable.md).
- [Ardos](https://github.com/ksmit799/Ardos): an Astron fork with native parenting rules for Toontown and Pirates clients.
- [OtpGo - Astron reimplementation](https://github.com/LittleToonCat/OtpGo): especially for cross-era Toontown/Pirates recreations
