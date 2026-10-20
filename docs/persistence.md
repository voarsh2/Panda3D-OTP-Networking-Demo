# Persistence and object lifetime

The demo compares a short-lived session avatar with one database-backed beacon.

## Beacon lifecycle

`demo/astron/config/astron.yml` enables Astron's YAML Database and DBSS roles. On AI startup, `demo/persistence.py` reads the beacon DO ID from `demo-data/beacon-doid.txt` and queries the database. It creates the object if the ID is new or missing, then activates it under the District in zone 2.

When `DemoBeaconAI` generates, it increments `setActivationCount`. The DC field is `required broadcast ram db`: the client sees the current value when the beacon enters view, updates are replicated while it is active, and DBSS saves the field. After a full Astron restart, the same DO ID is loaded and the count increases again.

## Compare with avatars

Avatars are registered with `clientAddSessionObject`. Astron removes that session object when its client disconnects. The beacon is activated from the database and has no client session owner, so its identity and saved field survive the disconnect and service restart.

This is a small persistence example, not account-owned inventory. Login is anonymous, and the beacon ID file and YAML database are local demo state under `demo-data/`.
