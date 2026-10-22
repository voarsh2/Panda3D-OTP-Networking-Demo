import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from direct.distributed.DistributedObject import DistributedObject
from direct.distributed.DistributedObjectAI import DistributedObjectAI
from direct.distributed.DistributedNode import DistributedNode

from demo.inspect import (
    avatar_leave_snapshot,
    avatar_snapshot,
    beacon_is_expected,
    beacon_snapshot,
    DemoInspector,
)
from demo.objects import DemoAvatar, DemoBeacon, DemoBeaconAI
from demo.persistence import ensure_persistent_beacon


class PersistentBeaconTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.id_file = Path(self.temp_dir.name) / "beacon-doid.txt"
        self.dclass = object()
        self.air = SimpleNamespace(
            dbId=403000,
            ourChannel=300001,
            dclassesByName={"DemoBeaconAI": self.dclass},
            dbInterface=SimpleNamespace(),
            sendActivate=Mock(),
            setAI=Mock(),
        )

    def test_creates_and_activates_beacon_and_saves_its_id(self):
        calls = []

        def create_object(database_id, dclass, fields, callback):
            calls.append((database_id, dclass, fields))
            callback(500123)

        self.air.dbInterface.createObject = create_object

        with contextlib.redirect_stdout(io.StringIO()):
            ensure_persistent_beacon(self.air, self.id_file, 5000, 2)

        self.assertEqual(calls, [(403000, self.dclass, {"setActivationCount": (0,)})])
        self.assertEqual(self.id_file.read_text(encoding="utf-8"), "500123\n")
        self.air.sendActivate.assert_called_once_with(500123, 5000, 2)
        self.air.setAI.assert_called_once_with(500123, 300001)

    def test_queries_and_reactivates_existing_beacon(self):
        self.id_file.write_text("500124\n", encoding="utf-8")
        queries = []

        def query_object(database_id, do_id, callback):
            queries.append((database_id, do_id))
            callback(self.dclass, {"setActivationCount": (3,)})

        self.air.dbInterface.queryObject = query_object
        self.air.dbInterface.createObject = Mock()

        with contextlib.redirect_stdout(io.StringIO()):
            ensure_persistent_beacon(self.air, self.id_file, 5000, 2)

        self.assertEqual(queries, [(403000, 500124)])
        self.air.dbInterface.createObject.assert_not_called()
        self.air.sendActivate.assert_called_once_with(500124, 5000, 2)
        self.air.setAI.assert_called_once_with(500124, 300001)

    def test_recreates_beacon_when_saved_id_is_missing_from_database(self):
        self.id_file.write_text("500125\n", encoding="utf-8")
        created = []

        def query_object(database_id, do_id, callback):
            callback(None, None)

        def create_object(database_id, dclass, fields, callback):
            created.append((database_id, dclass, fields))
            callback(500126)

        self.air.dbInterface.queryObject = query_object
        self.air.dbInterface.createObject = create_object

        with contextlib.redirect_stdout(io.StringIO()):
            ensure_persistent_beacon(self.air, self.id_file, 5000, 2)

        self.assertEqual(created, [(403000, self.dclass, {"setActivationCount": (0,)})])
        self.assertEqual(self.id_file.read_text(encoding="utf-8"), "500126\n")
        self.air.sendActivate.assert_called_once_with(500126, 5000, 2)
        self.air.setAI.assert_called_once_with(500126, 300001)

    def test_ai_increments_database_field_when_beacon_activates(self):
        beacon = object.__new__(DemoBeaconAI)
        beacon.doId = 500123
        beacon.activation_count = 4
        beacon.sendUpdate = Mock()

        with contextlib.redirect_stdout(io.StringIO()), patch.object(
            DistributedObjectAI, "announceGenerate"
        ) as parent_announce:
            DemoBeaconAI.announceGenerate(beacon)

        parent_announce.assert_called_once()
        self.assertEqual(beacon.activation_count, 5)
        beacon.sendUpdate.assert_called_once_with("setActivationCount", [5])

    def test_inspector_validates_the_live_client_object_state(self):
        beacon = SimpleNamespace(
            doId=500123,
            parentId=5000,
            zoneId=2,
            activation_count=4,
        )
        repository = SimpleNamespace(doId2do={500123: beacon})

        state = beacon_snapshot(repository, beacon)

        self.assertEqual(
            state,
            {
                "doId": 500123,
                "parentId": 5000,
                "zoneId": 2,
                "activationCount": 4,
                "inRepository": True,
            },
        )
        self.assertTrue(beacon_is_expected(state, 500123))
        self.assertFalse(beacon_is_expected(state, 500124))

    def test_avatar_disable_emits_one_leave_event_and_hides_model(self):
        avatar = DemoAvatar.__new__(DemoAvatar)
        DemoAvatar.__init__(avatar, SimpleNamespace(doId2do={}))
        avatar._left_view_reported = False
        avatar.model = SimpleNamespace(detachNode=Mock())
        avatar.doId = 300123

        with patch("demo.objects.messenger.send") as send, patch.object(
            DistributedNode, "disable"
        ):
            DemoAvatar.disable(avatar)
            DemoAvatar.disable(avatar)

        send.assert_called_once_with("demo-avatar-left-view", [avatar])
        self.assertEqual(avatar.model.detachNode.call_count, 2)

    def test_beacon_disable_hides_its_visual(self):
        beacon = object.__new__(DemoBeacon)
        beacon.model = SimpleNamespace(detachNode=Mock())

        with patch("demo.objects.messenger.send") as send, patch.object(
            DistributedObject, "disable"
        ):
            DemoBeacon.disable(beacon)

        beacon.model.detachNode.assert_called_once_with()
        send.assert_called_once_with("demo-beacon-left-view", [beacon])

    def test_inspector_distinguishes_session_view_from_saved_beacon(self):
        avatar = SimpleNamespace(
            doId=300123,
            parentId=5000,
            zoneId=1,
            isGenerated=lambda: False,
        )
        beacon = SimpleNamespace(
            doId=500123,
            isGenerated=lambda: True,
        )
        repository = SimpleNamespace(doId2do={300123: avatar, 500123: beacon})

        state = avatar_leave_snapshot(repository, avatar, 500123)

        self.assertFalse(state["avatarGenerated"])
        self.assertTrue(state["beaconGenerated"])
        self.assertTrue(state["beaconInRepository"])

    def test_inspector_reads_avatar_location_from_the_live_object(self):
        avatar = SimpleNamespace(
            doId=300123,
            parentId=5000,
            zoneId=2,
            isGenerated=lambda: True,
        )
        repository = SimpleNamespace(doId2do={300123: avatar})

        self.assertEqual(
            avatar_snapshot(repository, avatar),
            {
                "doId": 300123,
                "parentId": 5000,
                "zoneId": 2,
                "inRepository": True,
                "generated": True,
            },
        )

    def test_main_only_inspector_does_not_open_lab_interest(self):
        inspector = object.__new__(DemoInspector)
        inspector.include_lab = False
        inspector._lab_interest = None
        inspector.repo = SimpleNamespace(addInterest=Mock())

        DemoInspector._open_lab_interest(inspector, SimpleNamespace(doId=5000))

        inspector.repo.addInterest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
