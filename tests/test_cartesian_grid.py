import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import contextlib
import io

from direct.distributed.CartesianGridBase import CartesianGridBase
from direct.distributed.DoInterestManager import (
    DoInterestManager,
    InterestHandle,
    InterestState,
)

from demo.ai_server import DemoAIRepository
from demo.constants import LAB_ZONE, MAIN_ZONE
from demo.cartesian_grid import (
    GRID_CELL_WIDTH,
    GRID_RADIUS,
    GRID_SIZE,
    GRID_STARTING_ZONE,
    DemoWorldGridManagerAI,
    DemoGridProbeAI,
    grid_cell_location,
    grid_interest_window,
)
from demo.cartesian_grid_client import (
    GRID_LABEL_HEIGHT,
    GRID_LABEL_Y_OFFSET,
    DemoCartesianGridClient,
    interest_cell_edges,
)
from demo.client import DemoClientRepository


class CartesianGridTests(unittest.TestCase):
    def setUp(self):
        self.grid = CartesianGridBase()
        self.grid.startingZone = GRID_STARTING_ZONE
        self.grid.gridSize = GRID_SIZE
        self.grid.gridRadius = GRID_RADIUS
        self.grid.viewingRadius = GRID_RADIUS
        self.grid.cellWidth = GRID_CELL_WIDTH
        self.grid.style = "Cartesian"
        self.grid.center = GRID_SIZE * GRID_CELL_WIDTH / 2

    def test_world_position_maps_to_a_cell_and_cell_local_position(self):
        zone, local_position = grid_cell_location(self.grid, -6.0, 2.0)

        self.assertEqual(zone, GRID_STARTING_ZONE + 4 * GRID_SIZE + 2)
        self.assertEqual(local_position, (2.0, 2.0))

    def test_interest_window_moves_by_cell_and_includes_neighbors(self):
        left_center, left_zones = grid_interest_window(self.grid, (-2.0, 0.0, 0.0))
        right_center, right_zones = grid_interest_window(self.grid, (2.0, 0.0, 0.0))

        self.assertEqual(right_center, left_center + 1)
        self.assertEqual(len(left_zones), 9)
        self.assertEqual(len(right_zones), 9)
        self.assertNotEqual(left_zones, right_zones)
        self.assertGreater(len(set(left_zones) & set(right_zones)), 0)

    def test_interest_window_is_empty_outside_grid_bounds(self):
        self.assertEqual(grid_interest_window(self.grid, (-20.0, 0.0, 0.0)), (None, ()))
        self.assertEqual(grid_interest_window(self.grid, (16.0, 0.0, 0.0)), (None, ()))
        with self.assertRaises(ValueError):
            grid_cell_location(self.grid, 16.0, 0.0)

    def test_interest_outline_draws_each_edge_once(self):
        _, zones = grid_interest_window(self.grid, (0.0, 0.0, 0.0))

        self.assertEqual(len(zones), 9)
        self.assertEqual(len(interest_cell_edges(self.grid, zones)), 24)

    def test_grid_labels_are_aligned_and_visible_in_occupied_cells(self):
        labels = [
            SimpleNamespace(getY=Mock(return_value=1.0), setY=Mock(), setZ=Mock()),
            SimpleNamespace(getY=Mock(return_value=5.0), setY=Mock(), setZ=Mock()),
        ]
        grid = SimpleNamespace(
            doId=5001,
            parentId=5000,
            zoneId=MAIN_ZONE,
            startingZone=GRID_STARTING_ZONE,
            gridSize=GRID_SIZE,
            viewingRadius=GRID_RADIUS,
            cellWidth=GRID_CELL_WIDTH,
            cellLabelParent=SimpleNamespace(getChildren=lambda: labels),
            visualizeGrid=Mock(),
        )
        client = object.__new__(DemoCartesianGridClient)
        client.grid = None
        client.show_grid = True
        client.server_grid_interest = False
        client._owner_position = None
        client._grid_center = None
        client._interest_radius = None
        client._probe_do_id = None
        client._probe_zone = None
        client._probe_status = "WAITING"
        client._lab_interest = None
        client._hud_text = None
        client.grid_hud = SimpleNamespace(setText=Mock())

        with contextlib.redirect_stdout(io.StringIO()):
            DemoCartesianGridClient._set_grid(client, grid)

        grid.visualizeGrid.assert_called_once_with()
        for label, y in zip(labels, (1.0, 5.0)):
            label.setZ.assert_called_once_with(GRID_LABEL_HEIGHT)
            label.setY.assert_called_once_with(y + GRID_LABEL_Y_OFFSET)

    def test_client_interest_is_removed_when_owner_leaves_grid(self):
        client = object.__new__(DemoCartesianGridClient)
        client.grid = SimpleNamespace(doId=5001, viewingRadius=1)
        client._owner_position = (-2.0, 0.0)
        client._grid_interest = None
        client._grid_zones = ()
        client._interest_zones = ()
        client._interest_outline = None
        client.show_grid = False
        client._grid_center = None
        client._interest_radius = None
        client._probe_do_id = None
        client._probe_zone = None
        client._probe_status = "WAITING"
        client._lab_interest = None
        client._hud_text = None
        client.grid_hud = SimpleNamespace(setText=Mock())
        client.server_grid_interest = False
        client.repo = SimpleNamespace(
            addInterest=Mock(return_value=17),
            alterInterest=Mock(),
            removeInterest=Mock(),
        )

        with patch(
            "demo.cartesian_grid_client.grid_interest_window",
            side_effect=((GRID_STARTING_ZONE, (GRID_STARTING_ZONE,)), (None, ())),
        ), contextlib.redirect_stdout(io.StringIO()):
            client._update_grid_interest()
            client._owner_position = (20.0, 0.0)
            client._update_grid_interest()

        client.repo.removeInterest.assert_called_once_with(17)
        self.assertIsNone(client._grid_interest)
        self.assertEqual(client._grid_zones, ())

    def test_client_does_not_redraw_unchanged_interest_window(self):
        client = object.__new__(DemoCartesianGridClient)
        client.grid = SimpleNamespace(doId=5001, viewingRadius=1)
        client.server_grid_interest = True
        client._owner_position = (1.0, 2.0)
        client._grid_center = 6035
        client._interest_zones = (6026, 6027, 6028, 6034, 6035, 6036, 6042, 6043, 6044)
        client._interest_radius = 1
        client._hud_text = "unchanged"
        client._draw_interest_cells = Mock()
        client._update_hud = Mock()

        with patch(
            "demo.cartesian_grid_client.grid_interest_window",
            return_value=(client._grid_center, client._interest_zones),
        ):
            DemoCartesianGridClient._update_grid_interest(client)

        client._draw_interest_cells.assert_not_called()
        client._update_hud.assert_not_called()

    def test_grid_hud_tracks_observer_cell_and_probe_interest_lifecycle(self):
        client = object.__new__(DemoCartesianGridClient)
        client.grid = SimpleNamespace(doId=5001, viewingRadius=1)
        client.server_grid_interest = True
        client.show_grid = False
        client._interest_outline = None
        client._grid_center = None
        client._interest_radius = None
        client._owner_position = (-2.0, 0.0)
        client._interest_zones = ()
        client._probe_do_id = None
        client._probe_zone = None
        client._probe_status = "WAITING"
        client._lab_interest = None
        client._hud_text = None
        client.grid_hud = SimpleNamespace(setText=Mock())
        client.repo = SimpleNamespace(
            doId2do={},
            getServerInterestStates=Mock(return_value=()),
        )

        with patch(
            "demo.cartesian_grid_client.grid_interest_window",
            return_value=(6035, (6026, 6027, 6034, 6035, 6036)),
        ):
            DemoCartesianGridClient._update_grid_interest(client)

        self.assertEqual(client._grid_center, 6035)
        self.assertIn("Observer cell: 6035", client.grid_hud.setText.call_args.args[0])
        self.assertIn("Interest radius: 1", client.grid_hud.setText.call_args.args[0])
        self.assertIn("Interest source: AI-managed", client.grid_hud.setText.call_args.args[0])
        self.assertIn("AI-managed (WAITING 0/5)", client.grid_hud.setText.call_args.args[0])
        self.assertIn("District zone 2 (Tab): CLOSED", client.grid_hud.setText.call_args.args[0])

        probe = SimpleNamespace(
            doId=300002,
            parentId=5001,
            zoneId=6034,
            isGenerated=lambda: True,
        )
        client.repo.doId2do[probe.doId] = probe
        with contextlib.redirect_stdout(io.StringIO()):
            DemoCartesianGridClient._inspect_probe(client, probe)

        generated_text = client.grid_hud.setText.call_args.args[0]
        self.assertIn("doId: 300002", generated_text)
        self.assertIn("Zone: 6034", generated_text)
        self.assertIn("State: GENERATED", generated_text)

        client.repo.doId2do.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            DemoCartesianGridClient._inspect_probe_leave(client, probe)

        left_text = client.grid_hud.setText.call_args.args[0]
        self.assertIn("State: OUT OF INTEREST", left_text)

    def test_tab_opens_and_closes_whole_district_zone_two(self):
        client = object.__new__(DemoCartesianGridClient)
        client.grid = SimpleNamespace(doId=5001)
        client.server_grid_interest = False
        client.show_grid = False
        client._interest_zones = ()
        client._owner_position = (-2.0, 0.0)
        client._grid_center = 6035
        client._interest_radius = 1
        client._probe_do_id = None
        client._probe_zone = None
        client._probe_status = "WAITING"
        client._lab_interest = None
        client._hud_text = None
        client.grid_hud = SimpleNamespace(setText=Mock())
        client.owner_view = object()
        client.district = SimpleNamespace(doId=5000)
        client.repo = SimpleNamespace(
            addInterest=Mock(return_value=17),
            removeInterest=Mock(),
        )

        with contextlib.redirect_stdout(io.StringIO()):
            DemoCartesianGridClient._toggle_lab_interest(client)

        client.repo.addInterest.assert_called_once_with(
            5000, [LAB_ZONE], "demo lab zone"
        )
        self.assertIn(
            "District zone 2 (Tab): OPEN",
            client.grid_hud.setText.call_args.args[0],
        )

        with contextlib.redirect_stdout(io.StringIO()):
            DemoCartesianGridClient._toggle_lab_interest(client)

        client.repo.removeInterest.assert_called_once_with(17)
        self.assertIn(
            "District zone 2 (Tab): CLOSED",
            client.grid_hud.setText.call_args.args[0],
        )

    def test_ai_manager_opens_and_closes_server_owned_cell_interests(self):
        calls = []

        class Air:
            def __init__(self):
                self.doId2do = {grid.doId: grid}

            def clientAddInterest(self, channel, handle, parent, zone, callback=None):
                calls.append(("add", channel, handle, parent, zone, callback, False))

            def client_remove_interest(self, channel, handle, callback=None):
                calls.append(("remove", channel, handle, None, None, callback, False))

        def complete_interests():
            for index, call in enumerate(calls):
                if call[5] is None or call[6]:
                    continue
                calls[index] = (*call[:6], True)
                call[5](call[1], call[2])

        grid = self.grid
        grid.doId = 5001
        grid.interestSnapshotPending = Mock()
        grid.interestSnapshotReady = Mock()
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        left_center = int(grid.getZoneFromXYZ((-2.0, 0.0, 0.0)))
        right_center = int(grid.getZoneFromXYZ((2.0, 0.0, 0.0)))
        outside_zone = GRID_STARTING_ZONE - 1

        with contextlib.redirect_stdout(io.StringIO()):
            manager.handleLocationChanged(grid, avatar, left_center)
            first_zones = manager.getInterestZones(grid, avatar)
            complete_interests()
            manager.handleLocationChanged(grid, avatar, right_center)
            moved_zones = manager.getInterestZones(grid, avatar)
            complete_interests()
            manager.handleLocationChanged(grid, avatar, outside_zone)
            self.assertTrue(manager.hasPendingInterests(grid))
            complete_interests()

        self.assertEqual(
            first_zones,
            grid_interest_window(grid, (-2.0, 0.0, 0.0))[1],
        )
        self.assertNotEqual(moved_zones, first_zones)
        self.assertEqual(manager.getInterestZones(grid, avatar), ())
        adds = [call for call in calls if call[0] == "add"]
        removes = [call for call in calls if call[0] == "remove"]
        newly_visible = set(moved_zones) - set(first_zones)
        no_longer_visible = set(first_zones) - set(moved_zones)
        self.assertEqual(len(adds), len(first_zones) + len(newly_visible))
        self.assertEqual(len(removes), len(no_longer_visible) + len(moved_zones))
        self.assertTrue(all(call[2] & 0x8000 for call in adds))
        self.assertFalse(manager.hasPendingInterests(grid))

    def test_probe_patrol_uses_bounded_intervals_in_the_grid_frame(self):
        grid = object()
        sequence = SimpleNamespace(loop=Mock())
        probe = SimpleNamespace(
            SPEED=DemoGridProbeAI.SPEED,
            _grid=None,
            _move_interval=None,
            uniqueName=lambda name: name,
            startPosHprBroadcast=Mock(),
        )
        legs = [object(), object()]

        with patch(
            "demo.cartesian_grid.LerpPosInterval",
            side_effect=legs,
        ) as make_leg, patch(
            "demo.cartesian_grid.Sequence",
            return_value=sequence,
        ) as make_sequence:
            DemoGridProbeAI.start_patrol(probe, grid, -10.0, 10.0, -10.0, 2.0)

        self.assertEqual(make_leg.call_count, 2)
        forward, reverse = make_leg.call_args_list
        self.assertAlmostEqual(20.0 / DemoGridProbeAI.SPEED, forward.args[1])
        self.assertEqual(tuple(forward.args[2])[:2], (10.0, 2.0))
        self.assertAlmostEqual(forward.args[2].z, 0.7)
        self.assertEqual(tuple(forward.kwargs["startPos"])[:2], (-10.0, 2.0))
        self.assertAlmostEqual(forward.kwargs["startPos"].z, 0.7)
        self.assertIs(forward.kwargs["other"], grid)
        self.assertEqual(tuple(reverse.args[2])[:2], (-10.0, 2.0))
        self.assertAlmostEqual(reverse.args[2].z, 0.7)
        self.assertEqual(tuple(reverse.kwargs["startPos"])[:2], (10.0, 2.0))
        self.assertAlmostEqual(reverse.kwargs["startPos"].z, 0.7)
        self.assertIs(reverse.kwargs["other"], grid)
        make_sequence.assert_called_once_with(
            *legs,
            name="grid-patrol",
        )
        sequence.loop.assert_called_once_with()
        probe.startPosHprBroadcast.assert_called_once_with(period=0.2)

    def test_grid_pauses_until_every_new_interest_snapshot_is_done(self):
        calls = []

        class Air:
            def __init__(self):
                self.doId2do = {grid.doId: grid}

            def clientAddInterest(self, channel, handle, parent, zone, callback=None):
                calls.append((channel, handle, callback))

            def client_remove_interest(self, *_args, **_kwargs):
                raise AssertionError("no interests should be removed")

        grid = self.grid
        grid.doId = 5001
        grid.interestSnapshotPending = Mock()
        grid.interestSnapshotReady = Mock()
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        center = int(grid.getZoneFromXYZ((0.0, 0.0, 0.0)))

        with contextlib.redirect_stdout(io.StringIO()):
            manager.handleLocationChanged(grid, avatar, center)

        self.assertTrue(manager.hasPendingInterests(grid))
        grid.interestSnapshotPending.assert_called_once_with()
        grid.interestSnapshotReady.assert_not_called()
        calls[0][2](calls[0][0], calls[0][1])
        self.assertTrue(manager.hasPendingInterests(grid))
        grid.interestSnapshotReady.assert_not_called()

        for channel, handle, callback in calls[1:]:
            callback(channel, handle)

        self.assertFalse(manager.hasPendingInterests(grid))
        grid.interestSnapshotReady.assert_called_once_with()

    def test_missing_interest_done_callback_keeps_demo_grid_barrier_closed(self):
        calls = []

        class Air:
            def __init__(self):
                self.doId2do = {grid.doId: grid}

            def clientAddInterest(self, channel, handle, parent, zone, callback=None):
                calls.append((channel, handle, callback))

            def client_remove_interest(self, *_args, **_kwargs):
                raise AssertionError("no interests should be removed")

        grid = self.grid
        grid.doId = 5001
        grid.interestSnapshotPending = Mock()
        grid.interestSnapshotReady = Mock()
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        center = int(grid.getZoneFromXYZ((0.0, 0.0, 0.0)))

        with contextlib.redirect_stdout(io.StringIO()):
            manager.handleLocationChanged(grid, avatar, center)

        self.assertEqual(len(calls), len(grid_interest_window(grid, (0, 0, 0))[1]))
        self.assertTrue(manager.hasPendingInterests(grid))
        grid.interestSnapshotPending.assert_called_once_with()
        grid.interestSnapshotReady.assert_not_called()

    def test_grid_defers_removal_until_an_inflight_add_finishes(self):
        calls = []

        class Air:
            def __init__(self):
                self.doId2do = {grid.doId: grid}

            def clientAddInterest(self, channel, handle, parent, zone, callback=None):
                calls.append(("add", channel, handle, callback))

            def client_remove_interest(self, channel, handle, callback=None):
                calls.append(("remove", channel, handle, callback))

        grid = self.grid
        grid.doId = 5001
        grid.interestSnapshotPending = Mock()
        grid.interestSnapshotReady = Mock()
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        center = int(grid.getZoneFromXYZ((0.0, 0.0, 0.0)))

        with contextlib.redirect_stdout(io.StringIO()):
            manager.handleLocationChanged(grid, avatar, center)
            manager.clearAvatarInterest(grid, avatar)

        self.assertFalse(any(call[0] == "remove" for call in calls))
        self.assertTrue(manager.hasPendingInterests(grid))

        for kind, channel, handle, callback in tuple(calls):
            if kind == "add":
                callback(channel, handle)
        removes = [call for call in calls if call[0] == "remove"]
        self.assertEqual(len(removes), len(grid_interest_window(grid, (0, 0, 0))[1]))
        self.assertTrue(manager.hasPendingInterests(grid))

        for _, channel, handle, callback in removes:
            callback(channel, handle)

        self.assertFalse(manager.hasPendingInterests(grid))


    def test_client_marks_ai_interest_for_removal_until_done_response(self):
        handle = 0x8001
        state = InterestState(
            "server grid interest",
            InterestState.StateActive,
            7,
            None,
            5001,
            [GRID_STARTING_ZONE],
            SimpleNamespace(num=0),
            True,
        )
        DoInterestManager._interests[handle] = state
        client = DemoClientRepository.__new__(DemoClientRepository)

        class Datagram:
            values = iter((19, handle))

            def get_uint32(self):
                return next(self.values)

            def get_uint16(self):
                return next(self.values)

        try:
            with patch("demo.client.messenger.send") as send:
                DemoClientRepository.handle_remove_interest(client, Datagram())

            self.assertEqual(state.state, InterestState.StatePendingDel)
            self.assertEqual(state.context, 19)
            send.assert_called_once_with("CLIENT_REMOVE_INTEREST", [19, handle])
        finally:
            DoInterestManager._interests.pop(handle, None)

    def test_client_only_reports_server_interest_after_done_response(self):
        handle = 0x8001
        state = InterestState(
            "server grid interest",
            InterestState.StateActive,
            0,
            None,
            5001,
            [GRID_STARTING_ZONE],
            SimpleNamespace(num=0),
            True,
        )
        DoInterestManager._interests[handle] = state
        client = DemoClientRepository.__new__(DemoClientRepository)
        client._server_interest_pending = {handle}
        client._server_interest_complete = set()

        try:
            self.assertEqual(client.getServerInterestZones(5001), ())
            self.assertEqual(
                client.getServerInterestStates(5001),
                ((handle, (GRID_STARTING_ZONE,), "pending"),),
            )
        finally:
            DoInterestManager._interests.pop(handle, None)

    def test_client_done_response_marks_server_interest_complete(self):
        handle = 0x8002
        state = InterestState(
            "server grid interest",
            InterestState.StateActive,
            19,
            None,
            5001,
            [GRID_STARTING_ZONE],
            SimpleNamespace(num=0),
            True,
        )
        DoInterestManager._interests[handle] = state
        client = DemoClientRepository.__new__(DemoClientRepository)
        client._server_interest_pending = {handle}
        client._server_interest_complete = set()
        client._completeEventCount = SimpleNamespace(num=0)

        class Datagram:
            values = iter((19, handle))

            def get_uint32(self):
                return next(self.values)

            def get_uint16(self):
                return next(self.values)

        try:
            with patch("demo.client.messenger.send") as send, patch.object(
                DoInterestManager, "queueAllInterestsCompleteEvent"
            ), patch.object(
                DoInterestManager,
                "_DoInterestManager__verbose",
                return_value=False,
            ), patch.object(DoInterestManager, "printInterestsIfDebug", return_value=1):
                DemoClientRepository.handle_interest_done_message(
                    client, Datagram()
                )

            self.assertNotIn(handle, client._server_interest_pending)
            self.assertIn(handle, client._server_interest_complete)
            self.assertEqual(
                client.getServerInterestZones(5001), (GRID_STARTING_ZONE,)
            )
            send.assert_any_call("demo-server-interest-state-changed", [handle])
        finally:
            DoInterestManager._interests.pop(handle, None)

    def test_client_repository_reports_active_local_interest_zones(self):
        handle_id = 17
        state = InterestState(
            "local grid interest",
            InterestState.StateActive,
            0,
            None,
            5001,
            [6036, 6035],
            SimpleNamespace(num=0),
            True,
        )
        DoInterestManager._interests[handle_id] = state
        self.addCleanup(DoInterestManager._interests.pop, handle_id, None)
        handle = InterestHandle(handle_id)
        repository = DemoClientRepository.__new__(DemoClientRepository)

        self.assertEqual(repository.getClientInterestZones(handle), (6035, 6036))

    def test_ai_repository_dispatches_interest_completion_to_registered_callback(self):
        repository = DemoAIRepository.__new__(DemoAIRepository)
        repository.getMsgType = Mock(return_value=1204)
        repository.handle_client_agent_interest_done_resp = Mock()
        datagram = object()

        DemoAIRepository.handleDatagram(repository, datagram)

        repository.handle_client_agent_interest_done_resp.assert_called_once_with(
            datagram
        )

if __name__ == "__main__":
    unittest.main()
