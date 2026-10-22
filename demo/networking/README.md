# Demo networking layer

This package keeps the Astron wire code the demo uses. It depends on Panda's
Direct `ClientRepositoryBase`, `ConnectionRepository`, `DoInterestManager`, DC
classes, and built-in `PyDatagram`; it is not a general replacement for a full
OTP/Astron adapter.

The adapter is a slimmed-down port of selected networking code from
author's production projects, trimmed to the flows shown here. It keeps the
Direct-to-Astron connection and lifecycle work visible without bringing over
the surrounding game-specific systems. The [Astron Panda3D fork comparison](https://github.com/panda3d/panda3d/compare/master...Astron:panda3d:master)
provides context for the engine-side changes used to connect Astron with
Panda3D networking; this package covers the demo's application-level adapter.

| Module | Responsibility |
|---|---|
| `client_repository.py` | ClientAgent messages, required and Owner View generation, object leaving, interest callbacks, and client field updates. |
| `bulk_fields.py` | Decodes `CLIENT_OBJECT_SET_FIELDS` in wire order and sends each field through Direct's normal `handleUpdateField` path. |
| `internal_repository.py` | Message Director connection, AI object lifecycle/location, ClientAgent state/interest operations, ownership, and DBSS activation. |
| `database.py` | Database object creation and full-object queries used by the saved beacon. |
| `msgtypes.py` | Astron message IDs used by these flows. |

The bulk-field path keeps Direct responsible for DC decoding, Owner Views,
deferred updates, and `receiveUpdate` hooks. The live test checks repository
state and queries the State Server directly; it does not infer location changes
from an Owner View.

On `CLIENT_OBJECT_LEAVING`, the client repository removes the normal DO through
Direct's `deleteOrDelay()` lifecycle. The Owner View is tracked separately and
is not removed by an ordinary interest leave.

The adapter includes only protocol paths this demo exercises. NetMessenger,
EventLogger, partial database queries, generic database field updates, and
optional DBSS activation fields remain outside this package. Upstream code
attribution and its MIT license are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
