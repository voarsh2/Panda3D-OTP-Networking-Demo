import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from direct.distributed.DistributedNode import DistributedNode
from panda3d.core import NodePath

from demo.client import DemoClient, DemoClientRepository
from demo.constants import (
    AI_CHANNEL,
    DISTRICT_ID,
    GAME_ROOT_ID,
    LAB_ZONE,
    LOGIN_DISTRICT_INTEREST_ID,
    LOGIN_WORLD_ROOT_INTEREST_ID,
    MAIN_ZONE,
    MANAGEMENT_ZONE,
    ZONE_CROSSING_X,
)
from demo.objects import (
    DemoAvatar,
    DemoAvatarAI,
    DemoAvatarOV,
    DemoDistrictAI,
    DemoLoginManagerUD,
)
from demo.startup import write_ready_marker


class DemoFlowTests(unittest.TestCase):
    def test_ready_marker_is_written_when_launcher_requests_it(self):
        with TemporaryDirectory() as directory:
            marker = Path(directory) / "ai.ready"
            with patch.dict("os.environ", {"PANDA_DEMO_READY_FILE": str(marker)}):
                write_ready_marker("PANDA_DEMO_READY_FILE")

            self.assertTrue(marker.is_file())

    def test_login_loads_world_before_creating_avatar(self):
        calls = []
        callbacks = []
        district = SimpleNamespace(create_avatar=Mock())

        class Air:
            def get_msg_sender(self):
                return 100123

            def setClientState(self, channel, state):
                calls.append(("client-state", channel, state))

            def clientAddInterest(
                self, channel, handle, parent, zone, callback=None
            ):
                calls.append(("interest", channel, handle, parent, zone))
                callbacks.append(callback)

        login_manager = SimpleNamespace(air=Air(), district=district)
        with contextlib.redirect_stdout(io.StringIO()):
            DemoLoginManagerUD.login(login_manager, "Alice")

        self.assertEqual(calls[0], ("client-state", 100123, 2))
        self.assertEqual(
            calls[1],
            ("interest", 100123, LOGIN_WORLD_ROOT_INTEREST_ID, GAME_ROOT_ID, MANAGEMENT_ZONE),
        )
        district.create_avatar.assert_not_called()

        callbacks[0](100123, LOGIN_WORLD_ROOT_INTEREST_ID)
        self.assertEqual(
            calls[2],
            ("interest", 100123, LOGIN_DISTRICT_INTEREST_ID, DISTRICT_ID, MAIN_ZONE),
        )
        district.create_avatar.assert_not_called()

        callbacks[1](100123, LOGIN_DISTRICT_INTEREST_ID)
        district.create_avatar.assert_called_once_with(100123, "Alice")

    def test_client_authenticates_before_opening_gameglobals_interest(self):
        calls = []

        class LoginManager:
            def login(self, name):
                calls.append(("login", name))

        class Repository:
            def generateGlobalObject(self, do_id, dclass):
                calls.append(("global", do_id, dclass))
                return LoginManager()

            def addInterest(self, parent_id, zones, label):
                calls.append(("interest", parent_id, zones, label))
                return object()

        client = object.__new__(DemoClient)
        client.repo = Repository()
        client.name = "Alice"
        client.owner_view = None
        client._district_interest = None

        DemoClient._on_hello(client)
        self.assertEqual(calls[-1], ("login", "Alice"))
        self.assertFalse(any(call[0] == "interest" for call in calls))

        owner_view = object()
        DemoClient._set_owner_view(client, owner_view)
        self.assertIs(client.owner_view, owner_view)
        self.assertEqual(
            calls[-1],
            ("interest", GAME_ROOT_ID, [MANAGEMENT_ZONE], "demo game directory"),
        )

    def test_ai_creates_avatar_as_the_client_session_object_in_district(self):
        client_channel = 100123

        class Avatar:
            def __init__(self, air):
                self.air = air
                self.name = None
                self.position = None

            def setName(self, name):
                self.name = name

            def setPosition(self, x, y):
                self.position = (x, y)

            def generateWithRequiredAndId(self, do_id, parent_id, zone_id):
                self.doId = do_id
                self.air.calls.append(("generate", do_id, parent_id, zone_id))

        air = SimpleNamespace(
            ourChannel=AI_CHANNEL,
            calls=[],
            avatar=None,
            worldGridManager=None,
        )
        air.allocateChannel = lambda: 900001
        air.setAI = lambda do_id, channel: air.calls.append(("setAI", do_id, channel))
        air.clientAddSessionObject = lambda channel, do_id: air.calls.append(
            ("session", channel, do_id)
        )
        air.setOwner = lambda do_id, channel: air.calls.append(("owner", do_id, channel))

        district = object.__new__(DemoDistrictAI)
        district.air = air
        district.doId = DISTRICT_ID
        district._spawn_count = 0
        district.cartesian_grid = None

        def make_avatar(repository):
            air.avatar = Avatar(repository)
            return air.avatar

        with patch("demo.objects.DemoAvatarAI", side_effect=make_avatar):
            with contextlib.redirect_stdout(io.StringIO()):
                DemoDistrictAI.createAvatar(district, client_channel, "Bob")

        self.assertEqual(air.avatar.name, "Bob")
        self.assertEqual(air.avatar.position, (-2.0, 0.0))
        self.assertEqual(
            air.calls,
            [
                ("generate", 900001, DISTRICT_ID, MAIN_ZONE),
                ("setAI", 900001, AI_CHANNEL),
                ("session", client_channel, 900001),
                ("owner", 900001, client_channel),
            ],
        )

    def test_grid_avatar_is_generated_in_its_cell_after_grid_is_loaded(self):
        client_channel = 100123
        grid = SimpleNamespace(
            doId=5001,
            gridObjects={},
            getZoneFromXYZ=Mock(return_value=6035),
            addObjectToGrid=Mock(),
        )
        manager = SimpleNamespace(handleLocationChanged=Mock())

        class Avatar:
            def __init__(self, air):
                self.air = air
                self.name = None
                self.position = None

            def setName(self, name):
                self.name = name

            def setPosition(self, x, y):
                self.position = (x, y)

            def reparentTo(self, parent):
                self.parent = parent

            def generateWithRequiredAndId(self, do_id, parent_id, zone_id):
                self.doId = do_id
                self.air.calls.append(("generate", do_id, parent_id, zone_id))

        air = SimpleNamespace(
            ourChannel=AI_CHANNEL,
            calls=[],
            worldGridManager=manager,
        )
        air.allocateChannel = lambda: 900002
        air.setAI = lambda do_id, channel: air.calls.append(("setAI", do_id, channel))
        air.clientAddSessionObject = lambda channel, do_id: air.calls.append(
            ("session", channel, do_id)
        )
        air.setOwner = lambda do_id, channel: air.calls.append(
            ("owner", do_id, channel)
        )

        district = object.__new__(DemoDistrictAI)
        district.air = air
        district.doId = DISTRICT_ID
        district._spawn_count = 0
        district.cartesian_grid = grid

        def make_avatar(repository):
            air.avatar = Avatar(repository)
            return air.avatar

        with patch("demo.objects.DemoAvatarAI", side_effect=make_avatar):
            with contextlib.redirect_stdout(io.StringIO()):
                DemoDistrictAI.createAvatar(district, client_channel, "Alice")

        self.assertEqual(air.avatar.position, (-2.0, 2.0))
        grid.getZoneFromXYZ.assert_called_once_with((-2.0, 2.0, 0.0))
        self.assertEqual(
            air.calls,
            [
                ("generate", 900002, grid.doId, 6035),
                ("setAI", 900002, AI_CHANNEL),
                ("session", client_channel, 900002),
                ("owner", 900002, client_channel),
            ],
        )
        grid.addObjectToGrid.assert_called_once_with(
            air.avatar, useZoneId=6035
        )
        manager.handleLocationChanged.assert_called_once_with(
            grid, air.avatar, 6035
        )

    def test_owner_view_mirrors_state_and_sends_movement_intent(self):
        visual = SimpleNamespace(setName=Mock(), setPosition=Mock())
        owner_view = SimpleNamespace(avatar=visual, sendUpdate=Mock())

        DemoAvatarOV.setName(owner_view, "Alice")
        DemoAvatarOV.setPosition(owner_view, 1.25, -2.5)
        DemoAvatarOV.requestMove(owner_view, 1, 0)

        visual.setName.assert_called_once_with("Alice")
        visual.setPosition.assert_called_once_with(1.25, -2.5)
        owner_view.sendUpdate.assert_called_once_with("requestMove", [1, 0])

    def test_ai_moves_avatar_between_zones_at_the_boundary(self):
        for start_x, dx, start_zone, expected_zone in (
            (ZONE_CROSSING_X - 0.1, 1, MAIN_ZONE, LAB_ZONE),
            (ZONE_CROSSING_X + 0.1, -1, LAB_ZONE, MAIN_ZONE),
        ):
            with self.subTest(start_x=start_x):
                avatar = SimpleNamespace(
                    x=start_x,
                    y=0.0,
                    dx=dx,
                    dy=0,
                    parentId=DISTRICT_ID,
                    zoneId=start_zone,
                    cartesian_grid=None,
                    movement_limit=DemoAvatarAI.LIMIT,
                    LIMIT=DemoAvatarAI.LIMIT,
                    SPEED=DemoAvatarAI.SPEED,
                )
                events = []

                def set_position(x, y):
                    avatar.x = x
                    avatar.y = y
                    events.append("position")

                def set_location(parent_id, zone_id):
                    avatar.zoneId = zone_id
                    events.append("location")

                avatar.setPosition = set_position
                avatar.b_setPosition = lambda x, y: DemoAvatarAI.b_setPosition(
                    avatar, x, y
                )
                avatar.b_setLocation = Mock(side_effect=set_location)
                avatar.sendUpdate = lambda field, args: events.append("field")

                with patch(
                    "demo.objects.globalClock",
                    SimpleNamespace(getDt=lambda: 0.1),
                ):
                    DemoAvatarAI._update_position(avatar, None)

                avatar.b_setLocation.assert_called_once_with(
                    DISTRICT_ID, expected_zone
                )
                self.assertEqual(avatar.zoneId, expected_zone)
                self.assertLess(events.index("field"), events.index("location"))

    def test_grid_avatar_skips_grid_root_write_when_detached(self):
        grid = SimpleNamespace(doId=5001)
        avatar = SimpleNamespace(
            x=1.0,
            y=2.0,
            cartesian_grid=grid,
            parentId=grid.doId,
            gridParent=None,
            getParent=lambda: SimpleNamespace(isEmpty=lambda: True),
            setPos=Mock(),
            sendUpdate=Mock(),
        )
        avatar.setPosition = lambda x, y: DemoAvatarAI.setPosition(avatar, x, y)

        DemoAvatarAI.b_setPosition(avatar, 3.0, 4.0)

        self.assertEqual((avatar.x, avatar.y), (1.0, 2.0))
        avatar.setPos.assert_not_called()
        avatar.sendUpdate.assert_not_called()

    def test_grid_avatar_uses_the_gridparent_grid_attribute(self):
        grid = SimpleNamespace(doId=5001)
        avatar = SimpleNamespace(
            x=1.0,
            y=2.0,
            cartesian_grid=grid,
            parentId=grid.doId,
            gridParent=SimpleNamespace(grid=grid),
            getParent=lambda: SimpleNamespace(isEmpty=lambda: False),
            setPos=Mock(),
        )

        result = DemoAvatarAI.setPosition(avatar, 3.0, 4.0)

        self.assertTrue(result)
        avatar.setPos.assert_called_once_with(grid, 3.0, 4.0, 0.8)

    def test_grid_cell_changes_are_owned_by_the_grid_update_task(self):
        grid = SimpleNamespace(doId=5001, updateAvatarGridLocation=Mock())
        avatar = SimpleNamespace(
            x=1.0,
            y=2.0,
            cartesian_grid=grid,
            parentId=grid.doId,
            zoneId=6035,
            sendUpdate=Mock(),
        )

        def set_position(x, y):
            avatar.x, avatar.y = x, y
            return True

        avatar.setPosition = set_position

        DemoAvatarAI.b_setPosition(avatar, 3.0, 4.0)

        avatar.sendUpdate.assert_called_once_with("setPosition", [3.0, 4.0])
        grid.updateAvatarGridLocation.assert_not_called()

    def test_avatar_reenters_grid_when_movement_returns_inside(self):
        grid = SimpleNamespace(
            doId=5001,
            getZoneFromXYZ=Mock(return_value=6035),
            isValidZone=Mock(return_value=True),
        )
        avatar = SimpleNamespace(
            x=20.0,
            y=0.0,
            cartesian_grid=grid,
            parentId=DISTRICT_ID,
            zoneId=1,
            sendUpdate=Mock(),
            b_setLocation=Mock(),
        )

        def set_position(x, y):
            avatar.x, avatar.y = x, y
            return True

        avatar.setPosition = set_position

        DemoAvatarAI.b_setPosition(avatar, 0.0, 0.0)

        avatar.b_setLocation.assert_called_once_with(grid.doId, 6035)

    def test_client_avatar_reports_a_live_location_change(self):
        render = NodePath("render")
        cr = SimpleNamespace(doId2do={})
        avatar = DemoAvatar.__new__(DemoAvatar)
        DemoAvatar.__init__(avatar, cr)
        avatar.parentId = DISTRICT_ID
        avatar.zoneId = MAIN_ZONE

        def store_location(obj, parent_id, zone_id):
            obj.parentId = parent_id
            obj.zoneId = zone_id

        with patch("demo.objects.base", SimpleNamespace(render=render), create=True), patch.object(
            DistributedNode, "setLocation", new=store_location
        ), patch.object(DemoAvatar, "isGenerated", return_value=True), patch(
            "demo.objects.messenger.send"
        ) as send:
            DemoAvatar.setLocation(avatar, DISTRICT_ID, LAB_ZONE)

        send.assert_called_once_with(
            "demo-avatar-location-changed",
            [avatar, DISTRICT_ID, MAIN_ZONE, DISTRICT_ID, LAB_ZONE],
        )

    def test_client_avatar_can_deactivate_without_an_attached_nodepath(self):
        cr = SimpleNamespace(doId2do={})
        avatar = DemoAvatar.__new__(DemoAvatar)
        DemoAvatar.__init__(avatar, cr)
        avatar.removeNode()

        def store_location(obj, parent_id, zone_id):
            obj.parentId = parent_id
            obj.zoneId = zone_id

        with patch.object(DistributedNode, "setLocation", new=store_location):
            DemoAvatar.setLocation(avatar, 0, 0)

        self.assertTrue(avatar.isEmpty())
        self.assertEqual((avatar.parentId, avatar.zoneId), (0, 0))

    def test_client_repository_updates_owner_view_location_metadata(self):
        owner_view = SimpleNamespace(parentId=DISTRICT_ID, zoneId=MAIN_ZONE)

        class Datagram:
            values = iter((900001, DISTRICT_ID, LAB_ZONE))

            def getUint32(self):
                return next(self.values)

        repository = SimpleNamespace(
            doId2do={},
            doId2ownerView={900001: owner_view},
            notify=SimpleNamespace(warning=Mock()),
        )

        with patch("demo.client.messenger.send") as send:
            DemoClientRepository.handleObjectLocation(repository, Datagram())

        self.assertEqual(owner_view.parentId, DISTRICT_ID)
        self.assertEqual(owner_view.zoneId, LAB_ZONE)
        repository.notify.warning.assert_not_called()
        send.assert_called_once_with(
            "demo-owner-avatar-location-changed",
            [owner_view, DISTRICT_ID, LAB_ZONE],
        )

    def test_client_repository_forwards_normal_object_location_updates(self):
        avatar = SimpleNamespace(setLocation=Mock())

        class Datagram:
            values = iter((900001, DISTRICT_ID, LAB_ZONE))

            def getUint32(self):
                return next(self.values)

        repository = SimpleNamespace(
            doId2do={900001: avatar},
            doId2ownerView={},
            notify=SimpleNamespace(warning=Mock()),
        )

        DemoClientRepository.handleObjectLocation(repository, Datagram())

        avatar.setLocation.assert_called_once_with(DISTRICT_ID, LAB_ZONE)
        repository.notify.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
