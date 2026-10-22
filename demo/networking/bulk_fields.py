"""Route Astron bulk field messages through Direct's normal update handler."""

from direct.distributed.ClientRepositoryBase import ClientRepositoryBase
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.PyDatagramIterator import PyDatagramIterator
from panda3d.direct import DCPacker


def handle_bulk_field_updates(repository, di):
    do_id = di.get_uint32()
    field_count = di.get_uint16()
    owner_view = repository.doId2ownerView.get(do_id)
    dist_obj = repository.doId2do.get(do_id)
    dclass = owner_view.dclass if owner_view is not None else None
    if dclass is None and dist_obj is not None:
        dclass = dist_obj.dclass
    if dclass is None:
        deferred = repository.deferredDoIds.get(do_id)
        if deferred is not None:
            deferred_args = deferred[0]
            dclass = repository.dclassesByNumber[deferred_args[2]]

    if dclass is None:
        repository.notify.warning(
            f"Asked to bulk-update non-existent DistObj {do_id}"
        )
        return

    payload = bytes(di.get_remaining_bytes())
    unpacker = DCPacker()
    unpacker.setUnpackData(payload)

    # Astron preserves the DC-packed field sequence. Dispatch each field in
    # that wire order through Direct so Owner Views, deferred updates, DC
    # receive hooks, and normal object updates keep the single-field behavior.
    for _ in range(field_count):
        field_id = unpacker.rawUnpackUint16()
        field = dclass.getFieldByIndex(field_id)
        if field is None:
            raise ValueError(
                f"Unknown field {field_id} in {dclass.getName()} bulk update"
            )

        field_start = unpacker.getNumUnpackedBytes()
        unpacker.beginUnpack(field)
        field.unpackArgs(unpacker)
        unpacker.endUnpack()
        field_end = unpacker.getNumUnpackedBytes()

        update = PyDatagram()
        update.addUint32(do_id)
        update.addUint16(field_id)
        update.appendData(payload[field_start:field_end])
        ClientRepositoryBase.handleUpdateField(
            repository, PyDatagramIterator(update)
        )
