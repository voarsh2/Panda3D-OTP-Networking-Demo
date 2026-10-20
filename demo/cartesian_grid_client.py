import argparse

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.MessengerGlobal import messenger
from direct.showbase import ShowBaseGlobal
from panda3d.core import LineSegs, TextNode, TransparencyAttrib, loadPrcFileData

from demo.cartesian_grid import grid_interest_window
from demo.client import DemoClient
from demo.constants import CARTESIAN_GRID_DC_FILE

GRID_LABEL_HEIGHT = 1.8
GRID_LABEL_Y_OFFSET = 1.0


def interest_cell_edges(grid, zones):
    edges = set()
    width = float(grid.cellWidth)
    for zone in zones:
        x, y, _ = grid.getZoneCellOrigin(zone)
        corners = ((x, y), (x + width, y), (x + width, y + width), (x, y + width))
        for index, start in enumerate(corners):
            edge = tuple(sorted((start, corners[(index + 1) % len(corners)])))
            edges.add(edge)
    return tuple(sorted(edges))


class DemoCartesianGridClient(DemoClient):
    def __init__(self, name, show_grid=False, server_grid_interest=False):
        self.grid = None
        self.show_grid = show_grid
        self.server_grid_interest = server_grid_interest
        self._grid_interest = None
        self._grid_zones = ()
        self._interest_zones = ()
        self._interest_outline = None
        self._grid_center = None
        self._owner_position = None
        self._interest_radius = None
        self._probe_do_id = None
        self._probe_zone = None
        self._probe_status = "WAITING"
        self._hud_text = None
        super().__init__(name, extra_dc_file_names=[CARTESIAN_GRID_DC_FILE])
        self.help.setText(
            "Arrow keys: move observer across grid cells\n"
            "Tab: toggle whole District zone 2 interest (lab beacon)"
        )
        self.grid_hud = OnscreenText(
            text="",
            parent=ShowBaseGlobal.base.a2dTopLeft,
            pos=(0.08, -0.15),
            scale=0.04,
            fg=(1, 1, 1, 1),
            bg=(0, 0, 0, 0.65),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.accept("demo-cartesian-grid-generated", self._set_grid)
        self.accept("demo-owner-avatar-position", self._set_owner_position)
        self.accept("demo-grid-probe-generated", self._inspect_probe)
        self.accept("demo-grid-probe-location-changed", self._inspect_probe_move)
        self.accept("demo-grid-probe-left-view", self._inspect_probe_leave)
        self.accept(
            "demo-server-interest-state-changed",
            self._on_server_interest_state_changed,
        )

    def _set_owner_view(self, owner_view):
        super()._set_owner_view(owner_view)
        self._set_owner_position(*owner_view.last_position)

    def _set_grid(self, grid):
        self.grid = grid
        print(
            f"DO DemoCartesianGrid id={grid.doId} parent={grid.parentId} "
            f"zone={grid.zoneId} start={grid.startingZone} size={grid.gridSize} "
            f"radius={grid.viewingRadius} cellWidth={grid.cellWidth}",
            flush=True,
        )
        if self.server_grid_interest:
            print("Grid interest is managed by the AI server.", flush=True)
        if self.show_grid:
            grid.visualizeGrid()
            # Panda's default z=3 labels project into the previous row at this camera angle.
            for label in grid.cellLabelParent.getChildren():
                label.setZ(GRID_LABEL_HEIGHT)
                label.setY(label.getY() + GRID_LABEL_Y_OFFSET)
        if self._owner_position is not None:
            self._update_grid_interest()
        else:
            self._update_hud()

    def _set_owner_position(self, x, y):
        self._owner_position = (float(x), float(y))
        self._update_grid_interest()

    def _toggle_lab_interest(self):
        super()._toggle_lab_interest()
        self._update_hud()

    def _on_server_interest_state_changed(self, *_args):
        self._update_hud()

    def _update_grid_interest(self):
        if self.grid is None:
            self._update_hud()
            return
        self._interest_radius = int(self.grid.viewingRadius)
        if self._owner_position is None:
            self._update_hud()
            return

        center, zones = grid_interest_window(
            self.grid, (*self._owner_position, 0.0)
        )
        previous_center = self._grid_center
        previous_zones = self._interest_zones
        self._grid_center = center
        self._interest_zones = zones
        if zones != previous_zones:
            self._draw_interest_cells(zones)
        if center != previous_center or zones != previous_zones or self._hud_text is None:
            self._update_hud()
        if self.server_grid_interest:
            return

        if not zones:
            if self._grid_interest is not None:
                self.repo.removeInterest(self._grid_interest)
                self._grid_interest = None
                self._grid_zones = ()
                print("Grid interest closed: owner is outside the grid.", flush=True)
            return
        if zones == self._grid_zones:
            return
        if self._grid_interest is None:
            self._grid_interest = self.repo.addInterest(
                self.grid.doId, list(zones), "Cartesian grid view"
            )
        else:
            self.repo.alterInterest(
                self._grid_interest,
                self.grid.doId,
                list(zones),
                "Cartesian grid view",
            )
        self._grid_zones = zones
        print(f"Grid interest center={center} zones={list(zones)}", flush=True)

    def _draw_interest_cells(self, zones):
        outline = self._interest_outline
        if outline is not None:
            outline.removeNode()
            self._interest_outline = None
        if not self.show_grid or self.grid is None or not zones:
            return

        lines = LineSegs("grid-interest-window")
        lines.setColor(0.2, 0.75, 0.9, 0.48)
        lines.setThickness(2)
        for edge in interest_cell_edges(self.grid, zones):
            start, end = edge
            lines.moveTo(start[0], start[1], 0.02)
            lines.drawTo(end[0], end[1], 0.02)
        self._interest_outline = self.grid.attachNewNode(lines.create())
        self._interest_outline.setTransparency(TransparencyAttrib.MAlpha)
        self._interest_outline.setDepthWrite(False)

    def _update_hud(self):
        grid_id = self.grid.doId if self.grid is not None else "—"
        if self._owner_position is None:
            observer_cell = "WAITING"
        elif self._grid_center is None:
            observer_cell = "OUTSIDE GRID"
        else:
            observer_cell = self._grid_center

        source = (
            "AI-managed"
            if self.server_grid_interest
            else "client-local"
        )
        if source == "AI-managed":
            expected = len(self._interest_zones)
            states = (
                self.repo.getServerInterestStates(self.grid.doId)
                if self.grid is not None
                else ()
            )
            active = [state for _, _, state in states if state != "removing"]
            complete = sum(state == "complete" for state in active)
            if not expected:
                snapshot = "outside grid"
            elif complete == expected:
                snapshot = f"READY {complete}/{expected}"
            else:
                snapshot = f"WAITING {complete}/{expected}"
        else:
            snapshot = "client-local"
        legend = (
            "Cyan outlines: grid interest cells\n"
            if self.show_grid
            else ""
        )
        hud_text = (
            f"Cartesian Grid {grid_id}\n"
            f"Interest source: {source} ({snapshot})\n"
            f"Observer cell: {observer_cell}\n"
            f"Interest radius: {self._interest_radius if self._interest_radius is not None else '—'}\n"
            f"{legend}"
            f"District zone 2 (Tab): {'OPEN' if self._lab_interest is not None else 'CLOSED'}\n"
            f"Probe:\n"
            f"  doId: {self._probe_do_id or '—'}\n"
            f"  Zone: {self._probe_zone or '—'}\n"
            f"  State: {self._probe_status}"
        )
        if hud_text != self._hud_text:
            self._hud_text = hud_text
            self.grid_hud.setText(hud_text)

    def _probe_state(self, probe):
        return (
            f"id={probe.doId} parent={probe.parentId} zone={probe.zoneId} "
            f"inRepository={self.repo.doId2do.get(probe.doId) is probe} "
            f"generated={probe.isGenerated()} "
            f"serverInterestStates={self.repo.getServerInterestStates(probe.parentId)}"
        )

    def _inspect_probe(self, probe):
        self._probe_do_id = probe.doId
        self._probe_zone = probe.zoneId
        present = self.repo.doId2do.get(probe.doId) is probe
        generated = probe.isGenerated()
        self._probe_status = "GENERATED" if present and generated else "OUT OF INTEREST"
        self._update_hud()
        print(
            f"DO DemoGridProbe entered view: id={probe.doId} "
            f"parent={probe.parentId} zone={probe.zoneId} "
            f"inRepository={present} "
            f"serverInterestStates={self.repo.getServerInterestStates(probe.parentId)}",
            flush=True,
        )

    def _inspect_probe_move(self, probe, old_parent, old_zone):
        self._probe_do_id = probe.doId
        self._probe_zone = probe.zoneId
        self._probe_status = (
            "GENERATED"
            if self.repo.doId2do.get(probe.doId) is probe and probe.isGenerated()
            else "OUT OF INTEREST"
        )
        self._update_hud()
        print(
            f"DO DemoGridProbe moved: id={probe.doId} "
            f"({old_parent}, {old_zone}) -> ({probe.parentId}, {probe.zoneId}) "
            f"inRepository={self.repo.doId2do.get(probe.doId) is probe} "
            f"generated={probe.isGenerated()} "
            f"serverInterestStates={self.repo.getServerInterestStates(probe.parentId)}",
            flush=True,
        )

    def _inspect_probe_leave(self, probe):
        self._probe_do_id = probe.doId
        self._probe_zone = probe.zoneId
        self._probe_status = "OUT OF INTEREST"
        self._update_hud()
        print(f"DO DemoGridProbe left view: {self._probe_state(probe)}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Connect with the optional Cartesian grid example."
    )
    parser.add_argument("--name", default="Guest", help="name shown for this client")
    parser.add_argument("--show-grid", action="store_true")
    parser.add_argument(
        "--server-grid-interest",
        action="store_true",
        help="use AI-managed interest instead of client-local grid interest",
    )
    parser.add_argument("--offscreen", action="store_true")
    args = parser.parse_args()
    if args.offscreen:
        loadPrcFileData("", "window-type offscreen")
    DemoCartesianGridClient(
        args.name,
        show_grid=args.show_grid,
        server_grid_interest=args.server_grid_interest,
    ).run()


if __name__ == "__main__":
    main()
