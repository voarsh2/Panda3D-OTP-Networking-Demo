"""Run against a live grid-enabled Astron, UberDOG, and AI stack."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "references" / "panda3d-astron"))

from panda3d.core import TextNode, loadPrcFileData
from direct.gui.OnscreenText import OnscreenText

from direct.task import Task

from demo.cartesian_grid import grid_interest_window
from demo.cartesian_grid_client import DemoCartesianGridClient


class CartesianGridLiveCheck(DemoCartesianGridClient):
    def __init__(self, name, server_grid_interest, timeout_seconds, ui_mode=False):
        self._phase = "initial"
        self._all_interests_complete = False
        self._initial_center = None
        self._initial_zone = None
        self._target_zone = None
        self._initial_zones = ()
        self._beacon = None
        self._beacon_left = False
        self._probe_id = None
        self._probe_generated = False
        self._probe_generated_event_seen = False
        self._probe_left = False
        self._probe_reentered = False
        self._probe_zones = set()
        self.exit_code = 1
        self._finished = False
        self.ui_mode = ui_mode

        super().__init__(
            name,
            show_grid=ui_mode,
            server_grid_interest=server_grid_interest,
        )
        self._ui_status = None
        if ui_mode:
            self._ui_status = OnscreenText(
                text="UI CHECK RUNNING\nWaiting for grid interests",
                parent=self.aspect2d,
                pos=(0, 0.62),
                scale=0.06,
                fg=(1, 1, 1, 1),
                bg=(0, 0, 0, 0.7),
                align=TextNode.ACenter,
                mayChange=True,
            )
        self.accept(
            self.repo.getAllInterestsCompleteEvent(), self._on_interests_complete
        )
        self.accept(
            "demo-owner-avatar-location-changed", self._on_owner_location
        )
        self.accept("demo-beacon-generated", self._on_beacon_generated)
        self.accept("demo-beacon-left-view", self._on_beacon_left)
        self.accept("demo-grid-probe-generated", self._on_probe_generated)
        self.accept("demo-grid-probe-left-view", self._on_probe_left)
        self.accept("demo-grid-probe-location-changed", self._on_probe_moved)
        self.taskMgr.doMethodLater(
            timeout_seconds,
            self._on_timeout,
            "grid-live-check-timeout",
        )

    def _set_grid(self, grid):
        super()._set_grid(grid)
        self._advance()

    def _set_district(self, district):
        super()._set_district(district)
        self._advance()

    def _set_owner_view(self, owner_view):
        super()._set_owner_view(owner_view)
        self._advance()

    def _set_owner_position(self, x, y):
        super()._set_owner_position(x, y)
        self._advance()

    def _on_owner_location(self, owner_view, parent_id, zone_id):
        if owner_view is not self.owner_view:
            return
        if self._phase == "moving":
            if parent_id != self.grid.doId:
                self.owner_view.requestMove(0, 0)
                self._fail(
                    f"avatar left the grid during the adjacent-cell check: "
                    f"parent={parent_id}, zone={zone_id}"
                )
                return
            if zone_id != self._initial_zone:
                self.owner_view.requestMove(0, 0)
                self._phase = "moved"
                self._show_phase("Owner View crossed a cell; checking its interest window")
        self._advance()

    def _show_phase(self, description):
        if self._ui_status is not None:
            self._ui_status.setText(f"UI CHECK RUNNING\n{description}")

    def _check_probe_state(self, probe, event):
        present = self.repo.doId2do.get(probe.doId) is probe
        generated = probe.isGenerated()
        if event == "generated":
            valid = present
        elif event == "left":
            valid = not present and not generated
        else:
            valid = present and generated
        if not valid:
            self._fail(
                f"probe lifecycle event disagrees with repository: "
                f"event={event}, present={present}, "
                f"generated={generated}, doId={probe.doId}"
            )
            return False
        if self._probe_id is not None and self._probe_id != probe.doId:
            self._fail(
                f"probe identity changed: expected {self._probe_id}, got {probe.doId}"
            )
            return False
        self._probe_id = probe.doId
        if event in ("generated", "moved"):
            self._probe_generated = True
            self._probe_zones.add(int(probe.zoneId))
            if self._probe_left:
                self._probe_reentered = True
        elif self._probe_generated_event_seen:
            self._probe_left = True
        return True

    def _on_probe_generated(self, probe):
        self._probe_generated_event_seen = True
        self._check_probe_state(probe, "generated")
        self._advance()

    def _on_probe_left(self, probe):
        self._check_probe_state(probe, "left")
        self._advance()

    def _on_probe_moved(self, probe, old_parent, old_zone):
        if self._check_probe_state(probe, "moved") and (
            old_parent,
            old_zone,
        ) != (probe.parentId, probe.zoneId):
            self._probe_zones.add(int(probe.zoneId))
        self._advance()

    def _on_interests_complete(self):
        self._all_interests_complete = True
        self._advance()

    def _active_grid_zones(self):
        if self.server_grid_interest:
            states = self.repo.getServerInterestStates(self.grid.doId)
            if not states or any(state != "complete" for _, _, state in states):
                return None
            return self.repo.getServerInterestZones(self.grid.doId)

        if self.repo.getServerInterestStates(self.grid.doId):
            raise AssertionError("AI-managed interests are active in client-local mode")
        if self._grid_interest is None:
            return ()
        return self.repo.getClientInterestZones(self._grid_interest)

    def _owner_view_is_present(self):
        return (
            self.owner_view is not None
            and self.repo.doId2ownerView.get(self.owner_view.doId) is self.owner_view
        )

    def _on_beacon_generated(self, beacon):
        present = self.repo.doId2do.get(beacon.doId) is beacon
        if not present:
            self._fail(
                f"beacon generated event but doId2do lacks {beacon.doId}"
            )
            return
        self._beacon = beacon
        self._advance()

    def _on_beacon_left(self, beacon):
        present = self.repo.doId2do.get(beacon.doId) is beacon
        if present or beacon.isGenerated():
            self._fail(
                f"beacon left-view event but object remains active: "
                f"id={beacon.doId}, present={present}, generated={beacon.isGenerated()}"
            )
            return
        self._beacon_left = True
        self._advance()

    def _advance(self):
        if self._finished or self.grid is None or self.owner_view is None:
            return
        if self._phase == "initial" and self.district is not None and self._all_interests_complete:
            zones = self._active_grid_zones()
            if zones is None:
                return
            _, expected = grid_interest_window(
                self.grid, (*self._owner_position, 0.0)
            )
            if zones != expected:
                self._fail(f"initial interest zones differ: expected {expected}, got {zones}")
                return
            if not self._owner_view_is_present():
                self._fail("Owner View is missing after login")
                return
            self._initial_center = self._grid_center
            self._initial_zone = self._grid_center
            origin_x, _, _ = self.grid.getZoneCellOrigin(self._initial_zone)
            self._target_zone = int(
                self.grid.getZoneFromXYZ(
                    (origin_x + self.grid.cellWidth + 0.01, self._owner_position[1], 0.0)
                )
            )
            if not self.grid.isValidZone(self._target_zone):
                self._fail("avatar has no adjacent east cell for the movement check")
                return
            self._initial_zones = zones
            self._phase = "opening-zone-2"
            self._all_interests_complete = False
            self._show_phase("Opening District zone 2 interest")
            self._toggle_lab_interest()

        elif (
            self._phase == "opening-zone-2"
            and self._all_interests_complete
            and self._beacon is not None
        ):
            self._phase = "closing-zone-2"
            self._beacon_left = False
            self._all_interests_complete = False
            self._show_phase("Closing zone 2 and checking beacon removal")
            self._toggle_lab_interest()

        elif (
            self._phase == "closing-zone-2"
            and self._all_interests_complete
            and self._beacon_left
        ):
            self._phase = "moving"
            self._all_interests_complete = False
            self._show_phase("Moving Owner View to the adjacent grid cell")
            self.owner_view.requestMove(1, 0)

        elif self._phase == "moved" and self._all_interests_complete:
            zones = self._active_grid_zones()
            if zones is None:
                return
            center, expected = grid_interest_window(
                self.grid, (*self._owner_position, 0.0)
            )
            if center is None:
                self._fail("avatar left the grid during the one-cell movement check")
                return
            if center == self._initial_center or zones != expected:
                self._fail(f"interest did not follow the moved avatar: got {zones}")
                return
            if not self._owner_view_is_present():
                self._fail("Owner View disappeared during a cell transition")
                return
            if (
                self.owner_view.parentId != self.grid.doId
                or self.owner_view.zoneId != center
            ):
                self._fail(
                    "Owner View location does not match its current cell: "
                    f"parent={self.owner_view.parentId}, "
                    f"zone={self.owner_view.zoneId}, cell={center}"
                )
                return
            if self.owner_view.zoneId != self._target_zone:
                self._fail(
                    f"movement crossed past the adjacent cell: expected "
                    f"{self._target_zone}, got {self.owner_view.zoneId}"
                )
                return
            self._phase = "probe-lifecycle"
            self._show_phase("Checking probe generation, leave, and re-entry")

        if (
            self._phase == "probe-lifecycle"
            and self._probe_reentered
            and len(self._probe_zones) > 1
        ):
            self._finish(
                0,
                f"PASS: {self._mode_name}; center {self._initial_center} -> "
                f"{self._grid_center}; interest window follows the new cell; Owner View "
                f"{self.owner_view.doId} persisted; probe {self._probe_id} crossed cells, "
                "left, and re-entered; "
                "zone 2 beacon generated and removed.",
            )

    @property
    def _mode_name(self):
        return "AI-managed" if self.server_grid_interest else "client-local"

    def _on_timeout(self, task):
        self._fail(f"timed out during {self._phase}")
        return Task.done

    def _fail(self, message):
        self._finish(1, f"FAIL: {message}")

    def _finish(self, code, message):
        if self._finished:
            return
        self._finished = True
        self.exit_code = code
        print(message, flush=True)
        self.taskMgr.remove("grid-live-check-timeout")
        if self._ui_status is not None:
            self._ui_status.setText(
                f"{'PASS' if code == 0 else 'FAIL'}\n{message}\nPress Escape to close"
            )
            self._ui_status.setFg(
                (0.25, 1.0, 0.35, 1.0) if code == 0 else (1.0, 0.3, 0.3, 1.0)
            )
            return
        self.taskMgr.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Verify a live Cartesian grid interest flow against Astron."
    )
    parser.add_argument("--name", default="GridCheck")
    parser.add_argument(
        "--server-grid-interest",
        action="store_true",
        help="match an AI server started with --ai-grid-interest",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="single watchdog in seconds; raise above Astron's configured interest_timeout",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="show the automated result in a visible window and keep it open",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    loadPrcFileData(
        "",
        "window-type onscreen" if args.ui else "window-type offscreen",
    )
    client = CartesianGridLiveCheck(
        args.name,
        args.server_grid_interest,
        args.timeout,
        ui_mode=args.ui,
    )
    client.run()
    return client.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
