# Grid-aware smoothing in `disney_stable`

The `disney_stable` Panda3D branch carries an embedded grid-cell value (`E`) with
SmoothNode movement telemetry. This is a historical source note; the demo does
not implement this path.

## How the path works

1. When `E` changes, the C++ broadcaster sends a full `setSmPosHprE` update
   with position and HPR.
2. The receiving `DistributedSmoothNode.setSmPosHprE()` calls
   `transformTelemetry()` before recording the new sample.
3. `SmoothGridChild.transformTelemetry()` changes the grid cell and reparents
   the node before the sample enters the smoother.
4. `SmoothMover` stores the embedded value with each sample and rebases stored
   positions when the parent changes.

This keeps the coordinate-space identifier with the sample during a cell
crossing. It does not make Astron's State Server location update atomic with the
client's scene graph, and it does not replace interest management.

## Relation to this demo

The optional grid example here uses Panda3D's current Cartesian-grid classes and
`L` telemetry. It demonstrates cell transitions and interest changes; it does
not implement `E` or the historical `SmoothMover` reparenting path. See the
[Cartesian grid guide](cartesian-grid.md).

## Source map

The public `disney_stable` mirror is pinned to commit [`0611d49`](https://github.com/toontownretro/panda3d-CVS/tree/0611d497f6759ab2920497c078ef0eb99c243638).

- [C++ broadcaster](https://github.com/toontownretro/panda3d-CVS/blob/0611d497f6759ab2920497c078ef0eb99c243638/direct/src/distributed/cDistributedSmoothNodeBase.cxx#L124-L140) sends the embedded value with the positional update.
- [GridChild.py](https://github.com/toontownretro/panda3d-CVS/blob/0611d497f6759ab2920497c078ef0eb99c243638/direct/src/distributed/GridChild.py#L150-L192) handles the cell change before smoothing.
- [DistributedSmoothNode.py](https://github.com/toontownretro/panda3d-CVS/blob/0611d497f6759ab2920497c078ef0eb99c243638/direct/src/distributed/DistributedSmoothNode.py#L274-L295) applies telemetry after the transform hook.
- [SmoothMover](https://github.com/toontownretro/panda3d-CVS/blob/0611d497f6759ab2920497c078ef0eb99c243638/direct/src/deadrec/smoothMover.cxx#L762-L805) rebases its position history on reparent.
