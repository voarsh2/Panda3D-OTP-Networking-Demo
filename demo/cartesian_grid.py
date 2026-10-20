from direct.distributed.DistributedCartesianGrid import DistributedCartesianGrid
from direct.distributed.DistributedCartesianGridAI import DistributedCartesianGridAI
from direct.distributed.DistributedSmoothNode import DistributedSmoothNode
from direct.distributed.DistributedSmoothNodeAI import DistributedSmoothNodeAI
from direct.interval.IntervalGlobal import Sequence
from direct.interval.LerpInterval import LerpPosInterval
from direct.showbase.MessengerGlobal import messenger
from panda3d.core import Point3, TextNode

from demo.constants import (
    DISTRICT_ID,
    LOGIN_DISTRICT_INTEREST_ID,
    LOGIN_WORLD_ROOT_INTEREST_ID,
    MAIN_ZONE,
    OUTSIDE_GRID_ZONE,
)
from demo.objects import DemoAvatarAI

CARTESIAN_GRID_ID = 5001
GRID_STARTING_ZONE = 6000
GRID_SIZE = 8
GRID_RADIUS = 1
GRID_CELL_WIDTH = 4


def grid_cell_location(grid, x, y):
    if not _grid_contains(grid, x, y):
        raise ValueError(f"position {(x, y)} is outside the Cartesian grid")
    zone_id = int(grid.getZoneFromXYZ((x, y, 0)))
    if not grid.isValidZone(zone_id):
        raise ValueError(f"position {(x, y)} is outside the Cartesian grid")
    origin_x, origin_y, _ = grid.getZoneCellOrigin(zone_id)
    return zone_id, (float(x - origin_x), float(y - origin_y))


def grid_interest_window(grid, position):
    if not _grid_contains(grid, position[0], position[1]):
        return None, ()
    center = int(grid.getZoneFromXYZ(position))
    if not grid.isValidZone(center):
        return None, ()

    return center, grid_interest_zones(grid, center, grid.viewingRadius)


def grid_interest_zones(grid, center, radius):
    if not grid.isValidZone(center):
        return ()
    zones = {int(center)}
    for ring in range(1, int(radius) + 1):
        zones.update(grid.getConcentricZones(center, ring))
    zones = {zone for zone in zones if grid.isValidZone(zone)}
    return tuple(sorted(zones))


def _grid_contains(grid, x, y):
    half_extent = grid.gridSize * grid.cellWidth / 2
    return -half_extent <= x < half_extent and -half_extent <= y < half_extent


