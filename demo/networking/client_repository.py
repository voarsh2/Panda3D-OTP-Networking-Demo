"""ClientAgent protocol adapter for Direct's ClientRepositoryBase."""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed import DoInterestManager
from direct.distributed.ClientRepositoryBase import ClientRepositoryBase
from direct.distributed.PyDatagram import PyDatagram
from direct.showbase.MessengerGlobal import messenger
from panda3d.core import ConfigVariableString

from .bulk_fields import handle_bulk_field_updates
from .msgtypes import (
    CLIENT_ADD_INTEREST,
    CLIENT_ADD_INTEREST_MULTIPLE,
    CLIENT_DONE_INTEREST_RESP,
    CLIENT_EJECT,
    CLIENT_ENTER_OBJECT_REQUIRED,
    CLIENT_ENTER_OBJECT_REQUIRED_OTHER,
    CLIENT_ENTER_OBJECT_REQUIRED_OTHER_OWNER,
    CLIENT_ENTER_OBJECT_REQUIRED_OWNER,
    CLIENT_HEARTBEAT,
    CLIENT_HELLO,
    CLIENT_HELLO_RESP,
    CLIENT_OBJECT_LEAVING,
    CLIENT_OBJECT_LOCATION,
    CLIENT_OBJECT_SET_FIELD,
    CLIENT_OBJECT_SET_FIELDS,
    CLIENT_REMOVE_INTEREST,
)


