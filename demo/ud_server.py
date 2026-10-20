from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-type none")

from direct.showbase.ShowBase import ShowBase
from panda3d_astron.repository import AstronInternalRepository
from panda3d_astron.msgtypes import CLIENTAGENT_DONE_INTEREST_RESP

from demo.constants import (
    DC_FILE,
    DISTRICT_ID,
    GAME_ROOT_ID,
    LOGIN_MANAGER_ID,
    MESSAGE_DIRECTOR_HOST,
    MESSAGE_DIRECTOR_PORT,
    STATE_SERVER_CHANNEL,
    UD_CHANNEL,
)
from demo.startup import write_ready_marker


class DemoUDRepository(AstronInternalRepository):
    def handleDatagram(self, di):
        if self.getMsgType() == CLIENTAGENT_DONE_INTEREST_RESP:
            self.handle_client_agent_interest_done_resp(di)
            return
        super().handleDatagram(di)


class DemoUDServer(ShowBase):
    def __init__(self):
        super().__init__()
        from demo import objects

        self.objects = objects

        self.air = DemoUDRepository(
            UD_CHANNEL,
            serverId=STATE_SERVER_CHANNEL,
            dcFileNames=[DC_FILE],
            dcSuffix="UD",
        )
        self.air.GameGlobalsId = GAME_ROOT_ID
        self.accept("airConnected", self._on_connected)
        self.air.connect(MESSAGE_DIRECTOR_HOST, MESSAGE_DIRECTOR_PORT)

    def _on_connected(self):
        self.root = self.objects.DemoGameRootUD(self.air)
        self.root.generateWithRequiredAndId(GAME_ROOT_ID, 0, 0)

        # UD needs only a DC-aware proxy to route createAvatar to the AI district.
        self.district = self.objects.DemoDistrictUD(self.air)
        self.district.doId = DISTRICT_ID

        self.login_manager = self.air.generateGlobalObject(
            LOGIN_MANAGER_ID, "DemoLoginManager"
        )
        self.login_manager.set_district(self.district)
        print(f"UberDOG ready; GameGlobals root is {GAME_ROOT_ID}.", flush=True)
        write_ready_marker("PANDA_DEMO_UD_READY_FILE")


DemoUDServer().run()
