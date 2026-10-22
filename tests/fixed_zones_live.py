"""Verify fixed-zone visibility with two live Astron clients."""

import argparse
import multiprocessing
import sys
import threading
import time
from multiprocessing.connection import wait
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from direct.showbase.MessengerGlobal import messenger
from direct.task import Task
from panda3d.core import loadPrcFileData

from demo.client import DemoClient
from demo.constants import (
    DC_FILE,
    DISTRICT_ID,
    LAB_ZONE,
    MAIN_ZONE,
    MESSAGE_DIRECTOR_HOST,
    MESSAGE_DIRECTOR_PORT,
    STATE_SERVER_CHANNEL,
)
from demo.networking.internal_repository import AstronInternalRepository
from demo.objects import DemoAvatar

STATE_PROBE_CHANNEL = 450000

_demo_avatar_set_position = DemoAvatar.setPosition


def _report_demo_avatar_position(avatar, x, y):
    _demo_avatar_set_position(avatar, x, y)
    messenger.send(
        "fixed-zone-live-avatar-position", [avatar, float(x), float(y)]
    )


DemoAvatar.setPosition = _report_demo_avatar_position


class FixedZoneClient(DemoClient):
    def __init__(self, name, result_pipe, timeout_seconds):
        self.result_pipe = result_pipe
        self.timeout_seconds = timeout_seconds
        self._phase = "starting"
        self._all_interests_complete = False
        self._finished = False
        self.exit_code = 1
        self._main_interest_ready = False

        super().__init__(name)
        self.accept(
            self.repo.getAllInterestsCompleteEvent(),
            self._on_interests_complete,
        )
        self.taskMgr.doMethodLater(
            timeout_seconds,
            self._on_timeout,
            f"fixed-zone-live-timeout-{name}",
        )

    def _set_district(self, district):
        super()._set_district(district)
        self._main_interest_ready = False
        self._advance()

    def _on_interests_complete(self):
        self._all_interests_complete = True
        if self.district is not None and self.district.main_interest is not None:
            zones = self.repo.getClientInterestZones(self.district.main_interest)
            self._main_interest_ready = zones == (MAIN_ZONE,)
        self._advance()

    def _snapshot(self, avatar=None):
        owner = self.owner_view
        avatar = avatar or owner
        if avatar is None:
            return None
        return {
            "doId": int(avatar.doId),
            "parentId": avatar.parentId,
            "zoneId": avatar.zoneId,
            "inRepository": self.repo.doId2do.get(avatar.doId) is avatar,
            "generated": bool(avatar.isGenerated()),
        }

    def _send_result(self, kind, details):
        self.result_pipe.send((kind, details))

    def _on_timeout(self, task):
        self._fail(
            f"timed out during {self._phase}; "
            f"state={self._snapshot()}"
        )
        return Task.done

    def _fail(self, message):
        self._finish("fail", message)

    def _finish(self, kind, message):
        if self._finished:
            return
        self._finished = True
        self.exit_code = 0 if kind in ("pass", "stopped") else 1
        self._send_result(kind, message)
        self.taskMgr.remove(f"fixed-zone-live-timeout-{self.name}")
        self.taskMgr.stop()


