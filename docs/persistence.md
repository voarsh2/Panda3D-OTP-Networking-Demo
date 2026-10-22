# Persistence and object lifetime

The demo compares a short-lived session avatar with one database-backed beacon. The [DC field guide](object-flow.md#dc-field-permissions) explains how `ram` and `db` affect their lifetimes.

## Beacon lifecycle

`demo/astron/config/astron.yml` enables Astron's YAML Database and DBSS roles. On AI startup, `demo/persistence.py` reads the beacon DO ID from `demo-data/beacon-doid.txt` and queries the database. It creates the object if the ID is new or missing, then activates it under the District in zone 2.

When `DemoBeaconAI` generates, it increments `setActivationCount`. The DC field is `required broadcast ram db`: the client sees the current value when the beacon enters view, updates are replicated while it is active, and DBSS saves the field. After a full Astron restart, the same DO ID is loaded and the count increases again.

## Compare with avatars

Avatars are registered with `clientAddSessionObject`. Astron removes that session object when its client disconnects. The beacon is activated from the database and has no client session owner, so its identity and saved field survive the disconnect and service restart.

This is a small persistence example, not account-owned inventory. Login is anonymous, and the beacon ID file and YAML database are local demo state under `demo-data/`.

## Applying server-side logic to offline data

This matters when a game needs to operate on an object whose player is offline. For example, a `CarManager` could request a fuel refill for an offline player's vehicle, or a reward service could grant an offline reward. The authoritative AI or another game service can activate that database-backed object through DBSS, give it the appropriate AI authority, apply the normal game rules, and persist the changed fields. DBSS supplies the live object state and saves its `db` fields; game code validates eligibility and implements the refill or reward. No client session is required.

For a simple field edit that does not need live-object behavior, a direct database query or update may be enough. Activate through DBSS when existing distributed-object or AI logic needs to run against the stored state.

## Verify persistence across restart

With Astron running, `python tests/database_live.py` creates a temporary database object, queries its DC field, deletes it, and confirms it is gone.

With Astron, UberDOG, and the fixed-mode AI running, query the live beacon through a client:

```powershell
python tests/persistence_live.py --snapshot "$env:TEMP\panda-activation-count.txt"
```

Stop all three services, restart them with the same Astron database, then run the same command again. The check reads the beacon from the client repository and requires its activation count to exceed the saved snapshot.

## Source map

| Area | File |
|---|---|
| Beacon create, query, and DBSS activation | [`demo/persistence.py`](../demo/persistence.py) |
| Astron database messages used by the demo | [`demo/networking/database.py`](../demo/networking/database.py) |
| Database create/query/delete protocol check | [`tests/database_live.py`](../tests/database_live.py) |
| Live restart check | [`tests/persistence_live.py`](../tests/persistence_live.py) |

See Astron's [DBSS activation protocol](https://github.com/Astron/Astron/blob/master/docs/protocol/12-stateserver.md) and this demo's [beacon activation code](../demo/persistence.py).

This demo shows a database-backed beacon being activated and saved. It does not implement the offline car or reward workflows.
