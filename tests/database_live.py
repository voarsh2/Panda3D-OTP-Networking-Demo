"""Verify Astron Database create and full-object query callbacks live."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from direct.distributed.PyDatagram import PyDatagram
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import loadPrcFileData

from demo.constants import (
    DATABASE_CHANNEL,
    DC_FILE,
    MESSAGE_DIRECTOR_HOST,
    MESSAGE_DIRECTOR_PORT,
    STATE_SERVER_CHANNEL,
)
from demo.networking.internal_repository import AstronInternalRepository
from demo.networking.msgtypes import DBSERVER_OBJECT_DELETE


class DatabaseLiveCheck(ShowBase):
    def __init__(self, timeout_seconds):
        super().__init__()
        self.exit_code = 1
        self._finished = False
        self.do_id = None
        self.air = AstronInternalRepository(
            450100,
            serverId=STATE_SERVER_CHANNEL,
            dcFileNames=[DC_FILE],
            dcSuffix="AI",
        )
        self.accept("airConnected", self._on_connected)
        self.air.connect(MESSAGE_DIRECTOR_HOST, MESSAGE_DIRECTOR_PORT)
        self.taskMgr.doMethodLater(
            timeout_seconds,
            self._on_timeout,
            "database-live-timeout",
        )

    def _on_connected(self):
        self.dclass = self.air.dclassesByName["DemoBeaconAI"]
        self.air.dbInterface.createObject(
            DATABASE_CHANNEL,
            self.dclass,
            {"setActivationCount": (37,)},
            self._on_created,
        )

    def _on_created(self, do_id):
        if not do_id:
            self._fail("Astron Database did not create an object")
            return
        self.do_id = int(do_id)
        self.air.dbInterface.queryObject(
            DATABASE_CHANNEL,
            self.do_id,
            self._on_queried,
        )

    def _on_queried(self, dclass, fields):
        if dclass is None or dclass.getName() != "DemoBeacon":
            self._fail(f"Database returned the wrong DC class: {dclass}")
            return
        if fields != {"setActivationCount": (37,)}:
            self._fail(f"Database field values differ: {fields}")
            return
        datagram = PyDatagram()
        datagram.addServerHeader(
            DATABASE_CHANNEL, self.air.ourChannel, DBSERVER_OBJECT_DELETE
        )
        datagram.addUint32(self.do_id)
        self.air.send(datagram)
        self.air.dbInterface.queryObject(
            DATABASE_CHANNEL,
            self.do_id,
            self._on_deleted,
        )

    def _on_deleted(self, dclass, fields):
        if dclass is not None or fields is not None:
            self._fail(
                f"Temporary Database object was not deleted: "
                f"dclass={dclass}, fields={fields}"
            )
            return
        self._finish(
            0,
            f"PASS: Astron Database created, queried, and removed "
            f"temporary doId {self.do_id}",
        )

    def _on_timeout(self, task):
        self._fail("timed out before Database create/query callbacks completed")
        return Task.done

    def _fail(self, message):
        if self.do_id is not None:
            datagram = PyDatagram()
            datagram.addServerHeader(
                DATABASE_CHANNEL, self.air.ourChannel, DBSERVER_OBJECT_DELETE
            )
            datagram.addUint32(self.do_id)
            self.air.send(datagram)
        self._finish(1, f"FAIL: {message}")

    def _finish(self, code, message):
        if self._finished:
            return
        self._finished = True
        self.exit_code = code
        print(message, flush=True)
        self.taskMgr.remove("database-live-timeout")
        self.taskMgr.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Exercise Astron Database create and query messages."
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    loadPrcFileData("", "window-type none")
    check = DatabaseLiveCheck(args.timeout)
    check.run()
    return check.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