class FixedZoneMover(FixedZoneClient):
    """Drive through the Owner View; the observer and State Server prove location."""

    START_EVENT = "fixed-zone-live-start"
    REVERSE_EVENT = "fixed-zone-live-reverse"

    def __init__(self, name, result_pipe, control_pipe, timeout_seconds):
        self._owner_position = None
        self._control_pipe = control_pipe
        super().__init__(name, result_pipe, timeout_seconds)
        self.accept("demo-owner-avatar-position", self._on_owner_position)
        self.accept(self.START_EVENT, self._start)
        self.accept(self.REVERSE_EVENT, self._reverse)
        self.accept("fixed-zone-live-snapshot", self._send_owner_snapshot)
        self.accept("fixed-zone-live-stop", self._stop)
        threading.Thread(
            target=self._wait_for_reverse,
            name="fixed-zone-live-control",
            daemon=True,
        ).start()
        self._advance()

    def _set_owner_view(self, owner_view):
        super()._set_owner_view(owner_view)
        self._advance()

    def _on_owner_position(self, x, y):
        self._owner_position = (float(x), float(y))
        self._advance()

    def _wait_for_reverse(self):
        try:
            while True:
                command = self._control_pipe.recv()
                event = {
                    "start": self.START_EVENT,
                    "reverse": self.REVERSE_EVENT,
                    "snapshot": "fixed-zone-live-snapshot",
                    "stop": "fixed-zone-live-stop",
                }.get(command)
                if event is None:
                    return
                from direct.showbase.MessengerGlobal import messenger

                messenger.send(event, taskChain="default")
                if command == "stop":
                    return
        except (EOFError, OSError):
            pass

    def _start(self):
        if self._phase != "waiting-for-start":
            self._fail(f"received start while in phase {self._phase}")
            return
        self._phase = "moving-east"
        self.owner_view.requestMove(1, 0)

    def _reverse(self):
        if self._phase != "moving-east":
            self._fail(f"received reverse while in phase {self._phase}")
            return
        self._phase = "moving-west"
        self.owner_view.requestMove(-1, 0)

    def _send_owner_snapshot(self):
        self._send_result(
            "owner-snapshot",
            {
                "doId": int(self.owner_view.doId),
                "ownerViewPresent": (
                    self.repo.doId2ownerView.get(self.owner_view.doId)
                    is self.owner_view
                ),
                "ownerPosition": tuple(self.owner_view.last_position),
            },
        )

    def _stop(self):
        if self._phase != "moving-west":
            self._fail(f"received stop while in phase {self._phase}")
            return
        self.owner_view.requestMove(0, 0)
        self._finish(
            "stopped",
            {
                "doId": int(self.owner_view.doId),
                "ownerViewPresent": (
                    self.repo.doId2ownerView.get(self.owner_view.doId)
                    is self.owner_view
                ),
                "ownerViewGenerated": bool(self.owner_view.isGenerated()),
                "ownerPosition": tuple(self.owner_view.last_position),
            },
        )

    def _advance(self):
        if self._finished or self.owner_view is None:
            return
        if (
            self._phase == "starting"
            and self._main_interest_ready
            and self._owner_position is not None
        ):
            state = self._snapshot()
            if (
                not state["generated"]
                or self.repo.doId2ownerView.get(self.owner_view.doId)
                is not self.owner_view
            ):
                self._fail(f"Owner View is not generated: {state}")
                return
            if self._owner_position[0] >= 4.0:
                self._fail(f"Owner View starts beyond the zone boundary: {state}")
                return
            self._phase = "waiting-for-start"
            self._send_result("owner-ready", state)


