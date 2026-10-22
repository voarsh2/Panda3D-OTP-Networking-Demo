"""Check the live database-backed beacon and its value after restart."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from direct.task import Task
from panda3d.core import loadPrcFileData

from demo.client import DemoClient
from demo.constants import DISTRICT_ID, LAB_ZONE, PERSISTENT_BEACON_ID_FILE


class PersistenceLiveCheck(DemoClient):
    def __init__(self, name, snapshot_path, timeout_seconds):
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        self.timeout_seconds = timeout_seconds
        self._interest_complete = False
        self._beacon = None
        self._finished = False
        self.exit_code = 1

        super().__init__(name)
        self.accept("demo-beacon-generated", self._on_beacon_generated)
        self.accept(
            "persistence-live-interest-complete",
            self._on_interest_complete,
        )
        self.taskMgr.doMethodLater(
            timeout_seconds,
            self._on_timeout,
            "persistence-live-timeout",
        )

    def _set_district(self, district):
        super()._set_district(district)
        self.repo.addInterest(
            district.doId,
            [LAB_ZONE],
            "persistence live check",
            "persistence-live-interest-complete",
        )

    def _on_interest_complete(self):
        self._interest_complete = True
        self._finish_if_ready()

    def _on_beacon_generated(self, beacon):
        if self.repo.doId2do.get(beacon.doId) is not beacon:
            self._fail(f"beacon generate event disagrees with repository: {beacon.doId}")
            return
        self._beacon = beacon
        self.acceptOnce(
            beacon.uniqueName("generate"),
            self._on_fully_generated,
            [int(beacon.doId)],
        )

    def _on_fully_generated(self, do_id, beacon):
        if (
            self._beacon is not beacon
            or int(beacon.doId) != int(do_id)
            or not beacon.isGenerated()
        ):
            self._fail(f"Direct generate state disagrees with beacon {do_id}")
            return
        self._finish_if_ready()

    def _finish_if_ready(self):
        if self._finished or not self._interest_complete or self._beacon is None:
            return
        expected_id = int(
            PERSISTENT_BEACON_ID_FILE.read_text(encoding="utf-8").strip()
        )
        beacon = self._beacon
        state = {
            "doId": int(beacon.doId),
            "parentId": int(beacon.parentId),
            "zoneId": int(beacon.zoneId),
            "activationCount": int(beacon.activation_count),
            "inRepository": self.repo.doId2do.get(beacon.doId) is beacon,
            "generated": bool(beacon.isGenerated()),
        }
        if (
            state["doId"] != expected_id
            or state["parentId"] != DISTRICT_ID
            or state["zoneId"] != LAB_ZONE
            or not state["inRepository"]
            or not state["generated"]
            or state["activationCount"] < 1
        ):
            self._fail(f"live beacon state is invalid: {state}")
            return

        previous = None
        if self.snapshot_path is not None and self.snapshot_path.exists():
            previous = int(self.snapshot_path.read_text(encoding="utf-8").strip())
            if state["activationCount"] <= previous:
                self._fail(
                    "beacon activation count did not increase after restart: "
                    f"previous={previous}, current={state['activationCount']}, "
                    f"state={state}"
                )
                return
        if self.snapshot_path is not None:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.snapshot_path.write_text(
                f"{state['activationCount']}\n", encoding="utf-8"
            )
        self._finish(
            0,
            {
                "state": state,
                "previousActivationCount": previous,
                "snapshot": str(self.snapshot_path),
            },
        )

    def _on_timeout(self, task):
        state = None
        if self._beacon is not None:
            state = {
                "doId": int(self._beacon.doId),
                "parentId": self._beacon.parentId,
                "zoneId": self._beacon.zoneId,
                "activationCount": self._beacon.activation_count,
                "generated": bool(self._beacon.isGenerated()),
            }
        self._fail(
            f"timed out waiting for live beacon state; "
            f"interestComplete={self._interest_complete}, beacon={state}"
        )
        return Task.done

    def _fail(self, message):
        self._finish(1, message)

    def _finish(self, code, result):
        if self._finished:
            return
        self._finished = True
        self.exit_code = code
        print(
            f"{'PASS' if code == 0 else 'FAIL'}: persistence live check: {result}",
            flush=True,
        )
        self.taskMgr.remove("persistence-live-timeout")
        self.taskMgr.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Verify the live persistent beacon; rerun after service restart to compare counts."
    )
    parser.add_argument("--name", default="PersistenceCheck")
    parser.add_argument(
        "--snapshot",
        help="optional file storing a baseline count for comparison after restart",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    loadPrcFileData("", "window-type offscreen")
    client = PersistenceLiveCheck(args.name, args.snapshot, args.timeout)
    client.run()
    return client.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
