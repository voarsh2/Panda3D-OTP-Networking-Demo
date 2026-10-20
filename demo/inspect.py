import argparse

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-type offscreen")

from demo.client import DemoClient
from demo.constants import DISTRICT_ID, LAB_ZONE, PERSISTENT_BEACON_ID_FILE


def beacon_snapshot(repository, beacon):
    return {
        "doId": int(beacon.doId),
        "parentId": int(beacon.parentId),
        "zoneId": int(beacon.zoneId),
        "activationCount": int(beacon.activation_count),
        "inRepository": repository.doId2do.get(beacon.doId) is beacon,
    }


def avatar_snapshot(repository, avatar):
    return {
        "doId": int(avatar.doId),
        "parentId": int(avatar.parentId),
        "zoneId": int(avatar.zoneId),
        "inRepository": repository.doId2do.get(avatar.doId) is avatar,
        "generated": bool(avatar.isGenerated()),
    }


def beacon_is_expected(state, expected_id):
    return (
        state["doId"] == int(expected_id)
        and state["parentId"] == DISTRICT_ID
        and state["zoneId"] == LAB_ZONE
        and state["activationCount"] > 0
        and state["inRepository"]
    )


def avatar_leave_snapshot(repository, avatar, beacon_id):
    beacon = repository.doId2do.get(int(beacon_id))
    avatar_state = avatar_snapshot(repository, avatar)
    return {
        "avatarId": avatar_state["doId"],
        "avatarParentId": avatar_state["parentId"],
        "avatarZoneId": avatar_state["zoneId"],
        "avatarInRepository": avatar_state["inRepository"],
        "avatarGenerated": avatar_state["generated"],
        "beaconInRepository": beacon is not None,
        "beaconGenerated": beacon.isGenerated() if beacon is not None else False,
    }


class DemoInspector(DemoClient):
    def __init__(self, name, include_lab=True):
        self.include_lab = include_lab
        super().__init__(name)
        self.accept("demo-district-generated", self._open_lab_interest)
        self.accept("demo-beacon-generated", self._inspect_beacon)
        self.accept("demo-avatar-generated", self._inspect_avatar)
        self.accept("demo-avatar-location-changed", self._inspect_avatar_location)
        self.accept("demo-avatar-left-view", self._inspect_avatar_leaving)

    def _open_lab_interest(self, district):
        if self.include_lab and self._lab_interest is None:
            self._lab_interest = self.repo.addInterest(
                district.doId, [LAB_ZONE], "terminal object inspector"
            )

    def _inspect_beacon(self, beacon):
        expected_id = int(PERSISTENT_BEACON_ID_FILE.read_text(encoding="utf-8").strip())
        state = beacon_snapshot(self.repo, beacon)
        print(
            "DO DemoBeacon "
            f"id={state['doId']} parent={state['parentId']} zone={state['zoneId']} "
            f"activationCount={state['activationCount']} "
            f"inRepository={state['inRepository']}",
            flush=True,
        )
        passed = beacon_is_expected(state, expected_id)
        print(
            "PASS: client repository contains the saved beacon with its live state."
            if passed
            else "FAIL: saved beacon state does not match the expected object.",
            flush=True,
        )

    def _inspect_avatar(self, avatar):
        in_repository = self.repo.doId2do.get(avatar.doId) is avatar
        print(
            f"DO DemoAvatar entered view: id={avatar.doId} "
            f"parent={avatar.parentId} zone={avatar.zoneId} "
            f"inRepository={in_repository} "
            f"name={avatar.name}",
            flush=True,
        )

    def _inspect_avatar_location(
        self, avatar, old_parent_id, old_zone_id, parent_id, zone_id
    ):
        state = avatar_snapshot(self.repo, avatar)
        print(
            f"DO DemoAvatar moved: id={state['doId']} "
            f"({old_parent_id}, {old_zone_id}) -> "
            f"({state['parentId']}, {state['zoneId']}) "
            f"inRepository={state['inRepository']} generated={state['generated']}",
            flush=True,
        )

    def _inspect_avatar_leaving(self, avatar):
        beacon_id = int(PERSISTENT_BEACON_ID_FILE.read_text(encoding="utf-8").strip())
        state = avatar_leave_snapshot(self.repo, avatar, beacon_id)
        print(
            f"DO DemoAvatar left view: id={state['avatarId']} name={avatar.name} "
            f"parent={state['avatarParentId']} zone={state['avatarZoneId']} "
            f"inRepository={state['avatarInRepository']} "
            f"generated={state['avatarGenerated']}; "
            f"savedBeaconInRepository={state['beaconInRepository']} "
            f"savedBeaconGenerated={state['beaconGenerated']}",
            flush=True,
        )
        if not state["avatarGenerated"] and state["beaconGenerated"]:
            print("PASS: session avatar left active view; saved beacon remains generated.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect live Panda3D distributed objects arriving from Astron."
    )
    parser.add_argument("--name", default="Inspector", help="name shown for this client")
    parser.add_argument(
        "--main-only", action="store_true", help="watch District zone 1 only"
    )
    args = parser.parse_args()
    DemoInspector(args.name, include_lab=not args.main_only).run()


if __name__ == "__main__":
    main()