class FixedZoneObserver(FixedZoneClient):
    def __init__(self, name, result_pipe, alice_name, timeout_seconds):
        self.alice_name = alice_name
        self._alice_do_id = None
        self._lab_interest = None
        self._zone_2_generated = False
        self._zone_2_add_complete = False
        self._zone_2_left = False
        self._zone_2_remove_complete = False
        self._zone_2_location_checked = False
        self._zone_2_position_reached = False
        self._alice_position_x = None
        self._pending_generate_ids = set()
        self._state_probe_connected = False
        self._state_checks = {}
        self._location_events = []
        super().__init__(name, result_pipe, timeout_seconds)
        self.accept("demo-avatar-generated", self._on_avatar_generated)
        self.accept("demo-avatar-location-changed", self._on_avatar_location)
        self.accept("CLIENT_OBJECT_LEAVING", self._on_object_leaving)
        self.accept(
            "fixed-zone-live-avatar-position", self._on_avatar_position
        )
        self.accept(
            "fixed-zone-live-observer-zone-2-added",
            self._on_zone_2_added,
        )
        self.accept(
            "fixed-zone-live-observer-zone-2-removed",
            self._on_zone_2_removed,
        )
        self.accept("airConnected", self._on_state_probe_connected)
        self.state_probe = AstronInternalRepository(
            STATE_PROBE_CHANNEL,
            serverId=STATE_SERVER_CHANNEL,
            dcFileNames=[DC_FILE],
            dcSuffix="AI",
        )
        self.state_probe.connect(MESSAGE_DIRECTOR_HOST, MESSAGE_DIRECTOR_PORT)

    def _on_state_probe_connected(self):
        self._state_probe_connected = True
        self._advance()

    def _query_state_server(self, label, expected_zone):
        def on_location(do_id, parent_id, zone_id):
            state = {
                "doId": int(do_id),
                "parentId": int(parent_id),
                "zoneId": int(zone_id),
            }
            if (state["parentId"], state["zoneId"]) != (
                DISTRICT_ID,
                expected_zone,
            ):
                self._fail(
                    f"State Server location mismatch at {label}: "
                    f"expected {(DISTRICT_ID, expected_zone)}, got {state}"
                )
                return
            self._state_checks[label] = state
            if label == "after-zone-1-leave":
                self._phase = "opening-zone-2"
                self._lab_interest = self.repo.addInterest(
                    DISTRICT_ID,
                    [LAB_ZONE],
                    "fixed-zone live observer interest",
                    "fixed-zone-live-observer-zone-2-added",
                )
            elif label == "zone-2-generated":
                self._zone_2_location_checked = True
            elif label == "after-zone-2-close":
                self._phase = "waiting-for-alice-in-zone-1-again"
                self._send_result(
                    "zone-2-closed",
                    {
                        "doId": self._alice_do_id,
                        "stateServerLocation": state,
                        "zone2InterestRemoved": self._zone_2_remove_complete,
                    },
                )
            elif label == "returned-to-zone-1":
                avatar = self.repo.doId2do.get(self._alice_do_id)
                self._finish(
                    "pass",
                    {
                        "doId": self._alice_do_id,
                        "observedZones": [MAIN_ZONE, LAB_ZONE, MAIN_ZONE],
                        "locationEvents": self._location_events,
                        "stateServerLocations": self._state_checks,
                        "final": self._snapshot(avatar),
                    },
                )

        self.state_probe.getLocation(self._alice_do_id, on_location)

    def _advance(self):
        if self._finished:
            return
        if (
            self._phase == "starting"
            and self.owner_view is not None
            and self._main_interest_ready
            and self._state_probe_connected
        ):
            self._phase = "waiting-for-alice-in-zone-1"
            self._send_result(
                "ready",
                {
                    "mainInterestZones": self.repo.getClientInterestZones(
                        self.district.main_interest
                    ),
                    "observerOwnerId": int(self.owner_view.doId),
                },
            )
        elif (
            self._phase == "opening-zone-2"
            and self._zone_2_add_complete
            and self._zone_2_generated
            and self._zone_2_location_checked
            and self._zone_2_position_reached
        ):
            self._phase = "closing-zone-2"
            self._lab_interest = self.repo.removeInterest(
                self._lab_interest,
                "fixed-zone-live-observer-zone-2-removed",
            )
        elif (
            self._phase == "closing-zone-2"
            and self._zone_2_left
            and self._zone_2_remove_complete
        ):
            self._phase = "checking-zone-2-after-close"
            self._query_state_server("after-zone-2-close", LAB_ZONE)

    def _on_avatar_generated(self, avatar):
        if (
            self.repo.doId2do.get(avatar.doId) is not avatar
            or avatar.name != self.alice_name
        ):
            return
        if self._alice_do_id is None:
            self._watch_full_generation(avatar)
        elif int(avatar.doId) != self._alice_do_id:
            self._fail(f"Alice object identity changed: {self._snapshot(avatar)}")
        elif self._phase in (
            "opening-zone-2",
            "waiting-for-alice-in-zone-1-again",
        ):
            self._watch_full_generation(avatar)

    def _watch_full_generation(self, avatar):
        # demo-avatar-generated runs inside announceGenerate, before Direct's
        # postGenerateMessage marks the object ESGenerated.
        do_id = int(avatar.doId)
        if do_id in self._pending_generate_ids:
            return
        self._pending_generate_ids.add(do_id)
        self.acceptOnce(
            avatar.uniqueName("generate"),
            self._on_fully_generated,
            [do_id],
        )

    def _on_fully_generated(self, do_id, generated_avatar):
        self._pending_generate_ids.discard(int(do_id))
        avatar = self.repo.doId2do.get(int(do_id))
        if avatar is not generated_avatar or not avatar.isGenerated():
            self._fail(
                f"Direct generate event disagrees with repository state: "
                f"doId={do_id}, object={self._snapshot(avatar)}"
            )
            return
        state = self._snapshot(avatar)
        if self._alice_do_id is None:
            if (avatar.parentId, avatar.zoneId) != (DISTRICT_ID, MAIN_ZONE):
                self._fail(f"Alice did not enter observer zone 1: {state}")
                return
            self._alice_do_id = int(avatar.doId)
            self._phase = "waiting-for-alice-to-leave-zone-1"
            self._send_result("alice-generated-in-zone-1", state)
        elif self._phase == "opening-zone-2":
            if (avatar.parentId, avatar.zoneId) != (DISTRICT_ID, LAB_ZONE):
                self._fail(f"Alice generated outside observer zone 2: {state}")
                return
            self._zone_2_generated = True
            self._query_state_server("zone-2-generated", LAB_ZONE)
        elif self._phase == "waiting-for-alice-in-zone-1-again":
            if (avatar.parentId, avatar.zoneId) != (DISTRICT_ID, MAIN_ZONE):
                self._fail(f"Alice returned outside observer zone 1: {state}")
                return
            self._query_state_server("returned-to-zone-1", MAIN_ZONE)
        self._advance()

    def _on_avatar_location(
        self, avatar, old_parent_id, old_zone_id, parent_id, zone_id
    ):
        if self._alice_do_id != int(avatar.doId):
            return
        self._location_events.append(
            (int(old_parent_id), int(old_zone_id), int(parent_id), int(zone_id))
        )

    def _on_avatar_position(self, avatar, x, _y):
        if (
            avatar.name != self.alice_name
            or self.repo.doId2do.get(avatar.doId) is not avatar
        ):
            return
        self._alice_position_x = float(x)
        if (
            int(avatar.doId) == self._alice_do_id
            and self._phase == "opening-zone-2"
            and self._alice_position_x >= 8.0
        ):
            self._zone_2_position_reached = True
            self._advance()

    def _on_object_leaving(self, do_id):
        if self._alice_do_id != int(do_id):
            return
        if self.repo.doId2do.get(self._alice_do_id) is not None:
            self._fail(
                f"CLIENT_OBJECT_LEAVING fired while Alice remains in doId2do: "
                f"{self._snapshot(self.repo.doId2do[self._alice_do_id])}"
            )
            return
        if self._phase == "waiting-for-alice-to-leave-zone-1":
            self._phase = "checking-zone-2-location"
            self._query_state_server("after-zone-1-leave", LAB_ZONE)
        elif self._phase == "closing-zone-2":
            self._zone_2_left = True
            self._advance()

    def _on_zone_2_added(self):
        self._zone_2_add_complete = True
        self._advance()

    def _on_zone_2_removed(self):
        self._zone_2_remove_complete = True
        self._advance()


