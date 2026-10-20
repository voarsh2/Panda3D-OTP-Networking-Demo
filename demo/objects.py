from direct.distributed.DistributedObject import DistributedObject
from direct.distributed.DistributedObjectAI import DistributedObjectAI
from direct.distributed.DistributedObjectGlobal import DistributedObjectGlobal
from direct.distributed.DistributedObjectGlobalUD import DistributedObjectGlobalUD
from direct.distributed.DistributedObjectOV import DistributedObjectOV
from direct.distributed.DistributedObjectUD import DistributedObjectUD
from direct.distributed.DistributedNode import DistributedNode
from direct.distributed.DistributedNodeAI import DistributedNodeAI
from direct.showbase.MessengerGlobal import messenger
from direct.showbase.ShowBaseGlobal import globalClock
from direct.task import Task
from demo.constants import (
    DISTRICT_ID,
    GAME_ROOT_ID,
    LAB_ZONE,
    MAIN_ZONE,
    MANAGEMENT_ZONE,
    OUTSIDE_GRID_ZONE,
    LOGIN_DISTRICT_INTEREST_ID,
    LOGIN_WORLD_ROOT_INTEREST_ID,
    ZONE_CROSSING_X,
)
from panda3d.core import TextNode


class DemoLoginManager(DistributedObjectGlobal):
    def login(self, name):
        self.sendUpdate("login", [name])


# DC import mappings require this base view; clients use GameGlobalsId directly.
class DemoGameRoot(DistributedObject):
    pass


class DemoLoginManagerUD(DistributedObjectGlobalUD):
    def set_district(self, district):
        self.district = district

    def login(self, name):
        client_channel = self.air.get_msg_sender()
        name = (name or "Guest").strip()[:20] or "Guest"
        self.air.setClientState(client_channel, 2)  # Astron: ESTABLISHED
        print(f"Login accepted for {name} on channel {client_channel}.", flush=True)

        def create_avatar(*_):
            self.district.create_avatar(client_channel, name)

        def open_district(*_):
            self.air.clientAddInterest(
                client_channel,
                LOGIN_DISTRICT_INTEREST_ID,
                DISTRICT_ID,
                MAIN_ZONE,
                callback=create_avatar,
            )

        self.air.clientAddInterest(
            client_channel,
            LOGIN_WORLD_ROOT_INTEREST_ID,
            GAME_ROOT_ID,
            MANAGEMENT_ZONE,
            callback=open_district,
        )


class DemoGameRootUD(DistributedObjectUD):
    pass


class DemoDistrict(DistributedObject):
    def __init__(self, cr):
        super().__init__(cr)
        self.parenting_rules = ("fixed-zones", "1:2")
        self.name = "Demo District"
        self.main_interest = None

    def setName(self, name):
        self.name = name

    def setParentingRules(self, style, rule):
        self.parenting_rules = (style, rule)

    def announceGenerate(self):
        self.main_interest = self.cr.addInterest(
            self.doId, [MAIN_ZONE], "demo district main zone"
        )
        messenger.send("demo-district-generated", [self])

    def delete(self):
        if self.main_interest is not None:
            self.cr.removeInterest(self.main_interest)
            self.main_interest = None
        super().delete()


class DemoDistrictAI(DistributedObjectAI):
    def __init__(self, air):
        super().__init__(air)
        self._spawn_count = 0
        self.cartesian_grid = None
        self.parenting_rules = ("fixed-zones", "1:2")
        self.name = "Demo District"

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def getParentingRules(self):
        return self.parenting_rules

    def setParentingRules(self, style, rule):
        self.parenting_rules = (style, rule)

    def createAvatar(self, client_channel, name):
        avatar = DemoAvatarAI(self.air)
        grid = self.cartesian_grid
        spacing = 4.0 if grid is not None else 2.0
        x = -2.0 + spacing * self._spawn_count
        y = 2.0 if grid is not None else 0.0
        avatar.setName(name)
        avatar.cartesian_grid = grid
        if grid is not None:
            avatar.reparentTo(grid)
        avatar.setPosition(x, y)
        avatar.client_channel = client_channel
        avatar.grid_interest_manager = self.air.worldGridManager
        avatar.movement_limit = 20.0 if grid is not None else DemoAvatarAI.LIMIT
        self._spawn_count += 1

        do_id = self.air.allocateChannel()
        if grid is None:
            parent_id, spawn_zone = self.doId, MAIN_ZONE
        else:
            parent_id = grid.doId
            spawn_zone = int(grid.getZoneFromXYZ((x, y, 0.0)))
        avatar.generateWithRequiredAndId(do_id, parent_id, spawn_zone)
        self.air.setAI(do_id, self.air.ourChannel)
        self.air.clientAddSessionObject(client_channel, do_id)
        self.air.setOwner(do_id, client_channel)
        if grid is not None:
            if do_id not in grid.gridObjects:
                grid.addObjectToGrid(avatar, useZoneId=spawn_zone)
            manager = self.air.worldGridManager
            if manager is not None:
                manager.handleLocationChanged(grid, avatar, spawn_zone)
        print(f"Created avatar {name} ({do_id}) in district {self.doId}.", flush=True)

