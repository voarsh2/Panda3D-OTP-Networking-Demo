from direct.distributed.DistributedCartesianGrid import DistributedCartesianGrid
from direct.distributed.DistributedCartesianGridAI import DistributedCartesianGridAI
from direct.distributed.DistributedSmoothNode import DistributedSmoothNode
from direct.distributed.DistributedSmoothNodeAI import DistributedSmoothNodeAI
from direct.interval.IntervalGlobal import Sequence
from direct.interval.LerpInterval import LerpPosInterval
from direct.showbase.MessengerGlobal import messenger
from direct.task import Task
from direct.task.TaskManagerGlobal import taskMgr
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
    """Update one server-owned grid-zone set per observing avatar."""

    FIRST_INTEREST_ID = 100

    def __init__(self, air):
        self.air = air
        self._avatars = {}

    def _allocateInterestId(self, state):
        interest_id = state["next_interest_id"]
        reserved_ids = (
            LOGIN_DISTRICT_INTEREST_ID & 0x7FFF,
            LOGIN_WORLD_ROOT_INTEREST_ID & 0x7FFF,
        )
        while interest_id in reserved_ids:
            interest_id += 1
        if interest_id > 0x7FFF:
            raise RuntimeError("server-managed interest ID range exhausted")
        state["next_interest_id"] = interest_id + 1
        # allocates raw IDs from 100; Panda reserves bit 15 for AI interests.
        return interest_id | 0x8000

    def _cleanupAvatar(self, avatar_id, state):
        if state["closing"] and not state["grids"]:
            self._avatars.pop(avatar_id, None)

    def _finishInterest(self, avatar_id, grid_id, state, interest):
        if state["grids"].get(grid_id) is interest:
            state["grids"].pop(grid_id)
        self._cleanupAvatar(avatar_id, state)

    def _interestOperationDone(self, avatar_id, grid_id, handle):
        state = self._avatars.get(avatar_id)
        if state is None:
            return
        interest = state["grids"].get(grid_id)
        if interest is None or interest["handle"] != handle:
            return

        if interest["operation"] == "add":
            interest["zones"] = interest["operation_zones"]
        elif interest["operation"] == "remove":
            interest["zones"] = ()
        else:
            return
        interest["operation"] = None
        interest["operation_zones"] = ()

        if not interest["desired_zones"] and not interest["zones"]:
            self._finishInterest(avatar_id, grid_id, state, interest)
        elif interest["desired_zones"] != interest["zones"]:
            self._scheduleInterestUpdate(avatar_id, grid_id, interest)

    def _scheduleInterestUpdate(self, avatar_id, grid_id, interest):
        if interest["scheduled"]:
            return
        interest["scheduled"] = True
        # callbacks key on handle; add operation contexts to overlap updates.
        taskMgr.add(
            self._runScheduledInterestUpdate,
            f"demo-grid-interest-{avatar_id}-{grid_id}",
            extraArgs=[avatar_id, grid_id, interest["handle"]],
            appendTask=True,
        )

    def _runScheduledInterestUpdate(self, avatar_id, grid_id, handle, _task):
        state = self._avatars.get(avatar_id)
        interest = state["grids"].get(grid_id) if state is not None else None
        if interest is None or interest["handle"] != handle:
            return Task.done
        interest["scheduled"] = False
        self._sendInterestUpdate(avatar_id, grid_id, state, interest)
        return Task.done

    def _sendInterestUpdate(self, avatar_id, grid_id, state, interest):
        if interest["operation"] is not None:
            return
        if interest["desired_zones"] == interest["zones"]:
            if not interest["desired_zones"]:
                self._finishInterest(avatar_id, grid_id, state, interest)
            return

        handle = interest["handle"]
        callback = lambda _channel, _interest_id: self._interestOperationDone(
            avatar_id, grid_id, handle
        )
        if interest["desired_zones"]:
            interest["operation"] = "add"
            interest["operation_zones"] = interest["desired_zones"]
            self.air.client_add_interest_multiple(
                state["client_channel"],
                handle,
                grid_id,
                list(interest["operation_zones"]),
                callback=callback,
            )
        else:
            interest["operation"] = "remove"
            self.air.client_remove_interest(
                state["client_channel"], handle, callback=callback
            )

    def handleLocationChanged(self, grid, avatar, center_zone):
        if not grid.isValidZone(center_zone):
            self.clearAvatarInterest(grid, avatar)
            return

        state = self._avatars.setdefault(
            avatar.doId,
            {
                "client_channel": avatar.client_channel,
                "next_interest_id": self.FIRST_INTEREST_ID,
                "grids": {},
                "closing": False,
            },
        )
        interest = state["grids"].get(grid.doId)
        if interest is None:
            interest = {
                "handle": self._allocateInterestId(state),
                "zones": (),
                "desired_zones": (),
                "operation": None,
                "operation_zones": (),
                "scheduled": False,
            }
            state["grids"][grid.doId] = interest

        wanted = grid_interest_zones(grid, center_zone, grid.gridRadius)
        if wanted == interest["desired_zones"]:
            return
        interest["desired_zones"] = wanted
        self._sendInterestUpdate(avatar.doId, grid.doId, state, interest)

        print(
            f"AI grid interest avatar={avatar.doId} parent={grid.doId} "
            f"center={center_zone} zones={list(wanted)}",
            flush=True,
        )

    def getInterestZones(self, grid, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return ()
        interest = state["grids"].get(grid.doId)
        return interest["desired_zones"] if interest is not None else ()

    def _clearInterest(self, avatar_id, grid_id, state):
        interest = state["grids"].get(grid_id)
        if interest is None:
            return
        if interest["desired_zones"]:
            interest["desired_zones"] = ()
            print(
                f"AI grid interest avatar={avatar_id} parent={grid_id} zones=[]",
                flush=True,
            )
        self._sendInterestUpdate(avatar_id, grid_id, state, interest)

    def clearAvatarInterest(self, grid, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return
        self._clearInterest(avatar.doId, grid.doId, state)

    def clearAvatarInterests(self, avatar):
        state = self._avatars.get(avatar.doId)
        if state is None:
            return
        state["closing"] = True
        for grid_id in tuple(state["grids"]):
            self._clearInterest(avatar.doId, grid_id, state)
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

    def generate(self):
        super().generate()
        self._grid = self.air.doId2do.get(self.parentId)

    def delete(self):
        if self._move_interval is not None:
            self._move_interval.pause()
            self._move_interval = None
        self.stopPosHprBroadcast()
        super().delete()

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