def _run_client(client_type, args):
    loadPrcFileData("", "window-type offscreen")
    client = client_type(*args)
    client.run()
    raise SystemExit(client.exit_code)


def _child_entry(client_type, args):
    _run_client(client_type, args)


def _receive_until(connection, process, deadline):
    remaining = max(0.0, deadline - time.monotonic())
    ready = wait([connection, process.sentinel], timeout=remaining)
    if connection in ready:
        try:
            return connection.recv()
        except EOFError:
            return ("fail", "client closed its result connection")
    if process.sentinel in ready:
        return ("fail", f"client process exited with code {process.exitcode}")
    return ("fail", "live fixed-zone test timed out")


def main():
    parser = argparse.ArgumentParser(
        description="Verify fixed-zone crossing and visibility with two live clients."
    )
    parser.add_argument("--name", default="FixedZoneAlice")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    # Keep one ClientRepository per process; Direct's interest map is class-level.
    context = multiprocessing.get_context("spawn")
    bob_parent, bob_child = context.Pipe(duplex=True)
    alice_parent, alice_child = context.Pipe(duplex=True)
    bob = context.Process(
        target=_child_entry,
        args=(FixedZoneObserver, ("FixedZoneBob", bob_child, args.name, args.timeout)),
        name="FixedZoneBob",
    )
    alice = None
    # Let each client's watchdog send its phase and object snapshot first.
    deadline = time.monotonic() + args.timeout + 5.0
    try:
        bob.start()
        bob_child.close()
        kind, details = _receive_until(bob_parent, bob, deadline)
        if kind != "ready":
            print(f"FAIL: observer did not become ready: {kind}: {details}")
            return 1

        alice = context.Process(
            target=_child_entry,
            args=(
                FixedZoneMover,
                (args.name, alice_child, alice_child, args.timeout),
            ),
            name=args.name,
        )
        alice.start()
        alice_child.close()

        reversed_movement = False
        alice_owner_ready = False
        alice_generated = False
        movement_started = False
        bob_passed = False
        mover_stopped = False
        alice_details = None
        bob_details = None
        while not (mover_stopped and bob_passed):
            waitables = []
            if not bob_passed:
                waitables.extend((bob_parent, bob.sentinel))
            if not mover_stopped:
                waitables.extend((alice_parent, alice.sentinel))
            source = wait(waitables, timeout=max(0.0, deadline - time.monotonic()))
            if not source:
                print(
                    "FAIL: fixed-zone live check timed out; "
                    f"reversed-movement={reversed_movement}"
                )
                return 1
            if bob_parent in source:
                try:
                    kind, details = bob_parent.recv()
                except EOFError:
                    print("FAIL: observer closed its result connection")
                    return 1
                if kind == "fail":
                    print(f"FAIL: observer: {details}")
                    return 1
                if kind == "alice-generated-in-zone-1":
                    alice_generated = True
                    if alice_owner_ready and not movement_started:
                        alice_parent.send("start")
                        movement_started = True
                elif kind == "zone-2-closed":
                    bob_details = details
                    alice_parent.send("snapshot")
                elif kind == "pass":
                    bob_passed = True
                    bob_details = details
                    bob_parent.close()
                    alice_parent.send("stop")
            elif alice_parent in source:
                try:
                    kind, details = alice_parent.recv()
                except EOFError:
                    print("FAIL: mover closed its result connection")
                    return 1
                if kind == "fail":
                    print(f"FAIL: mover: {details}")
                    return 1
                if kind == "owner-ready":
                    alice_owner_ready = True
                    if alice_generated and not movement_started:
                        alice_parent.send("start")
                        movement_started = True
                elif kind == "owner-snapshot":
                    if details["ownerPosition"][0] != 8.0:
                        print(
                            "FAIL: Owner View stopped receiving position "
                            f"outside its ordinary interest: {details}"
                        )
                        return 1
                    if not reversed_movement:
                        alice_parent.send("reverse")
                        reversed_movement = True
                elif kind == "stopped":
                    mover_stopped = True
                    alice_details = details
                    alice_parent.close()
            elif bob.sentinel in source:
                print(f"FAIL: observer exited with code {bob.exitcode}")
                return 1
            elif alice.sentinel in source:
                print(f"FAIL: mover exited with code {alice.exitcode}")
                return 1

        print(
            "PASS: fixed-zone crossing verified with two clients; "
            f"Alice={alice_details}; Bob={bob_details}"
        )
        return 0
    finally:
        for process in (alice, bob):
            if process is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
        for connection in (bob_parent, bob_child, alice_parent, alice_child):
            try:
                connection.close()
            except OSError:
                pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
