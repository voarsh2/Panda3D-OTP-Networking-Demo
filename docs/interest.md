# Zones and interest

## Interest paths in this repo

| Path | Requester | Scope |
|---|---|---|
| Login bootstrap | UberDOG through ClientAgent | GameGlobals management zone, then District main zone |
| Fixed District zones | Client | A whole District zone; Tab toggles zone 2 |
| Client-local grid | Client | Current grid cell and its neighbors, based on the Owner View position |
| AI-managed grid | AI through ClientAgent | Current grid cell and its neighbors, based on the avatar's server-side location |

The grid paths are optional and can run independently. Compare their commands and lifecycle in [the Cartesian grid guide](cartesian-grid.md). The AI-managed path waits for ClientAgent interest-completion callbacks before resuming grid-child movement.

## Fixed District zones

The District is the parent of the demo's avatars and beacon. It uses two fixed zones:

| Zone | Contents | Client interest |
|---|---|---|
| `1` | Main area and newly created avatars | Opened when the District arrives |
| `2` | Lab area, saved beacon, and avatars that cross the boundary | Toggled with **Tab**; opened automatically by `demo.inspect` |

Interest is a client's request to receive objects in a parent/zone location. It does not move an object. The AI moves an avatar between the two locations when its authoritative X position crosses `4`, using `b_setLocation`. Astron's State Server then updates the object's location and applies each client's interest.

The owning client keeps a `DemoAvatarOV` in `doId2ownerView`, outside the normal interest-tracked `doId2do` map. That is why your own avatar stays visible when a remote avatar or grid probe leaves interest. In grid mode, Tab adds or removes a separate whole-zone interest for District zone 2; it does not replace the grid's cell window.

This separates two kinds of update:

- `setPosition` is a DC field update: interested clients that know the avatar receive its new coordinates.
- `b_setLocation` changes the distributed object's parent/zone: clients may receive a location update, generate the object, or disable it as it enters or leaves their interest.

Try it with two normal clients. Both start interested in zone 1. Move Alice past **x = 4** and Bob loses her avatar; press **Tab** in Bob's client and it enters view in zone 2. Move Alice back below the boundary and the reverse happens. The default inspector watches both zones and prints the avatar's actual location change. Run it with `--main-only` to observe the object leaving zone 1 instead.

The boundary is deliberately fixed and the interest is manually toggled. This demonstrates State Server location and interest behavior; it is not automatic proximity or grid interest. To observe a client that is interested only in the main area, run `python -m demo.inspect --main-only --name MainOnly`.