class AstronClientRepository(ClientRepositoryBase):
    """Panda Direct client repository with Astron ClientAgent framing."""

    notify = DirectNotifyGlobal.directNotify.newCategory(
        "DemoAstronClientRepository"
    )
    GameGlobalsId = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base.finalExitCallbacks.append(self.shutdown)
        self.message_handlers = {
            CLIENT_HELLO_RESP: self.handle_hello_resp,
            CLIENT_EJECT: self.handle_eject,
            CLIENT_ENTER_OBJECT_REQUIRED: self.handle_enter_object_required,
            CLIENT_ENTER_OBJECT_REQUIRED_OTHER: self.handle_enter_object_required_other,
            CLIENT_ENTER_OBJECT_REQUIRED_OWNER: self.handle_enter_object_required_owner,
            CLIENT_ENTER_OBJECT_REQUIRED_OTHER_OWNER: self.handle_enter_object_required_other_owner,
            CLIENT_OBJECT_SET_FIELD: self.handle_update_field,
            CLIENT_OBJECT_SET_FIELDS: self.handle_update_fields,
            CLIENT_OBJECT_LEAVING: self.handle_object_leaving,
            CLIENT_OBJECT_LOCATION: self.handleObjectLocation,
            CLIENT_ADD_INTEREST: self.handle_add_interest,
            CLIENT_ADD_INTEREST_MULTIPLE: self.handle_add_interest_multiple,
            CLIENT_REMOVE_INTEREST: self.handle_remove_interest,
            CLIENT_DONE_INTEREST_RESP: self.handle_interest_done_message,
        }

    def handleDatagram(self, di):
        msg_type = self.getMsgType()
        handler = self.message_handlers.get(msg_type)
        if handler is None:
            self.notify.error(f"Received unknown message type: {msg_type}!")
            return
        handler(di)
        self.consider_heartbeat()

    handle_datagram = handleDatagram

    def consider_heartbeat(self):
        super().considerHeartbeat()

    def handle_hello_resp(self, _di):
        messenger.send("CLIENT_HELLO_RESP", [])

    def handle_eject(self, di):
        messenger.send("CLIENT_EJECT", [di.get_uint16(), di.get_string()])

    def handle_update_field(self, di):
        super().handleUpdateField(di)

    def handle_update_fields(self, di):
        handle_bulk_field_updates(self, di)

    def handle_enter_object_required(self, di):
        do_id = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        self.generateWithRequiredFields(
            self.dclassesByNumber[dclass_id], do_id, di, parent_id, zone_id
        )

    def handle_enter_object_required_other(self, di):
        do_id = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        self.generateWithRequiredOtherFields(
            self.dclassesByNumber[dclass_id], do_id, di, parent_id, zone_id
        )

    def handle_enter_object_required_owner(self, di):
        do_id = di.get_uint32()
        # Owner Views are keyed separately from doId2do; the required-owner
        # packet carries location fields, but Direct does not location-generate
        # this owner-only perspective.
        di.get_uint32()  # parent id is present in the protocol header
        di.get_uint32()  # zone id is present in the protocol header
        dclass_id = di.get_uint16()
        self.generateWithRequiredFieldsOwner(
            self.dclassesByNumber[dclass_id], do_id, di
        )

    def generateWithRequiredFieldsOwner(self, dclass, do_id, di):
        # Panda 1.10's ClientRepositoryBase has the required-other Owner View
        # path; this required-fields variant is part of the Astron protocol.
        if do_id in self.doId2ownerView:
            self.notify.error(
                "duplicate owner generate for %s (%s)"
                % (do_id, dclass.getName())
            )
            dist_obj = self.doId2ownerView[do_id]
            assert dist_obj.dclass == dclass
            dist_obj.generate()
            dist_obj.updateRequiredFields(dclass, di)
        elif self.cacheOwner.contains(do_id):
            dist_obj = self.cacheOwner.retrieve(do_id)
            assert dist_obj.dclass == dclass
            self.doId2ownerView[do_id] = dist_obj
            dist_obj.generate()
            dist_obj.updateRequiredFields(dclass, di)
        else:
            class_def = dclass.getOwnerClassDef()
            if class_def is None:
                self.notify.error(
                    "Could not create an undefined %s object. "
                    "Have you created an owner view?" % dclass.getName()
                )
            dist_obj = class_def(self)
            dist_obj.dclass = dclass
            dist_obj.doId = do_id
            self.doId2ownerView[do_id] = dist_obj
            dist_obj.generateInit()
            dist_obj.generate()
            dist_obj.updateRequiredFields(dclass, di)
        return dist_obj

    generate_with_required_fields_owner = generateWithRequiredFieldsOwner

    def handle_enter_object_required_other_owner(self, di):
        do_id = di.get_uint32()
        di.get_uint32()  # parent id is present in the protocol header
        di.get_uint32()  # zone id is present in the protocol header
        dclass_id = di.get_uint16()
        self.generateWithRequiredOtherFieldsOwner(
            self.dclassesByNumber[dclass_id], do_id, di
        )

    def handle_object_leaving(self, di):
        do_id = di.get_uint32()
        # Let deleteObject call Direct's deleteOrDelay in the correct order.
        self.deleteObject(do_id)
        messenger.send("CLIENT_OBJECT_LEAVING", [do_id])

    def deleteObject(self, do_id):
        """Remove a visible DO through Direct's deleteOrDelay lifecycle."""
        if do_id in self.doId2do:
            dist_obj = self.doId2do[do_id]
            del self.doId2do[do_id]
            dist_obj.deleteOrDelay()
            if self.isLocalId(do_id):
                self.freeDoId(do_id)
        elif self.cache.contains(do_id):
            self.cache.delete(do_id)
            if self.isLocalId(do_id):
                self.freeDoId(do_id)
        else:
            self.notify.warning(f"Asked to delete non-existent DistObj {do_id}")

    delete_object = deleteObject

    def handle_add_interest(self, di):
        context = di.get_uint32()
        interest_id = di.get_uint16()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        messenger.send(
            "CLIENT_ADD_INTEREST", [context, interest_id, parent_id, zone_id]
        )
        self.add_internal_interest_handle(
            context, interest_id, parent_id, [zone_id]
        )

    def handle_add_interest_multiple(self, di):
        context = di.get_uint32()
        interest_id = di.get_uint16()
        parent_id = di.get_uint32()
        zone_ids = [di.get_uint32() for _ in range(di.get_uint16())]
        messenger.send(
            "CLIENT_ADD_INTEREST_MULTIPLE",
            [context, interest_id, parent_id, zone_ids],
        )
        self.add_internal_interest_handle(
            context, interest_id, parent_id, zone_ids
        )

    def add_internal_interest_handle(
        self, context, interest_id, parent_id, zone_ids
    ):
        if parent_id != self.getGameDoId():
            parent = self.getDo(parent_id)
            if parent is None:
                self.notify.error(
                    f"Attempting to add interest under unknown object {parent_id}"
                )
            if not parent.hasParentingRules():
                self.notify.error(
                    "No setParentingRules defined in the DC for object "
                    f"{parent_id} ({type(parent).__name__})"
                )

        DoInterestManager.DoInterestManager._interests[interest_id] = (
            DoInterestManager.InterestState(
                None,
                DoInterestManager.InterestState.StateActive,
                context,
                None,
                parent_id,
                zone_ids,
                self._completeEventCount,
                True,
            )
        )

    def handle_interest_done_message(self, di):
        DoInterestManager.DoInterestManager.handleInterestDoneMessage(self, di)

    def handle_remove_interest(self, di):
        context = di.get_uint32()
        interest_id = di.get_uint16()
        messenger.send("CLIENT_REMOVE_INTEREST", [context, interest_id])

    def handleObjectLocation(self, di):
        do_id = di.getUint32()
        parent_id = di.getUint32()
        zone_id = di.getUint32()
        dist_obj = self.doId2do.get(do_id)
        if dist_obj is not None:
            dist_obj.setLocation(parent_id, zone_id)
            return
        self.notify.warning(
            f"handleObjectLocation: Asked to update non-existent obj: {do_id}"
        )

    def sendUpdate(self, dist_obj, field_name, args):
        datagram = dist_obj.dclass.clientFormatUpdate(
            field_name, dist_obj.doId, args
        )
        self.send(datagram)

    send_update = sendUpdate

    def sendHello(self, version_string=None):
        if version_string is None:
            version_string = ConfigVariableString("server-version", "")
        if version_string is None or version_string == "":
            self.notify.error(
                'No server version defined; set the "server-version" PRC value'
            )
            return
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_HELLO)
        datagram.addUint32(self.get_dc_file().get_hash())
        datagram.addString(str(version_string))
        self.send(datagram)

    send_hello = sendHello

    def sendHeartbeat(self):
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_HEARTBEAT)
        self.send(datagram)

    send_heartbeat = sendHeartbeat

    def sendAddInterest(self, context, interest_id, parent_id, zone_id):
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_ADD_INTEREST)
        datagram.addUint32(context)
        datagram.addUint16(interest_id)
        datagram.addUint32(parent_id)
        datagram.addUint32(zone_id)
        self.send(datagram)

    send_add_interest = sendAddInterest

    def sendAddInterestMultiple(self, context, interest_id, parent_id, zone_ids):
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_ADD_INTEREST_MULTIPLE)
        datagram.addUint32(context)
        datagram.addUint16(interest_id)
        datagram.addUint32(parent_id)
        datagram.addUint16(len(zone_ids))
        for zone_id in zone_ids:
            datagram.addUint32(zone_id)
        self.send(datagram)

    send_add_interest_multiple = sendAddInterestMultiple

    def sendRemoveInterest(self, context, interest_id):
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_REMOVE_INTEREST)
        datagram.addUint32(context)
        datagram.addUint16(interest_id)
        self.send(datagram)

    send_remove_interest = sendRemoveInterest

    def lostConnection(self):
        messenger.send("LOST_CONNECTION")

    def disconnect(self):
        for do_id in list(self.doId2do):
            self.deleteObject(do_id)
        ClientRepositoryBase.disconnect(self)
