import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        client._grid_interest = None
        client._owner_position = None
        client._grid_center = None
        client._interest_radius = None
        client._probe_do_id = None
        client._probe_zone = None
        client._probe_status = "WAITING"
        client._lab_interest = None
        client._hud_text = None
        client.grid_hud = SimpleNamespace(setText=Mock())
        client.repo = SimpleNamespace(
            getServerInterestStates=Mock(return_value=()),
            getServerInterestZones=Mock(return_value=()),
        )

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
            getServerInterestStates=Mock(return_value=()),
            getServerInterestZones=Mock(return_value=()),
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
        client._grid_interest = None
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
        client._grid_interest = None
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
            getServerInterestZones=Mock(return_value=()),
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

        completed_zones = (6026, 6027, 6034, 6035, 6036)
        client.repo.getServerInterestStates.return_value = (
            (0x8064, completed_zones, "complete"),
        )
        client.repo.getServerInterestZones.return_value = completed_zones
        client._hud_text = None
        DemoCartesianGridClient._update_hud(client)
        self.assertIn(
            "AI-managed (READY 5/5)",
            client.grid_hud.setText.call_args.args[0],
        )

        client.server_grid_interest = False
        client._grid_interest = InterestHandle(17)
        client._hud_text = None
        DemoCartesianGridClient._update_hud(client)
        self.assertIn(
            "Interest source: AI-managed + client-local (READY 5/5)",
            client.grid_hud.setText.call_args.args[0],
        )
        client.repo.getServerInterestStates.assert_called_with(5001)

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
        client._grid_interest = None
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
            getServerInterestStates=Mock(return_value=()),
            getServerInterestZones=Mock(return_value=()),
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

    def test_ai_manager_updates_one_server_owned_interest_zone_set(self):
        calls = []

        class Air:
            def client_add_interest_multiple(
                self, channel, handle, parent, zones, callback=None
            ):
                calls.append(
                    {
                        "kind": "add",
                        "channel": channel,
                        "handle": handle,
                        "parent": parent,
                        "zones": tuple(zones),
                        "callback": callback,
                    }
                )

            def client_remove_interest(self, channel, handle, callback=None):
                calls.append(
                    {
                        "kind": "remove",
                        "channel": channel,
                        "handle": handle,
                        "callback": callback,
                    }
                )

        grid = self.grid
        grid.doId = 5001
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        left_center = int(grid.getZoneFromXYZ((-2.0, 0.0, 0.0)))
        right_center = int(grid.getZoneFromXYZ((2.0, 0.0, 0.0)))
        outside_zone = GRID_STARTING_ZONE - 1

        with contextlib.redirect_stdout(io.StringIO()):
            manager.handleLocationChanged(grid, avatar, left_center)
            first_zones = manager.getInterestZones(grid, avatar)
            first = calls[0]
            first["callback"](first["channel"], first["handle"])
            manager.handleLocationChanged(grid, avatar, right_center)
            moved_zones = manager.getInterestZones(grid, avatar)
            second = calls[1]
            second["callback"](second["channel"], second["handle"])
            manager.handleLocationChanged(grid, avatar, outside_zone)
            removal = calls[2]
            removal["callback"](removal["channel"], removal["handle"])
            cleared_zones = manager.getInterestZones(grid, avatar)
            manager.handleLocationChanged(grid, avatar, left_center)
            reentry = calls[3]

        self.assertEqual(
            first_zones,
            grid_interest_window(grid, (-2.0, 0.0, 0.0))[1],
        )
        self.assertNotEqual(moved_zones, first_zones)
        self.assertEqual(cleared_zones, ())
        self.assertEqual(
            [call["kind"] for call in calls],
            ["add", "add", "remove", "add"],
        )
        self.assertEqual(first["zones"], first_zones)
        self.assertEqual(second["zones"], moved_zones)
        self.assertEqual(first["handle"], second["handle"])
        self.assertEqual(second["handle"], removal["handle"])
        self.assertEqual(first["handle"], 0x8064)
        self.assertEqual(first["parent"], grid.doId)
        self.assertEqual(reentry["handle"], 0x8065)

    def test_interest_id_allocator_skips_fixed_login_ids(self):
        manager = DemoWorldGridManagerAI(SimpleNamespace())
        state = {"next_interest_id": 0x7FF0}

        self.assertEqual(manager._allocateInterestId(state), 0xFFF2)
        self.assertEqual(state["next_interest_id"], 0x7FF3)

    def test_ai_interest_updates_coalesce_per_observer_without_blocking_others(self):
        calls = []
        scheduled = []

        class Air:
            def client_add_interest_multiple(
                self, channel, handle, parent, zones, callback=None
            ):
                calls.append(
                    {
                        "channel": channel,
                        "handle": handle,
                        "parent": parent,
                        "zones": tuple(zones),
                        "callback": callback,
                    }
                )

            def client_remove_interest(self, *_args, **_kwargs):
                raise AssertionError("no interests should be removed")

        def schedule(func, _name, extraArgs, appendTask):
            self.assertTrue(appendTask)
            scheduled.append((func, extraArgs))

        grid = self.grid
        grid.doId = 5001
        alice = SimpleNamespace(doId=900001, client_channel=100123)
        bob = SimpleNamespace(doId=900002, client_channel=100124)
        manager = DemoWorldGridManagerAI(Air())
        left_center = int(grid.getZoneFromXYZ((-2.0, 0.0, 0.0)))
        right_center = int(grid.getZoneFromXYZ((2.0, 0.0, 0.0)))

        with (
            patch("demo.cartesian_grid.taskMgr.add", side_effect=schedule),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            manager.handleLocationChanged(grid, alice, left_center)
            manager.handleLocationChanged(grid, alice, right_center)
            manager.handleLocationChanged(grid, bob, left_center)

            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["channel"], alice.client_channel)
            self.assertEqual(calls[1]["channel"], bob.client_channel)

            calls[1]["callback"](calls[1]["channel"], calls[1]["handle"])
            manager.handleLocationChanged(grid, bob, right_center)
            self.assertEqual(len(calls), 3)

            calls[0]["callback"](calls[0]["channel"], calls[0]["handle"])
            self.assertEqual(len(scheduled), 1)
            run_task, extra_args = scheduled.pop()
            run_task(*extra_args, SimpleNamespace())

        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[2]["channel"], bob.client_channel)
        self.assertEqual(calls[3]["channel"], alice.client_channel)
        self.assertEqual(calls[0]["handle"], calls[3]["handle"])
        self.assertEqual(calls[0]["zones"], grid_interest_window(grid, (-2, 0, 0))[1])
        self.assertEqual(calls[3]["zones"], grid_interest_window(grid, (2, 0, 0))[1])

    def test_ai_interest_reentry_waits_for_its_remove_callback(self):
        calls = []
        scheduled = []

        class Air:
            def client_add_interest_multiple(
                self, channel, handle, parent, zones, callback=None
            ):
                calls.append(("add", channel, handle, tuple(zones), callback))

            def client_remove_interest(self, channel, handle, callback=None):
                calls.append(("remove", channel, handle, (), callback))

        def schedule(func, _name, extraArgs, appendTask):
            self.assertTrue(appendTask)
            scheduled.append((func, extraArgs))

        grid = self.grid
        grid.doId = 5001
        avatar = SimpleNamespace(doId=900001, client_channel=100123)
        manager = DemoWorldGridManagerAI(Air())
        left_center = int(grid.getZoneFromXYZ((-2.0, 0.0, 0.0)))
        right_center = int(grid.getZoneFromXYZ((2.0, 0.0, 0.0)))

        with (
            patch("demo.cartesian_grid.taskMgr.add", side_effect=schedule),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            manager.handleLocationChanged(grid, avatar, left_center)
            calls[0][4](calls[0][1], calls[0][2])
            manager.clearAvatarInterest(grid, avatar)
            manager.handleLocationChanged(grid, avatar, right_center)
            self.assertEqual([call[0] for call in calls], ["add", "remove"])

            calls[1][4](calls[1][1], calls[1][2])
            run_task, extra_args = scheduled.pop()
            run_task(*extra_args, SimpleNamespace())
            calls[2][4](calls[2][1], calls[2][2])

        self.assertEqual([call[0] for call in calls], ["add", "remove", "add"])
        self.assertEqual(calls[0][2], calls[1][2])
        self.assertEqual(calls[1][2], calls[2][2])
        self.assertEqual(calls[2][3], grid_interest_window(grid, (2, 0, 0))[1])
        self.assertEqual(manager.getInterestZones(grid, avatar), calls[2][3])

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

    def test_remote_interest_removal_marks_interest_pending_delete(self):
        handle = 0x8064
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

    def test_client_local_interest_removal_avoids_server_cleanup(self):
        handle = 17
        state = InterestState(
            "local grid interest",
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

            self.assertEqual(state.state, InterestState.StateActive)
            self.assertEqual(state.context, 7)
            send.assert_called_once_with("CLIENT_REMOVE_INTEREST", [19, handle])
        finally:
            DoInterestManager._interests.pop(handle, None)

    def test_client_reports_server_interest_pending_until_done_response(self):
        handle = 0x8064
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
        handle = 0x8065
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

    def test_interest_inspection_separates_server_and_client_handles(self):
        local_id = 17
        server_id = 0x8064
        local_state = InterestState(
            "local grid interest",
            InterestState.StateActive,
            0,
            None,
            5001,
            [6035],
            SimpleNamespace(num=0),
            True,
        )
        server_state = InterestState(
            "AI grid interest",
            InterestState.StateActive,
            0,
            None,
            5001,
            [6034, 6035, 6036],
            SimpleNamespace(num=0),
            True,
        )
        DoInterestManager._interests[local_id] = local_state
        DoInterestManager._interests[server_id] = server_state
        self.addCleanup(DoInterestManager._interests.pop, local_id, None)
        self.addCleanup(DoInterestManager._interests.pop, server_id, None)
        repository = DemoClientRepository.__new__(DemoClientRepository)
        repository._server_interest_pending = set()
        repository._server_interest_complete = {server_id}

        self.assertEqual(
            repository.getServerInterestStates(5001),
            ((server_id, (6034, 6035, 6036), "complete"),),
        )
        self.assertEqual(
            repository.getServerInterestZones(5001),
            (6034, 6035, 6036),
        )

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