class DemoWorldGridManagerAI:
    """Open and close a player's grid-cell interests from the AI server."""

    FIRST_INTEREST_ID = 0x8000

    def __init__(self, air):
        self.air = air
        self._avatars = {}

    def hasPendingInterests(self, grid):
        return self.hasPendingInterestsForId(grid.doId)

    def hasPendingInterestsForId(self, grid_id):
        # This teaching demo uses one grid-wide barrier for all observers.
        return any(
            state["pending_adds"].get(grid_id)
            or state["pending_removes"].get(grid_id)
            for state in self._avatars.values()
        )

    def _allocateHandle(self, state):
        while True:
            handle = state["next_handle"]
            state["next_handle"] += 1
            if state["next_handle"] > 0xFFFF:
                state["next_handle"] = self.FIRST_INTEREST_ID
            if handle not in state["allocated_handles"] and handle not in (
                LOGIN_DISTRICT_INTEREST_ID,
                LOGIN_WORLD_ROOT_INTEREST_ID,
            ):
                state["allocated_handles"].add(handle)
                return handle

    def _cleanupAvatar(self, avatar_id, state):
        if (
            not state["grids"]
            and not any(state["pending_adds"].values())
            and not any(state["pending_removes"].values())
            and not state["retire_after_add"]
            and not state["retiring_handles"]
        ):
            self._avatars.pop(avatar_id, None)

    def _removeInterest(self, avatar_id, grid_id, state, handle):
        state["pending_removes"].setdefault(grid_id, set()).add(handle)
        state["retiring_handles"].add(handle)
        self.air.client_remove_interest(
            state["client_channel"],
            handle,
            callback=lambda _channel, _interest_id, avatar_id=avatar_id,
            grid_id=grid_id, interest_id=handle: self._interestRemoved(
                avatar_id, grid_id, interest_id
            ),
        )

    def _notifyReadyIfComplete(self, grid_id):
        if self.hasPendingInterestsForId(grid_id):
            return
        grid = self.air.doId2do.get(grid_id)
        if grid is not None:
            grid.interestSnapshotReady()

    def _interestAdded(self, avatar_id, grid_id, handle):
        state = self._avatars.get(avatar_id)
        if state is None:
            return
        pending = state["pending_adds"].get(grid_id)
        if pending is not None:
            pending.discard(handle)
            if not pending:
                state["pending_adds"].pop(grid_id, None)

        if handle in state["retire_after_add"]:
            state["retire_after_add"].discard(handle)
            self._removeInterest(avatar_id, grid_id, state, handle)
        self._notifyReadyIfComplete(grid_id)
        self._cleanupAvatar(avatar_id, state)

    def _interestRemoved(self, avatar_id, grid_id, handle):
        state = self._avatars.get(avatar_id)
        if state is None:
            return
        pending = state["pending_removes"].get(grid_id)
        if pending is not None:
            pending.discard(handle)
            if not pending:
                state["pending_removes"].pop(grid_id, None)
        state["retiring_handles"].discard(handle)
        state["allocated_handles"].discard(handle)
        self._notifyReadyIfComplete(grid_id)
        self._cleanupAvatar(avatar_id, state)

    def handleLocationChanged(self, grid, avatar, center_zone):
        if not grid.isValidZone(center_zone):
            self.clearAvatarInterest(grid, avatar)
            return

        state = self._avatars.setdefault(
            avatar.doId,
            {
                "client_channel": avatar.client_channel,
                "next_handle": self.FIRST_INTEREST_ID,
                "grids": {},
                "pending_adds": {},
                "pending_removes": {},
                "retire_after_add": set(),
                "retiring_handles": set(),
                "allocated_handles": set(),
            },
        )
        handles = state["grids"].setdefault(grid.doId, {})
        wanted = set(grid_interest_zones(grid, center_zone, grid.gridRadius))
        added = wanted - set(handles)
        removed = set(handles) - wanted
        if not added and not removed:
            return
        grid.interestSnapshotPending()

        for zone_id in sorted(added):
            handle = self._allocateHandle(state)
            handles[zone_id] = handle
            state["pending_adds"].setdefault(grid.doId, set()).add(handle)
            self.air.clientAddInterest(
                state["client_channel"],
                handle,
                grid.doId,
                zone_id,
                callback=lambda _channel, _interest_id, avatar_id=avatar.doId,
                grid_id=grid.doId, interest_id=handle: self._interestAdded(
                    avatar_id, grid_id, interest_id
                ),
            )

        for zone_id in sorted(removed):
            handle = handles.pop(zone_id)
            if handle in state["pending_adds"].get(grid.doId, ()):
                state["retire_after_add"].add(handle)
            else:
                self._removeInterest(avatar.doId, grid.doId, state, handle)
        if not handles:
            del state["grids"][grid.doId]
        if not state["grids"]:
            self._cleanupAvatar(avatar.doId, state)

        print(
            f"AI grid interest avatar={avatar.doId} parent={grid.doId} "
            f"center={center_zone} zones={sorted(wanted)}",
            flush=True,
        )

    def getInterestZones(self, grid, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return ()
        return tuple(sorted(state["grids"].get(grid.doId, {})))

    def clearAvatarInterest(self, grid, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return
        handles = state["grids"].pop(grid.doId, {})
        if handles:
            grid.interestSnapshotPending()
        for handle in handles.values():
            if handle in state["pending_adds"].get(grid.doId, ()):
                state["retire_after_add"].add(handle)
            else:
                self._removeInterest(avatar.doId, grid.doId, state, handle)
        if not state["grids"]:
            self._cleanupAvatar(avatar.doId, state)
        if not handles:
            return
        print(
            f"AI grid interest avatar={avatar.doId} parent={grid.doId} "
            "zones=[]",
            flush=True,
        )

    def clearAvatarInterests(self, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return
        for grid_id in tuple(state["grids"]):
            grid = self.air.doId2do.get(grid_id)
            if grid is None:
                handles = state["grids"].pop(grid_id)
                for handle in handles.values():
                    if handle in state["pending_adds"].get(grid_id, ()):
                        state["retire_after_add"].add(handle)
                    else:
                        self._removeInterest(avatar.doId, grid_id, state, handle)
            else:
                self.clearAvatarInterest(grid, avatar)
        self._cleanupAvatar(avatar.doId, state)


class DemoCartesianGrid(DistributedCartesianGrid):
    def generate(self):
        super().generate()
        if self.getParent().isEmpty():
            self.reparentTo(render)

    def announceGenerate(self):
        super().announceGenerate()
        messenger.send("demo-cartesian-grid-generated", [self])


class DemoCartesianGridAI(DistributedCartesianGridAI):
    def __init__(self, air):
        super().__init__(
            air,
            GRID_STARTING_ZONE,
            GRID_SIZE,
            GRID_RADIUS,
            GRID_CELL_WIDTH,
        )
        self._paused_grid_objects = set()
        self._grid_update_paused = False

    def interestSnapshotReady(self):
        for child in tuple(self._paused_grid_objects):
            self._paused_grid_objects.discard(child)
            if not child.isEmpty():
                child.resumeAfterInterest()
        if self._grid_update_paused:
            self._grid_update_paused = False
            if self.gridObjects:
                self.startUpdateGridTask()
        print(f"AI grid interests ready for grid={self.doId}.", flush=True)

    def interestSnapshotPending(self):
        if self.updateTaskStarted:
            self.stopUpdateGridTask()
            self._grid_update_paused = True
        for child in tuple(self.gridObjects.values()):
            if hasattr(child, "pauseForInterest"):
                child.pauseForInterest()
                self._paused_grid_objects.add(child)

    def handleChildArrive(self, child, zone_id):
        super().handleChildArrive(child, zone_id)
        if isinstance(child, DemoAvatarAI):
            if child.doId not in self.gridObjects:
                self.addObjectToGrid(child, useZoneId=zone_id)
            manager = self.air.worldGridManager
            if manager is not None and child.isGenerated():
                manager.handleLocationChanged(self, child, zone_id)

    def handleChildArriveZone(self, child, zone_id):
        super().handleChildArriveZone(child, zone_id)
        if isinstance(child, DemoAvatarAI):
            manager = self.air.worldGridManager
            if manager is not None:
                manager.handleLocationChanged(self, child, zone_id)

    def handleChildLeave(self, child, zone_id):
        if isinstance(child, DemoAvatarAI):
            if child.doId in self.gridObjects:
                self.removeObjectFromGrid(child)
            manager = self.air.worldGridManager
            if manager is not None:
                manager.clearAvatarInterest(self, child)
        super().handleChildLeave(child, zone_id)

    def handleAvatarZoneChange(self, avatar, useZoneId=-1):
        if isinstance(avatar, DemoAvatarAI):
            position = avatar.getPos(self)
            x, y = position[0], position[1]
            if not _grid_contains(self, x, y):
                if avatar.parentId == self.doId:
                    avatar.b_setLocation(DISTRICT_ID, OUTSIDE_GRID_ZONE)
                return

        result = super().handleAvatarZoneChange(avatar, useZoneId)
        if (
            isinstance(avatar, DemoAvatarAI)
            and avatar.parentId == self.doId
            and avatar.isGenerated()
        ):
            manager = self.air.worldGridManager
            if manager is not None:
                manager.handleLocationChanged(self, avatar, avatar.zoneId)
        return result

class DemoGridProbe(DistributedSmoothNode):
    def __init__(self, cr):
        super().__init__(cr)
        self.name = "Grid probe"
        self.model = None
        self.label = None

    def generate(self):
        super().generate()
        if self.model is None:
            self.model = base.loader.loadModel("models/misc/sphere")
            self.model.setScale(0.45)
            self.model.setColor(0.75, 0.3, 1.0, 1.0)
            self.model.reparentTo(self)
        self.setName(self.name)

    def disable(self):
        if self.model is not None:
            self.model.detachNode()
        super().disable()
        messenger.send("demo-grid-probe-left-view", [self])

    def delete(self):
        if self.model is not None:
            self.model.removeNode()
            self.model = None
            self.label = None
        super().delete()

    def setName(self, name):
        self.name = name
        if self.model is not None:
            if self.label is None:
                text = TextNode("grid-probe-label")
                self.label = self.model.attachNewNode(text)
                self.label.setZ(1.0)
                self.label.setScale(0.16)
                self.label.setBillboardPointEye()
                self.label.setColor(1, 1, 1, 1)
            self.label.node().setText(name)

    def setLocation(self, parent_id, zone_id):
        old_parent, old_zone = self.parentId, self.zoneId
        super().setLocation(parent_id, zone_id)
        if self.isGenerated() and (old_parent, old_zone) != (parent_id, zone_id):
            messenger.send(
                "demo-grid-probe-location-changed",
                [self, old_parent, old_zone],
            )

    def announceGenerate(self):
        super().announceGenerate()
        messenger.send("demo-grid-probe-generated", [self])


class DemoGridProbeAI(DistributedSmoothNodeAI):
    SPEED = 3.0

    def __init__(self, air):
        super().__init__(air)
        self.name = "Cell patrol"
        self._grid = None
        self._move_interval = None
        self._interest_paused = False

    def generate(self):
        super().generate()
        self._grid = self.air.doId2do.get(self.parentId)

    def delete(self):
        if self._move_interval is not None:
            self._move_interval.pause()
            self._move_interval = None
        self.stopPosHprBroadcast()
        self._interest_paused = False
        super().delete()

    def pauseForInterest(self):
        if self._interest_paused:
            return
        self._interest_paused = True
        if self._move_interval is not None:
            self._move_interval.pause()
        self.stopPosHprBroadcast()

    def resumeAfterInterest(self):
        if not self._interest_paused:
            return
        self._interest_paused = False
        if self._move_interval is not None:
            self._move_interval.resume()
        if self.air.doId2do.get(self.doId) is self:
            self.startPosHprBroadcast(period=0.2)

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def start_patrol(self, grid, min_x, max_x, start_x, start_y):
        self._grid = grid
        start = Point3(start_x, start_y, 0.7)
        minimum = Point3(min_x, start_y, 0.7)
        maximum = Point3(max_x, start_y, 0.7)
        duration = (max_x - min_x) / self.SPEED
        self._move_interval = Sequence(
            LerpPosInterval(
                self,
                duration,
                maximum,
                startPos=start,
                other=grid,
            ),
            LerpPosInterval(
                self,
                duration,
                minimum,
                startPos=maximum,
                other=grid,
            ),
            name=self.uniqueName("grid-patrol"),
        )
        self._move_interval.loop()
        self.startPosHprBroadcast(period=0.2)


def create_cartesian_grid(air, parent_id=DISTRICT_ID, parent_zone=MAIN_ZONE):
    grid = DemoCartesianGridAI(air)
    grid.generateWithRequiredAndId(CARTESIAN_GRID_ID, parent_id, parent_zone)
    air.setAI(grid.doId, air.ourChannel)

    start_x, y = -10.0, 2.0
    zone_id, _ = grid_cell_location(grid, start_x, y)
    probe = DemoGridProbeAI(air)
    probe.setName("Cell patrol")
    probe.reparentTo(grid)
    probe.setPos(start_x, y, 0.7)
    probe.generateWithRequiredAndId(air.allocateChannel(), grid.doId, zone_id)
    air.setAI(probe.doId, air.ourChannel)
    grid.addObjectToGrid(probe, zone_id)
    probe.start_patrol(grid, -10.0, 10.0, start_x, y)

    print(
        f"Cartesian grid {grid.doId}: start={grid.startingZone} size={grid.gridSize} "
        f"radius={grid.gridRadius} cellWidth={grid.cellWidth}; "
        f"probe {probe.doId} starts in zone {zone_id}.",
        flush=True,
    )
    return grid
