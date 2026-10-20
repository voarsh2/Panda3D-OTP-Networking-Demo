# Optional Cartesian grid example

The default walkthrough uses fixed District zones. This optional example adds a real Panda3D `DistributedCartesianGridAI` / `DistributedCartesianGrid` pair under the District, a session avatar parented to the grid, and a moving probe. Its classes and required fields are in a separate DC file and Astron config, loaded only by the grid-enabled AI and client.

## What it shows

- `DemoCartesianGridAI` supplies `startingZone=6000`, `gridSize=8`, `gridRadius=1`, and `cellWidth=4`.
- The two demo avatars start near cell centers. Grid labels sit just above the avatar and probe, offset toward each cell's far edge, so the angled camera keeps the number visible in the occupied cell.
- Required DC fields publish `setParentingRules` and `setCellWidth` to the client. The client grid maps coordinates to cell zones with `getZoneFromXYZ`.
- The AI adds the avatar and a moving `DemoGridProbe` to the grid. Panda3D's grid task changes their State Server zones as they cross cell boundaries; `GridParent` preserves their world positions relative to each cell.
- The probe uses `DistributedSmoothNode` telemetry and bounded `posInterval` legs in a captured grid-root frame. Panda's `DistributedCartesianGridAI.updateGridTask` owns cell transitions; movement does not infer a frame-to-frame grid-root delta across a reparent.
- By default, the client follows its Owner View's position and holds local interest in the current cell and its neighbors. Leaving the grid closes that interest.
- `DemoWorldGridManagerAI` provides the server-managed counterpart. Grid child arrival, cell-change, and leave hooks open and clear one ClientAgent interest per visible cell. `getInterestZones(grid, avatar)` reports the AI's requested zone set.
- Server-opened handles use the high-bit ID range. The AI waits for ClientAgent completion callbacks before resuming grid-child movement; the client reports received handle state and `doId2do` membership for the moving probe.

## Demo synchronization limit

`interestSnapshotPending()` pauses the grid update task and all tracked grid-child movement while any avatar has an unfinished interest operation. That global barrier avoids broadcasting changes into a view whose initial objects may still be generating. It also means one slow avatar pauses every player sharing this grid, so it is a demonstration strategy rather than a production-wide policy. A production MMO should sequence or buffer visibility per observer and let unrelated players continue moving.

If a completion callback never arrives, this demo's barrier stays closed. Astron's configured ClientAgent `interest_timeout` normally forces completion, but a disconnected agent can still leave the grid paused. There is no local watchdog: resuming blindly could send fields before the client has generated the objects.

The probe leaves and re-enters the client repository when it crosses the edge of the owner's interest window. That is the expected AOI lifecycle; the client logs `doId2do` membership on both events. Both Astron configs set the ClientAgent `interest_timeout` to 5 seconds. A heavily loaded machine may need a longer value under the role's `tuning` section.

During login, UberDOG opens the GameGlobals management interest and then District main interest, waiting for both ClientAgent callbacks before asking the AI to create the avatar. The grid is therefore in the client repository before AI-managed cell interests open. The AI generates the avatar directly in its initial grid cell. When it moves beyond the grid bounds, the AI moves it to an unobserved District zone; returning to the grid reparents it and opens the interest window again. The session avatar uses a simple AI-authored `setPosition` field; only the patrol probe demonstrates SmoothNode telemetry.

## Run it

On Windows, double-click `start-grid-client-local.bat` or `start-grid-ai-managed.bat`. Each starts a fresh Astron config, UberDOG, AI mode, and visible client. Close those service windows before switching modes.

Start Astron with the matching grid config, then start UberDOG as described in the main README:

```powershell
astrond demo/astron/config/astron-cartesian-grid.yml
```

Start the AI with the optional grid enabled. The default uses client-local interest:

```powershell
python -m demo.ai_server --cartesian-grid
```

Use the grid-aware client in place of `demo.client`:

```powershell
python -m demo.cartesian_grid_client --name Alice --show-grid
python -m demo.cartesian_grid_client --name Bob
```

### Use AI-managed interest

Keep the same Astron configuration and start the AI with its WorldGridManager enabled:

```powershell
python -m demo.ai_server --cartesian-grid --ai-grid-interest
```

Start a client with local grid interest disabled so the AI manager is the only grid-interest source:

```powershell
python -m demo.cartesian_grid_client --name Alice --server-grid-interest
```

Move beyond the grid edge (x or y reaches 16). The AI reports its requested zone set and closes every server-opened cell interest. Move back in to reopen the window. The client prints interest handles as pending, complete, or removing, alongside whether each probe object is present in `doId2do` and generated.

The local and AI-managed paths can also be run together to compare them; for a single-source run, use the command pair above. The HUD shows the interest source, observer cell, radius, District zone 2 state, and probe ID/zone/lifecycle. With `--show-grid`, cyan outlines mark the current interest window while leaving cell labels visible. `--offscreen` runs without a visible window.

The fixed-zone path remains `python -m demo.ai_server` with `python -m demo.client`.

## Verify live interest

For an optional visible check, double-click `test-ui-grid-client-local.bat` or `test-ui-grid-ai-managed.bat`. The window drives the scenario, checks live object and interest state, and holds a PASS/FAIL result until Escape.

With Astron using the grid config, UberDOG running, and the AI started in the matching mode, run this offscreen integration check:

```powershell
python tests/cartesian_grid_live.py
```

This checks client-local interest. To check AI-managed interest, restart the AI with `--cartesian-grid --ai-grid-interest`, then run:

```powershell
python tests/cartesian_grid_live.py --server-grid-interest
```

The check moves its session avatar across a cell boundary, then reads completed interest zones, `doId2do`, and the Owner View map. It also verifies the zone 2 beacon appears and leaves view, and that the probe crosses cells, leaves, and re-enters. It uses object lifecycle and location events, with one watchdog. The default watchdog is 90 seconds; raise it with `--timeout` if Astron's `tuning.interest_timeout` or startup time is higher.