class DemoDistrictUD(DistributedObjectUD):
    def create_avatar(self, client_channel, name):
        self.sendUpdate("createAvatar", [client_channel, name])


class DemoAvatar(DistributedNode):
    def __init__(self, cr):
        super().__init__(cr)
        self.name = ""
        self.model = None
        self.name_label = None
        self.name_text = None
        self._left_view_reported = False

    def generate(self):
        super().generate()
        self._left_view_reported = False
        if self.model is None:
            self.model = base.loader.loadModel("models/misc/sphere")
            self.model.setScale(0.8)
            self.model.setColor(0.25, 0.65, 1.0, 1.0)
        self.model.reparentTo(self)
        self.model.setPos(0, 0, 0.8)
        if self.gridParent is None:
            self.reparentTo(base.render)
        self.setName(self.name)

    def disable(self):
        if not self._left_view_reported:
            self._left_view_reported = True
            messenger.send("demo-avatar-left-view", [self])
        if self.model is not None:
            self.model.detachNode()
        super().disable()

    def delete(self):
        if self.model is not None:
            self.model.removeNode()
            self.model = None
            self.name_label = None
            self.name_text = None
        super().delete()

    def setName(self, name):
        self.name = name
        if self.model is not None:
            if self.name_label is None:
                self.name_text = TextNode("avatar-name")
                self.name_label = self.model.attachNewNode(self.name_text)
                self.name_label.setZ(1.4)
                self.name_label.setScale(0.2)
                self.name_label.setBillboardPointEye()
                self.name_label.setColor(1, 1, 1, 1)
            self.name_text.setText(name)

    def setPosition(self, x, y):
        parent = self.cr.doId2do.get(self.parentId)
        if parent is not None and parent.isGridParent():
            self.setPos(parent, x, y, 0.8)
        else:
            self.setPos(x, y, 0.8)

    def setLocation(self, parent_id, zone_id):
        old_location = (self.parentId, self.zoneId)
        # _deactivateDO calls setLocation(0, 0) even when no NodePath was attached.
        if self.isEmpty():
            return super().setLocation(parent_id, zone_id)
        world_pos = self.getPos(base.render)
        super().setLocation(parent_id, zone_id)
        parent = self.cr.doId2do.get(parent_id)
        if (
            (parent is None or not parent.isGridParent())
            and self.getParent().isEmpty()
        ):
            self.reparentTo(base.render)
            self.setPos(base.render, world_pos)
        # Initial generation sets location before the object is fully generated.
        if self.isGenerated() and old_location != (parent_id, zone_id):
            messenger.send(
                "demo-avatar-location-changed",
                [self, *old_location, parent_id, zone_id],
            )

    def announceGenerate(self):
        super().announceGenerate()
        messenger.send("demo-avatar-generated", [self])


class DemoAvatarOV(DistributedObjectOV):
    """Render the local session avatar; remote clients use DemoAvatar."""

    def __init__(self, cr):
        super().__init__(cr)
        self.avatar = DemoAvatar(cr)
        self.last_position = (0.0, 0.0)

    def generateInit(self):
        self.avatar.doId = self.doId
        messenger.send("demo-avatar-owner", [self])

    def generate(self):
        self.avatar.generate()

    def delete(self):
        if self.avatar.model is not None:
            self.avatar.model.removeNode()
            self.avatar.model = None
        super().delete()

    def setName(self, name):
        self.avatar.setName(name)

    def setPosition(self, x, y):
        self.last_position = (float(x), float(y))
        self.avatar.setPosition(x, y)
        messenger.send("demo-owner-avatar-position", [float(x), float(y)])

    def requestMove(self, dx, dy):
        self.sendUpdate("requestMove", [dx, dy])


