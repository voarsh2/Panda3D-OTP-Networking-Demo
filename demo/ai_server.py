import argparse

from panda3d.core import loadPrcFileData

# Apply before importing ShowBase so the AI runs headless.
loadPrcFileData("", "window-type none")

from direct.showbase.ShowBase import ShowBase

from demo.constants import (
    AI_CHANNEL,
    CARTESIAN_GRID_DC_FILE,
    DATABASE_CHANNEL,
    DC_FILE,
    DISTRICT_ID,
    GAME_ROOT_ID,
    LAB_ZONE,
    MAIN_ZONE,
    MANAGEMENT_ZONE,
    MESSAGE_DIRECTOR_HOST,
    MESSAGE_DIRECTOR_PORT,
    PERSISTENT_BEACON_ID_FILE,
    STATE_SERVER_CHANNEL,
)
from demo.networking.internal_repository import AstronInternalRepository
from demo.networking.msgtypes import CLIENTAGENT_DONE_INTEREST_RESP
from demo.persistence import ensure_persistent_beacon
from demo.startup import write_ready_marker


class DemoAIRepository(AstronInternalRepository):
    def handleDatagram(self, di):
        if self.getMsgType() == CLIENTAGENT_DONE_INTEREST_RESP:
            self.handle_client_agent_interest_done_resp(di)
            return
        super().handleDatagram(di)


class DemoAIServer(ShowBase):
    def __init__(self, cartesian_grid=False, ai_grid_interest=False):
        super().__init__()
        from demo import objects

        self.objects = objects
        self.cartesian_grid = cartesian_grid
        self.ai_grid_interest = ai_grid_interest

        self.air = DemoAIRepository(
            AI_CHANNEL,
            serverId=STATE_SERVER_CHANNEL,
            dcFileNames=[DC_FILE]
            + ([CARTESIAN_GRID_DC_FILE] if cartesian_grid else []),
            dcSuffix="AI",
        )
        self.air.worldGridManager = None
        self.air.GameGlobalsId = GAME_ROOT_ID
        self.air.districtId = DISTRICT_ID
        self.air.dbId = DATABASE_CHANNEL
        self.accept("airConnected", self._on_connected)
        self.air.connect(MESSAGE_DIRECTOR_HOST, MESSAGE_DIRECTOR_PORT)

    def _on_connected(self):
        self.district = self.objects.DemoDistrictAI(self.air)
        self.district.generateWithRequiredAndId(
            DISTRICT_ID, GAME_ROOT_ID, MANAGEMENT_ZONE
        )
        self.air.setAI(DISTRICT_ID, self.air.ourChannel)
        if self.cartesian_grid:
            from demo.cartesian_grid import create_cartesian_grid

            self.grid = create_cartesian_grid(
                self.air, self.district.doId, MAIN_ZONE
            )
            self.district.cartesian_grid = self.grid
            if self.ai_grid_interest:
                from demo.cartesian_grid import DemoWorldGridManagerAI

                self.air.worldGridManager = DemoWorldGridManagerAI(self.air)
                print("AI-managed Cartesian grid interest is enabled.", flush=True)
        ensure_persistent_beacon(
            self.air,
            PERSISTENT_BEACON_ID_FILE,
            DISTRICT_ID,
            LAB_ZONE,
        )
        print(
            f"AI ready; District {DISTRICT_ID} is under GameGlobals {GAME_ROOT_ID}.",
            flush=True,
        )
        write_ready_marker("PANDA_DEMO_AI_READY_FILE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cartesian-grid",
        action="store_true",
        help="also run the optional Cartesian grid example",
    )
    parser.add_argument(
        "--ai-grid-interest",
        action="store_true",
        help="manage each avatar's grid interest from the AI server",
    )
    args = parser.parse_args()
    if args.ai_grid_interest and not args.cartesian_grid:
        parser.error("--ai-grid-interest requires --cartesian-grid")
    DemoAIServer(
        cartesian_grid=args.cartesian_grid,
        ai_grid_interest=args.ai_grid_interest,
    ).run()


if __name__ == "__main__":
    main()
