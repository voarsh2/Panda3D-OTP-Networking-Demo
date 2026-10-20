from pathlib import Path


def ensure_persistent_beacon(air, id_file, parent_id, zone_id):
    """Load or create the demo's one database-backed beacon, then activate it."""
    id_file = Path(id_file)
    # Internal repositories key DC classes by the active view suffix (AI here).
    dclass = air.dclassesByName["DemoBeaconAI"]

    try:
        do_id = int(id_file.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        _create_beacon(air, id_file, dclass, parent_id, zone_id)
        return
    except ValueError:
        print(f"Invalid beacon ID file at {id_file}; creating a new beacon.", flush=True)
        _create_beacon(air, id_file, dclass, parent_id, zone_id)
        return

    def on_query_result(found_dclass, fields):
        if not found_dclass or not fields:
            print(f"Saved beacon {do_id} was not found; creating a replacement.", flush=True)
            _create_beacon(air, id_file, dclass, parent_id, zone_id)
            return
        _activate_beacon(air, do_id, parent_id, zone_id)

    air.dbInterface.queryObject(
        air.dbId,
        do_id,
        on_query_result,
        dclass=dclass,
    )


def _create_beacon(air, id_file, dclass, parent_id, zone_id):
    def on_created(do_id):
        if not do_id:
            print("Astron could not create the persistent beacon.", flush=True)
            return

        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(f"{int(do_id)}\n", encoding="utf-8")
        print(f"Created persistent beacon {do_id} in Astron's database.", flush=True)
        _activate_beacon(air, int(do_id), parent_id, zone_id)

    air.dbInterface.createObject(
        air.dbId,
        dclass,
        {"setActivationCount": (0,)},
        on_created,
    )


def _activate_beacon(air, do_id, parent_id, zone_id):
    air.sendActivate(do_id, parent_id, zone_id)
    air.setAI(do_id, air.ourChannel)
    print(f"Activated saved beacon {do_id} in zone {zone_id}.", flush=True)
