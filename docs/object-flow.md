# Login and distributed objects

The demo uses one DC contract with client, UberDOG, AI, and Owner View classes. Astron carries messages between those processes; the State Server maintains each generated object's fields and location.

## Login and avatar creation

1. The client completes Astron's hello exchange, then calls `DemoLoginManager.login` with a display name.
2. `DemoLoginManagerUD` moves the Client Agent connection to `ESTABLISHED`, opens the GameGlobals management interest, then opens District main interest after the first completion callback.
3. After the District interest completes, the AI creates the avatar. The default path generates it in District main; the grid path generates it directly in its Cartesian cell. The AI registers it as the client's session object, assigns the client as owner, and sets its AI authority.
4. The owner gets a `DemoAvatarOV`. Other interested clients get the regular `DemoAvatar` view.

The avatar's Owner View sends movement intent with `requestMove`. The Client Agent restricts that call to the owner. The AI validates the direction, updates position, and broadcasts `setPosition`. Clients render the state they receive; they do not choose the authoritative position.

Owner Views live in `doId2ownerView`, separately from the normal client-object map `doId2do`. The demo's client repository handles location messages for both maps so the owner's local view gets updated location metadata without being added to interest tracking.

## DC field permissions

| Field | Direction and flags | Purpose |
|---|---|---|
| `login` | `clsend` | Client requests login through the global login object. |
| `createAvatar` | `airecv` | UberDOG routes avatar creation to the AI. |
| `requestMove` | `ownsend airecv` | Only the owner can send movement intent; AI receives it. |
| `setPosition` | `required broadcast ram` | AI-authored position is sent to interested clients and included at generation. |
| `setActivationCount` | `required broadcast ram db` | Beacon count is sent at generation, replicated at runtime, and stored by DBSS. |

`required` controls initial state sent when an object is generated. `broadcast` sends updates to clients that know the object. `ram` keeps state in the running State Server; `db` also writes the field to the database. `ownsend` and `airecv` constrain who can send and receive a field.

## Source map

| Area | Files |
|---|---|
| DC contract | [`demo/astron/dclass/demo.dc`](../demo/astron/dclass/demo.dc) |
| Client login, input, and interest | [`demo/client.py`](../demo/client.py) |
| Login and session-object setup | [`demo/objects.py`](../demo/objects.py), [`demo/ud_server.py`](../demo/ud_server.py) |
| District, avatar authority, and zone changes | [`demo/objects.py`](../demo/objects.py), [`demo/ai_server.py`](../demo/ai_server.py) |
| Live client-side object inspection | [`demo/inspect.py`](../demo/inspect.py) |
