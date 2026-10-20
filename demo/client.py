import argparse

from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.distributed.DoInterestManager import DoInterestManager, InterestState
from direct.showbase.MessengerGlobal import messenger
from panda3d.core import URLSpec, WindowProperties
from panda3d_astron.repository import AstronClientRepository

from demo.constants import (
    CLIENT_AGENT_HOST,
    CLIENT_AGENT_PORT,
    DC_FILE,
    GAME_ROOT_ID,
    LAB_ZONE,
    LOGIN_MANAGER_ID,
    MANAGEMENT_ZONE,
    VERSION_STRING,
)


class DemoClientRepository(AstronClientRepository):
    StopVisibilityEvent = "demo-stop-cartesian-grid-visibility"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._server_interest_pending = set()
        self._server_interest_complete = set()

    def add_internal_interest_handle(self, context, interest_id, parent_id, zones):
        super().add_internal_interest_handle(
            context, interest_id, parent_id, zones
        )
        # DoInterestManager reserves bit 15 for interests controlled by the AI.
        if interest_id & 0x8000:
            self._server_interest_pending.add(interest_id)
            self._server_interest_complete.discard(interest_id)

    def handle_interest_done_message(self, di):
        context = di.get_uint32()
        interest_id = di.get_uint16()

        class InterestDoneIterator:
            def __init__(self, context, interest_id):
                self.values = iter((context, interest_id))

            def getUint32(self):
                return next(self.values)

            def getUint16(self):
                return next(self.values)

        DoInterestManager.handleInterestDoneMessage(
            self, InterestDoneIterator(context, interest_id)
        )
        if interest_id & 0x8000:
            self._server_interest_pending.discard(interest_id)
            state = DoInterestManager._interests.get(interest_id)
            if state is not None and not state.isPendingDelete():
                self._server_interest_complete.add(interest_id)
            else:
                self._server_interest_complete.discard(interest_id)
            messenger.send("demo-server-interest-state-changed", [interest_id])

    def getClientInterestZones(self, handle):
        if handle is None or not self.isValidInterestHandle(handle):
            return ()
        state = DoInterestManager._interests.get(handle.asInt())
        if state is None or state.isPendingDelete():
            return ()
        return tuple(sorted(int(zone) for zone in state.zoneIdList))

    def getServerInterestStates(self, parent_id):
        return tuple(
            sorted(
                (
                    handle,
                    tuple(state.zoneIdList),
                    "removing"
                    if state.isPendingDelete()
                    else "pending"
                    if handle in self._server_interest_pending
                    else "complete"
                    if handle in self._server_interest_complete
                    else "unconfirmed",
                )
                for handle, state in DoInterestManager._interests.items()
                if handle & 0x8000 and state.parentId == parent_id
            )
        )

    def getServerInterestZones(self, parent_id):
        return tuple(
            sorted(
                {
                    zone
                    for handle in self._server_interest_complete
                    for state in (DoInterestManager._interests.get(handle),)
                    if state is not None
                    if handle & 0x8000
                    and state.parentId == parent_id
                    and not state.isPendingDelete()
                    for zone in state.zoneIdList
                }
            )
        )

    def handle_remove_interest(self, di):
        context = di.get_uint32()
        interest_id = di.get_uint16()
        state = DoInterestManager._interests.get(interest_id)
        # DoInterestManager owns local removal state; AI IDs need this extra cleanup.
        if interest_id & 0x8000 and state is not None:
            state.clearEvents()
            state.state = InterestState.StatePendingDel
            state.context = context
            self._considerRemoveInterest(interest_id)
        messenger.send("CLIENT_REMOVE_INTEREST", [context, interest_id])

    def handleObjectLocation(self, di):
        do_id = di.getUint32()
        parent_id = di.getUint32()
        zone_id = di.getUint32()

        dist_obj = self.doId2do.get(do_id)
        if dist_obj is not None:
            dist_obj.setLocation(parent_id, zone_id)
            return

        owner_view = self.doId2ownerView.get(do_id)
        if owner_view is not None:
            # Owner Views are outside doId2do and are not part of interest tracking.
            owner_view.parentId = parent_id
            owner_view.zoneId = zone_id
            messenger.send(
                "demo-owner-avatar-location-changed",
                [owner_view, parent_id, zone_id],
            )
            return

        self.notify.warning(
            f"handleObjectLocation: Asked to update non-existent obj: {do_id}"
        )