class DemoAvatarAI(DistributedNodeAI):
    SPEED = 4.0
    LIMIT = 8.0

    def __init__(self, air):
        super().__init__(air)
        self.name = "Guest"
        self.x = 0.0
        self.y = 0.0
        self.dx = 0
        self.dy = 0
        self._move_task = None
        self._interest_paused = False
        self.client_channel = None
        self.cartesian_grid = None
        self.grid_interest_manager = None
        self.movement_limit = self.LIMIT

    def generate(self):
        super().generate()
        self._move_task = base.taskMgr.add(
            self._update_position, self.uniqueName("move")
        )

    def delete(self):
        if self.grid_interest_manager is not None:
            self.grid_interest_manager.clearAvatarInterests(self)
        if self._move_task is not None:
            base.taskMgr.remove(self._move_task)
            self._move_task = None
        self._interest_paused = False
        super().delete()

    def pauseForInterest(self):
        if self._interest_paused:
            return
        self._interest_paused = True
        if self._move_task is not None:
            base.taskMgr.remove(self._move_task)
            self._move_task = None

    def resumeAfterInterest(self):
        if not self._interest_paused:
            return
        self._interest_paused = False
        if self.air.doId2do.get(self.doId) is self:
            self._move_task = base.taskMgr.add(
                self._update_position, self.uniqueName("move")
            )

    def getName(self):
        return self.name

    def getPosition(self):
        return self.x, self.y

    def setName(self, name):
        self.name = name

    def b_setName(self, name):
        self.setName(name)
        self.sendUpdate("setName", [name])

    def setPosition(self, x, y):
        x = float(x)
        y = float(y)
        if (
            self.cartesian_grid is not None
            and self.parentId == self.cartesian_grid.doId
        ):
            grid_parent = self.gridParent
            if (
                self.getParent().isEmpty()
                or grid_parent is None
                or grid_parent.grid is not self.cartesian_grid
            ):
                return False
            self.setPos(self.cartesian_grid, x, y, 0.8)
        else:
            self.setPos(x, y, 0.8)
        self.x, self.y = x, y
        return True

    def b_setPosition(self, x, y):
        if self.setPosition(x, y) is False:
            return
        # Publish the grid-root pose before changing location. The new
        # location then generates late observers with this current RAM value.
        self.sendUpdate("setPosition", [self.x, self.y])
        if self.cartesian_grid is None:
            zone_id = LAB_ZONE if self.x >= ZONE_CROSSING_X else MAIN_ZONE
            if zone_id != self.zoneId:
                self.b_setLocation(self.parentId, zone_id)
        elif self.parentId != self.cartesian_grid.doId:
            zone_id = int(self.cartesian_grid.getZoneFromXYZ((self.x, self.y, 0.0)))
            if self.cartesian_grid.isValidZone(zone_id):
                self.b_setLocation(self.cartesian_grid.doId, zone_id)

    def setLocation(self, parent_id, zone_id):
        parent = self.air.doId2do.get(parent_id)
        if parent is not None and parent.isGridParent():
            # GridParent preserves the pose during a cell change. A second
            # grid-root write here can reapply a transient crossing position.
            return super().setLocation(parent_id, zone_id)

        world_pos = self.getPos(base.render)
        super().setLocation(parent_id, zone_id)
        if self.getParent().isEmpty():
            self.reparentTo(base.render)
            self.setPos(base.render, world_pos)

    def requestMove(self, dx, dy):
        # The ClientAgent checks ownership; the AI validates the requested input.
        if dx not in (-1, 0, 1) or dy not in (-1, 0, 1):
            return
        self.dx = dx
        self.dy = dy

    def _update_position(self, task):
        # ponytail: cap catch-up at 100 ms; a fixed-step simulation if deterministic timing matters.
        dt = min(globalClock.getDt(), 0.1)
        if self.dx or self.dy:
            limit = self.movement_limit
            x = max(-limit, min(limit, self.x + self.dx * self.SPEED * dt))
            y = max(-limit, min(limit, self.y + self.dy * self.SPEED * dt))
            if x != self.x or y != self.y:
                self.b_setPosition(x, y)
        return Task.cont


class DemoBeacon(DistributedObject):
    def __init__(self, cr):
        super().__init__(cr)
        self.model = None
        self.activation_count = 0
        self.activation_label = None

    def generate(self):
        if self.model is None:
            self.model = base.loader.loadModel("models/misc/sphere")
            self.model.setScale(0.55)
            self.model.setColor(1.0, 0.75, 0.15, 1.0)
            text = TextNode("persistent-beacon-label")
            self.activation_label = self.model.attachNewNode(text)
            self.activation_label.setZ(1.1)
            self.activation_label.setScale(0.18)
            self.activation_label.setBillboardPointEye()
            self.activation_label.setColor(1, 1, 1, 1)
        self.model.setPos(2.0, 3.0, 0.55)
        self.model.reparentTo(base.render)
        self._update_activation_label()

    def disable(self):
        if self.model is not None:
            self.model.detachNode()
        super().disable()
        messenger.send("demo-beacon-left-view", [self])

    def delete(self):
        if self.model is not None:
            self.model.removeNode()
            self.model = None
            self.activation_label = None
        super().delete()

    def setActivationCount(self, count):
        self.activation_count = int(count)
        self._update_activation_label()

    def announceGenerate(self):
        super().announceGenerate()
        messenger.send("demo-beacon-generated", [self])

    def _update_activation_label(self):
        if self.activation_label is not None:
            self.activation_label.node().setText(
                f"Saved beacon; AI activations: {self.activation_count}"
            )


class DemoBeaconAI(DistributedObjectAI):
    def __init__(self, air):
        super().__init__(air)

        self.activation_count = 0

    def announceGenerate(self):
        super().announceGenerate()
        self.b_setActivationCount(self.activation_count + 1)
        print(
            f"Persistent beacon {self.doId} AI activation count: {self.activation_count}.",
            flush=True,
        )

    def getActivationCount(self):
        return self.activation_count

    def setActivationCount(self, count):
        self.activation_count = int(count)

    def b_setActivationCount(self, count):
        self.setActivationCount(count)
        self.sendUpdate("setActivationCount", [self.activation_count])
