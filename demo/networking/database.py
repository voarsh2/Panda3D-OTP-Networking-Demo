"""Database Server create/query messages used by the persistent beacon."""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram
from panda3d.direct import DCPacker

from .msgtypes import (
    DBSERVER_CREATE_OBJECT,
    DBSERVER_CREATE_OBJECT_RESP,
    DBSERVER_OBJECT_GET_ALL,
    DBSERVER_OBJECT_GET_ALL_RESP,
    MsgId2Names,
)


class AstronDatabaseInterface:
    """Small create and full-object query interface for Astron's Database."""

    notify = DirectNotifyGlobal.directNotify.newCategory(
        "DemoAstronDatabaseInterface"
    )

    def __init__(self, air):
        self.air = air
        self._callbacks = {}

    def createObject(self, database_id, dclass, fields=None, callback=None):
        """Create a persistent object; callback receives its allocated DO ID."""
        context = self.air.getContext()
        self._callbacks[context] = callback
        field_packer = DCPacker()
        field_count = 0
        for field_name, args in (fields or {}).items():
            field = dclass.getFieldByName(field_name)
            if field is None:
                self.notify.error(
                    f"Creation request for {dclass.getName()} has no field "
                    f"named {field_name}"
                )
            field_packer.rawPackUint16(field.getNumber())
            field_packer.beginPack(field)
            field.packArgs(field_packer, args)
            field_packer.endPack()
            field_count += 1

        datagram = PyDatagram()
        datagram.addServerHeader(
            database_id, self.air.ourChannel, DBSERVER_CREATE_OBJECT
        )
        datagram.addUint32(context)
        datagram.addUint16(dclass.getNumber())
        datagram.addUint16(field_count)
        datagram.appendData(bytes(field_packer.getBytes()))
        self.air.send(datagram)

    def queryObject(self, database_id, do_id, callback):
        """Query all fields.

        The callback receives ``(dclass, fields)`` or ``(None, None)``.
        """
        context = self.air.getContext()
        self._callbacks[context] = callback

        datagram = PyDatagram()
        datagram.addServerHeader(
            database_id, self.air.ourChannel, DBSERVER_OBJECT_GET_ALL
        )
        datagram.addUint32(context)
        datagram.addUint32(do_id)
        self.air.send(datagram)

    def handleDatagram(self, message_type, di):
        if message_type == DBSERVER_CREATE_OBJECT_RESP:
            self.handleCreateObjectResp(di)
        elif message_type == DBSERVER_OBJECT_GET_ALL_RESP:
            self.handleQueryObjectResp(message_type, di)

    handle_datagram = handleDatagram

    def handleCreateObjectResp(self, di):
        context = di.getUint32()
        do_id = di.getUint32()
        if context not in self._callbacks:
            self.notify.warning(
                "Received unexpected DBSERVER_CREATE_OBJECT_RESP "
                f"(ctx {context}, doId {do_id})"
            )
            return
        callback = self._callbacks[context]
        try:
            if callback is not None:
                callback(do_id)
        finally:
            del self._callbacks[context]

    def handleQueryObjectResp(self, message_type, di):
        context = di.getUint32()
        success = di.getUint8()
        if context not in self._callbacks:
            name = MsgId2Names.get(message_type, [str(message_type)])[0]
            self.notify.warning(
                f"Received unexpected {name} (ctx {context})"
            )
            return

        callback = self._callbacks[context]
        try:
            if not success:
                if callback is not None:
                    callback(None, None)
                return

            dclass_id = di.getUint16()
            dclass = self.air.dclassesByNumber.get(dclass_id)
            if dclass is None:
                self.notify.error(
                    f"Received unknown dclass {dclass_id} in database query"
                )
            field_count = di.getUint16()
            unpacker = DCPacker()
            unpacker.setUnpackData(di.getRemainingBytes())
            fields = {}
            for _ in range(field_count):
                field_id = unpacker.rawUnpackInt16()
                field = dclass.getFieldByIndex(field_id)
                if field is None:
                    self.notify.error(
                        f"Received unknown field {field_id} in "
                        f"{dclass.getName()} database query"
                    )
                unpacker.beginUnpack(field)
                fields[field.getName()] = field.unpackArgs(unpacker)
                unpacker.endUnpack()
            if callback is not None:
                callback(dclass, fields)
        finally:
            del self._callbacks[context]

    handle_create_object_resp = handleCreateObjectResp
    handle_query_object_resp = handleQueryObjectResp
