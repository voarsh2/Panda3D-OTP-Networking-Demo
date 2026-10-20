# Zones and interest

In OTP/Astron, an object's **location** is its parent and zone. A client's **interest** selects the parent/zone locations it wants to see. Together, location and interest determine which objects are generated, updated, or disabled for a client. A zone number is scoped by its parent: District zone `2` and Grid zone `2` are different locations.

## The interest models differ

Both stacks use interest to keep clients from receiving updates about objects outside their selected zones. The difference is where the audience, routing, and current object state are maintained.

| Area | Stock CMU `ClientRepository` / `ServerRepository` | OTP/Astron |
|---|---|---|
| Interest scope | One flat list of zone IDs per client. | Each interest ID names a parent object and a set of child zones; multiple interests may overlap. |
| Broadcast audience | `ServerRepository` keeps a zone-to-client set and sends each broadcast to the other clients in that set. | The ClientAgent subscribes to parent/zone location channels; the Message Director routes channel messages to subscribers. |
| State on entry | The server tracks object ID, class, and zone, but not current field values. On zone entry, object owners send their generate data. | The State Server keeps live `ram` fields and locations, and supplies the current object snapshot when an interest opens. |
| Interest control | The client sends its zone list; the server also includes zones with that client's own objects. | The client can manage interest subject to the ClientAgent's `add_interest` policy; game AI can request interest changes separately. |

The key distinction is not whether zones filter traffic: both stacks do that. Stock CMU performs per-zone fan-out in `ServerRepository`; Astron uses ClientAgent location subscriptions and Message Director pub/sub, with current state and snapshots in the State Server. Only Astron supplies that service split out of the box.

## How Astron routes interest traffic

When an interest opens, the ClientAgent subscribes to location channels for newly covered `(parent, zone)` pairs and asks the State Server for existing objects there. The State Server returns their current state; the ClientAgent sends generates to the client and reports when the snapshot is complete. If another interest already covers a pair, Astron shares that subscription.

For later updates, the AI sends a field change to the object's State Server channel. The State Server stores `ram` values and publishes `broadcast` fields to the object's current location channel. The Message Director delivers the update to ClientAgents subscribed to that location. A location change publishes to the old and new location channels, so clients can disable or generate the object according to their interests. Removing an interest unsubscribes only from locations no other open interest still covers.

Interest limits the audience to selected locations; it does not reduce updates for objects inside those locations. Zone size, interest radius, and field update frequency still affect traffic.

Interest is an audience filter, not a scheduler: it does not choose an AI shard or redistribute simulation work. See [scaling and load distribution](object-flow.md#scaling-and-load-distribution).

See Astron's [Message Director](https://github.com/Astron/Astron/blob/master/docs/protocol/19-messagedirector.md), [ClientAgent](https://github.com/Astron/Astron/blob/master/docs/protocol/11-clientagent.md), and [State Server](https://github.com/Astron/Astron/blob/master/docs/protocol/12-stateserver.md) protocol notes for these message flows.

## Interest paths in this repo

| Path | Requester | Scope |
|---|---|---|
| Login bootstrap | UberDOG through ClientAgent | GameGlobals management zone, then District main zone |
| Fixed District zones | Client | A whole District zone; Tab toggles zone 2 |
| Client-local grid | Client | Current grid cell and its neighbors, based on the Owner View position |
| AI-managed grid | AI through ClientAgent | Current grid cell and its neighbors, based on the avatar's server-side location |

The grid paths are optional and can run independently. Compare their commands and lifecycle in [the Cartesian grid guide](cartesian-grid.md). AI-managed mode keeps a server-owned cell-window interest per observer.

In a larger world, a grid-interest manager has to keep this window separately for each observer and grid, update it as the avatar crosses cells, wait for asynchronous interest completions, and clear it when the avatar leaves that grid. This demo shows one such window and its lifecycle; it does not claim that Cartesian grids or zone interests are unique to Astron.

## Multiple interest layers

Interests are independent, so a client can hold more than one at a time. Login opens the GameGlobals management and District main interests. The optional grid adds an interest under the Cartesian Grid object for its cell window. **Tab** adds a separate interest under the District for zone 2; it does not replace the grid interest or make the lab another grid. Client-local and AI-managed describe who moves the grid-cell window, not different kinds of zone.

The owner's `DemoAvatarOV` is outside the normal `doId2do` interest map. In this demo it renders the local avatar and sends movement input; other clients receive their own `DemoAvatar` through interest. The local visual can therefore remain while the owner's grid-cell interest changes.

## Fixed District zones

The District is the parent of the demo's avatars and beacon. It uses two fixed zones:

| Zone | Contents | Client interest |
|---|---|---|
| `1` | Main area and newly created avatars | Opened when the District arrives |
| `2` | Lab area, saved beacon, and avatars that cross the boundary | Toggled with **Tab**; opened automatically by `demo.inspect` |

The AI moves an avatar between the two locations when its authoritative X position crosses `4`, using `b_setLocation`. Astron's State Server then updates the object's location and applies each client's interest.

This separates two kinds of update:

- `setPosition` is a DC field update: interested clients that know the avatar receive its new coordinates.
- `b_setLocation` changes the distributed object's parent/zone: clients may receive a location update, generate the object, or disable it as it enters or leaves their interest.

Try it with two normal clients. Both start interested in zone 1. Move Alice past **x = 4** and Bob loses her avatar; press **Tab** in Bob's client and it enters view in zone 2. Move Alice back below the boundary and the reverse happens. The default inspector watches both zones and prints the avatar's actual location change. Run it with `--main-only` to observe the object leaving zone 1 instead.

The boundary is deliberately fixed and the interest is manually toggled. This demonstrates State Server location and interest behavior; it is not automatic proximity or grid interest. To observe a client that is interested only in the main area, run `python -m demo.inspect --main-only --name MainOnly`.
