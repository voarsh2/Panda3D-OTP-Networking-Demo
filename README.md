# Panda3D Distributed Objects with Astron

A small, runnable Panda3D world that shows how Direct distributed objects work with Astron: two clients, an UberDOG, an AI, a State Server, zones, and one database-backed object.

The login accepts a display name for local use; it is not account authentication.

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

On Windows, choose one mode launcher: `start-fixed-zones.bat` (`start-all.bat` is the same fixed-zone mode), `start-grid-client-local.bat` for client-led grid interest, or `start-grid-ai-managed.bat` for AI-managed grid interest. Each starts Astron, waits for its ports, starts UberDOG and waits for its login manager before starting AI, then opens Alice and Bob after the AI District is ready. Stop that stack before switching modes. The first launch offers to initialize the `panda3d-astron` submodule and install Python requirements in `.venv` if either is missing. `start-game.bat` and `start-game-dev-user2.bat` open extra fixed-zone clients.

The separate grid UI check launchers are optional development tools. Contract tests live under `tests/`; the normal mode launchers are for the two-client demo.

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

Open one terminal for each client and one for the inspector. The inspector opens interest in zone 2 automatically.

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

- [Login, ownership, and DC fields](docs/object-flow.md)
- [Zones, interest, and location changes](docs/interest.md)
- [Database persistence and object lifetime](docs/persistence.md)
- [Optional Cartesian grid module](docs/cartesian-grid.md)

The fixed-zone walkthrough is the default. The optional Cartesian grid module demonstrates both client-local interest and AI-managed ClientAgent interest; its AI and client commands are separate so each path can be inspected on its own.


## Further reading and related projects

- [Astron README](https://github.com/Astron/Astron/blob/master/README.md) and [documentation](https://github.com/Astron/Astron/tree/master/docs)

- [`panda3d-astron` SimpleExample](https://github.com/thetestgame/panda3d-astron/tree/v1.1.0/examples): the compact login, Owner View, and replication baseline. Its MIT-licensed source is pinned in [`references/panda3d-astron`](references/panda3d-astron).
- [Programmer's Quest](https://github.com/thetestgame/programmers-quest): a larger work-in-progress MMO reference, licensed [AGPL-3.0](https://github.com/thetestgame/programmers-quest/blob/develop/LICENSE). This demo links to it and includes none of its code.
- [Panda3D Distributed Networking manual](https://docs.panda3d.org/1.10/python/programming/networking/distributed/index)
- [Astron](https://github.com/Astron/Astron): message director, State Server, Client Agent, and database services for distributed-object networking.
- [Pirates Online (2013 recreation - Sunrise Games)](https://gitlab.com/sunrisemmos/pirates/game)
- [Disney Stable Panda3D source](https://gitlab.com/sunrisemmos/pirates/panda3d/-/tree/disney_stable?ref_type=heads): includes `GridChild` and related changes. [See the source notes](docs/disney_stable.md).
- [Ardos](https://github.com/ksmit799/Ardos): an Astron fork with native parenting rules for Toontown and Pirates clients.
- [OtpGo - Astron reimplementation](https://github.com/LittleToonCat/OtpGo): especially for cross-era Toontown/Pirates recreations