class DemoClient(ShowBase):
    def __init__(self, name, extra_dc_file_names=()):
        super().__init__()
        if self.win is not None and hasattr(self.win, "requestProperties"):
            properties = WindowProperties()
            properties.setTitle(f"Panda3D Networking Demo - {name}")
            self.win.requestProperties(properties)
        self.disableMouse()
        self.camera.setPos(0, -18, 14)
        self.camera.lookAt(0, 0, 0)
        self.accept("escape", self.userExit)

        self.name = name
        self.owner_view = None
        self.district = None
        self._pressed = set()
        self._lab_interest = None
        self._district_interest = None

        self.help = OnscreenText(
            text="Arrow keys: move; cross x=4 to enter zone 2\n"
            "Tab: toggle whole zone 2 interest (lab beacon)\n"
            "Open a second client to watch the same world",
            pos=(0, 0.88),
            scale=0.05,
            fg=(1, 1, 1, 1),
            shadow=(0, 0, 0, 0.7),
        )

        self.accept("demo-avatar-owner", self._set_owner_view)
        self.accept("demo-district-generated", self._set_district)
        self.accept("CLIENT_HELLO_RESP", self._on_hello)
        self.accept("CLIENT_EJECT", self._on_eject)
        self.accept("LOST_CONNECTION", self._on_lost_connection)
        self.accept("arrow_left", self._key, ["left", True])
        self.accept("arrow_left-up", self._key, ["left", False])
        self.accept("arrow_right", self._key, ["right", True])
        self.accept("arrow_right-up", self._key, ["right", False])
        self.accept("arrow_up", self._key, ["up", True])
        self.accept("arrow_up-up", self._key, ["up", False])
        self.accept("arrow_down", self._key, ["down", True])
        self.accept("arrow_down-up", self._key, ["down", False])
        self.accept("tab", self._toggle_lab_interest)

        self.repo = DemoClientRepository(
            dcFileNames=[DC_FILE, *extra_dc_file_names],
            connectMethod=AstronClientRepository.CM_NET,
        )
        self.repo.GameGlobalsId = GAME_ROOT_ID
        url = URLSpec()
        url.setServer(CLIENT_AGENT_HOST)
        url.setPort(CLIENT_AGENT_PORT)
        self.repo.connect(
            [url],
            successCallback=self._connection_succeeded,
            failureCallback=self._connection_failed,
        )

    def _connection_succeeded(self, *args):
        self.repo.sendHello(VERSION_STRING)

    def _connection_failed(self, *args):
        self.notify.error("Could not connect to Astron's Client Agent")

    def _on_hello(self, *args):
        login_manager = self.repo.generateGlobalObject(
            LOGIN_MANAGER_ID, "DemoLoginManager"
        )
        login_manager.login(self.name)

    def _set_owner_view(self, owner_view):
        self.owner_view = owner_view
        if self._district_interest is None:
            self._district_interest = self.repo.addInterest(
                GAME_ROOT_ID, [MANAGEMENT_ZONE], "demo game directory"
            )

    def _set_district(self, district):
        self.district = district

    def _key(self, key, is_down):
        if is_down:
            self._pressed.add(key)
        else:
            self._pressed.discard(key)

        if self.owner_view is None:
            return

        dx = int("right" in self._pressed) - int("left" in self._pressed)
        dy = int("up" in self._pressed) - int("down" in self._pressed)
        self.owner_view.requestMove(dx, dy)

    def _toggle_lab_interest(self):
        if self.owner_view is None or self.district is None:
            return
        if self._lab_interest is None:
            self._lab_interest = self.repo.addInterest(
                self.district.doId, [LAB_ZONE], "demo lab zone"
            )
            print("Opened interest in zone 2: the saved yellow beacon should appear.")
        else:
            self.repo.removeInterest(self._lab_interest)
            self._lab_interest = None
            print("Closed interest in zone 2: the saved yellow beacon should disappear.")

    def _on_eject(self, error_code, reason):
        self.notify.error(f"Astron ejected the client ({error_code}): {reason}")

    def _on_lost_connection(self, *args):
        self.notify.error("Connection to Astron was lost")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Guest", help="name shown for this client")
    args = parser.parse_args()
    DemoClient(args.name).run()


if __name__ == "__main__":
    main()
