"""Astron Message Director connection used by the demo's AI and UberDOG."""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.ConnectionRepository import ConnectionRepository
from direct.distributed.PyDatagram import PyDatagram
from direct.showbase.MessengerGlobal import messenger
from direct.showbase.ShowBaseGlobal import config
from direct.task.TaskManagerGlobal import taskMgr
from panda3d.core import URLSpec, UniqueIdAllocator

from .database import AstronDatabaseInterface
from .msgtypes import (
    CLIENTAGENT_ADD_INTEREST,
    CLIENTAGENT_ADD_INTEREST_MULTIPLE,
    CLIENTAGENT_ADD_SESSION_OBJECT,
    CLIENTAGENT_DONE_INTEREST_RESP,
    CLIENTAGENT_REMOVE_INTEREST,
    CLIENTAGENT_SET_STATE,
    CONTROL_ADD_CHANNEL,
    CONTROL_ADD_POST_REMOVE,
    CONTROL_CLEAR_POST_REMOVES,
    CONTROL_REMOVE_CHANNEL,
    DBSS_OBJECT_ACTIVATE_WITH_DEFAULTS,
    DBSERVER_CREATE_OBJECT_RESP,
    DBSERVER_OBJECT_GET_ALL_RESP,
    STATESERVER_DELETE_AI_OBJECTS,
    STATESERVER_OBJECT_CHANGING_AI,
    STATESERVER_OBJECT_CHANGING_LOCATION,
    STATESERVER_OBJECT_DELETE_RAM,
    STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED,
    STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER,
    STATESERVER_OBJECT_GET_LOCATION,
    STATESERVER_OBJECT_GET_LOCATION_RESP,
    STATESERVER_OBJECT_SET_AI,
    STATESERVER_OBJECT_SET_LOCATION,
    STATESERVER_OBJECT_SET_OWNER,
)


class AstronInternalRepository(ConnectionRepository):
    """The small internal Astron protocol surface used by this demo."""

    notify = DirectNotifyGlobal.directNotify.newCategory(
        "DemoAstronInternalRepository"
    )

    def __init__(
        self,
        base_channel,
        serverId=None,
        dcFileNames=None,
        dcSuffix="AI",
        connectMethod=None,
        threadedNet=None,
    ):
        if connectMethod is None:
            connectMethod = self.CM_NATIVE
        super().__init__(
            connectMethod,
            config,
            hasOwnerView=False,
            threadedNet=threadedNet,
        )
        self.setClientDatagram(False)
        self.dcSuffix = dcSuffix
        self.serverId = self.config.GetInt("air-stateserver", 0) or None
        if serverId is not None:
            self.serverId = serverId

        max_channels = self.config.GetInt("air-channel-allocation", 1000000)
        self.channelAllocator = UniqueIdAllocator(
            base_channel, base_channel + max_channels - 1
        )
        self._registeredChannels = set()
        self._context_counter = 0
        self._callbacks = {}
        self.dbInterface = AstronDatabaseInterface(self)
        self.ourChannel = self.allocateChannel()
        self.readDCFile(dcFileNames)

    def getContext(self):
        self._context_counter = (self._context_counter + 1) & 0xFFFFFFFF
        return self._context_counter

    def allocateChannel(self):
        return self.channelAllocator.allocate()

    def deallocateChannel(self, channel):
        self.channelAllocator.free(channel)

    def registerForChannel(self, channel):
        if channel in self._registeredChannels:
            return
        self._registeredChannels.add(channel)
        datagram = PyDatagram()
        datagram.addServerControlHeader(CONTROL_ADD_CHANNEL)
        datagram.addChannel(channel)
        self.send(datagram)

    def unregisterForChannel(self, channel):
        if channel not in self._registeredChannels:
            return
        self._registeredChannels.remove(channel)
        datagram = PyDatagram()
        datagram.addServerControlHeader(CONTROL_REMOVE_CHANNEL)
        datagram.addChannel(channel)
        self.send(datagram)

    def addPostRemove(self, datagram):
        post_remove = PyDatagram()
        post_remove.addServerControlHeader(CONTROL_ADD_POST_REMOVE)
        post_remove.addUint64(self.ourChannel)
        post_remove.addBlob(datagram.getMessage())
        self.send(post_remove)

    def clearPostRemove(self):
        datagram = PyDatagram()
        datagram.addServerControlHeader(CONTROL_CLEAR_POST_REMOVES)
        datagram.addUint64(self.ourChannel)
        self.send(datagram)

    def handleDatagram(self, di):
        message_type = self.getMsgType()
        if message_type in (
            STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED,
            STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER,
        ):
            self.handleObjEntry(
                di,
                message_type == STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER,
            )
        elif message_type in (
            STATESERVER_OBJECT_CHANGING_AI,
            STATESERVER_OBJECT_DELETE_RAM,
        ):
            self.handleObjExit(di)
        elif message_type == STATESERVER_OBJECT_CHANGING_LOCATION:
            self.handleObjLocation(di)
        elif message_type in (
            DBSERVER_CREATE_OBJECT_RESP,
            DBSERVER_OBJECT_GET_ALL_RESP,
        ):
            self.dbInterface.handleDatagram(message_type, di)
        elif message_type == STATESERVER_OBJECT_GET_LOCATION_RESP:
            self.handleGetLocationResp(di)
        elif message_type == CLIENTAGENT_DONE_INTEREST_RESP:
            self.handle_client_agent_interest_done_resp(di)
        else:
            self.notify.warning(f"Received unknown MsgType={message_type}")

    handle_datagram = handleDatagram

    def handleObjLocation(self, di):
        do_id = di.getUint32()
        parent_id = di.getUint32()
        zone_id = di.getUint32()
        dist_obj = self.doId2do.get(do_id)
        if dist_obj is None:
            self.notify.warning(f"Received location for unknown doId={do_id}!")
            return
        dist_obj.setLocation(parent_id, zone_id)

    def handleObjEntry(self, di, other):
        do_id = di.getUint32()
        parent_id = di.getUint32()
        zone_id = di.getUint32()
        dclass_id = di.getUint16()
        dclass = self.dclassesByNumber.get(dclass_id)
        if dclass is None:
            self.notify.warning(
                f"Received entry for unknown dclass={dclass_id}! "
                f"(Object {do_id})"
            )
            return
        if do_id in self.doId2do:
            return

        class_def = dclass.getClassDef()
        if class_def is None:
            self.notify.error(f"Could not create undefined {dclass.getName()}")
        dist_obj = class_def(self)
        dist_obj.dclass = dclass
        dist_obj.doId = do_id
        dist_obj.doNotDeallocateChannel = True
        self.addDOToTables(dist_obj, location=(parent_id, zone_id))
        dist_obj.generate()
        if other:
            dist_obj.updateAllRequiredOtherFields(dclass, di)
        else:
            dist_obj.updateAllRequiredFields(dclass, di)

    def handleObjExit(self, di):
        do_id = di.getUint32()
        if do_id not in self.doId2do:
            self.notify.warning(f"Received AI exit for unknown object {do_id}")
            return
        dist_obj = self.doId2do[do_id]
        self.removeDOFromTables(dist_obj)
        dist_obj.delete()
        dist_obj.sendDeleteEvent()

    def getLocation(self, do_id, callback):
        context = self.getContext()
        self._callbacks[context] = callback
        datagram = PyDatagram()
        datagram.addServerHeader(
            do_id, self.ourChannel, STATESERVER_OBJECT_GET_LOCATION
        )
        datagram.addUint32(context)
        self.send(datagram)

    def handleGetLocationResp(self, di):
        context = di.getUint32()
        do_id = di.getUint32()
        parent_id = di.getUint32()
        zone_id = di.getUint32()
        if context not in self._callbacks:
            self.notify.warning(
                "Received unexpected STATESERVER_OBJECT_GET_LOCATION_RESP "
                f"(ctx: {context})"
            )
            return
        try:
            self._callbacks[context](do_id, parent_id, zone_id)
        finally:
            del self._callbacks[context]

    def sendUpdate(self, dist_obj, field_name, args):
        return self.sendUpdateToChannel(dist_obj, dist_obj.doId, field_name, args)

    def sendUpdateToChannel(self, dist_obj, channel_id, field_name, args):
        field = dist_obj.dclass.getFieldByName(field_name)
        if field is None:
            self.notify.error(
                f"Unknown field {field_name} on {dist_obj.dclass.getName()}"
            )
        self.send(
            field.aiFormatUpdate(
                dist_obj.doId, channel_id, self.ourChannel, args
            )
        )

    def sendActivate(self, do_id, parent_id, zone_id):
        datagram = PyDatagram()
        datagram.addServerHeader(
            do_id, self.ourChannel, DBSS_OBJECT_ACTIVATE_WITH_DEFAULTS
        )
        datagram.addUint32(do_id)
        datagram.addUint32(parent_id)
        datagram.addUint32(zone_id)
        self.send(datagram)

    def sendSetLocation(self, dist_obj, parent_id, zone_id):
        datagram = PyDatagram()
        datagram.addServerHeader(
            dist_obj.doId, self.ourChannel, STATESERVER_OBJECT_SET_LOCATION
        )
        datagram.addUint32(parent_id)
        datagram.addUint32(zone_id)
        self.send(datagram)

    def generateWithRequired(self, dist_obj, parent_id, zone_id, optionalFields=None):
        self.generateWithRequiredAndId(
            dist_obj,
            self.allocateChannel(),
            parent_id,
            zone_id,
            optionalFields or [],
        )

    def generateWithRequiredAndId(
        self, dist_obj, do_id, parent_id, zone_id, optionalFields=None
    ):
        dist_obj.doId = do_id
        self.addDOToTables(dist_obj, location=(parent_id, zone_id))
        dist_obj.sendGenerateWithRequired(
            self, parent_id, zone_id, optionalFields or []
        )

    def connect(self, host, port=7199):
        url = URLSpec()
        url.setServer(host)
        url.setPort(port)
        self.notify.info(f"Now connecting to {host}:{port}...")
        ConnectionRepository.connect(
            self,
            [url],
            successCallback=self.__connected,
            failureCallback=self.__connect_failed,
            failureArgs=[host, port],
        )

    def __connected(self):
        self.registerForChannel(self.ourChannel)
        if self.serverId:
            cleanup = PyDatagram()
            cleanup.addServerHeader(
                self.serverId,
                self.ourChannel,
                STATESERVER_DELETE_AI_OBJECTS,
            )
            cleanup.addChannel(self.ourChannel)
            self.addPostRemove(cleanup)
        messenger.send("airConnected")
        self.handleConnected()

    def __connect_failed(self, code, explanation, host, port):
        self.notify.warning(
            f"Failed to connect (code={code}; {explanation!r})"
        )
        retry = self.config.GetFloat("air-reconnect-delay", 5.0)
        taskMgr.doMethodLater(
            retry,
            self.connect,
            "Reconnect delay",
            extraArgs=[host, port],
        )

    def handleConnected(self):
        """Subclass hook called after Astron channel registration."""
        pass

    def lostConnection(self):
        self.notify.error("Lost connection to the Message Director")

    def setAI(self, do_id, ai_channel):
        datagram = PyDatagram()
        datagram.addServerHeader(do_id, ai_channel, STATESERVER_OBJECT_SET_AI)
        datagram.addUint64(ai_channel)
        self.send(datagram)

    set_ai = setAI

    def setOwner(self, do_id, new_owner):
        datagram = PyDatagram()
        datagram.addServerHeader(
            do_id, self.ourChannel, STATESERVER_OBJECT_SET_OWNER
        )
        datagram.addUint64(new_owner)
        self.send(datagram)

    set_owner = setOwner

    def setClientState(self, client_channel, state):
        datagram = PyDatagram()
        datagram.addServerHeader(
            client_channel, self.ourChannel, CLIENTAGENT_SET_STATE
        )
        datagram.addUint16(state)
        self.send(datagram)

    set_client_state = setClientState

    def clientAddSessionObject(self, client_channel, do_id):
        datagram = PyDatagram()
        datagram.addServerHeader(
            client_channel, self.ourChannel, CLIENTAGENT_ADD_SESSION_OBJECT
        )
        datagram.addUint32(do_id)
        self.send(datagram)

    client_add_session_object = clientAddSessionObject

    def clientAddInterest(
        self, client_channel, interest_id, parent_id, zone_id, callback=None
    ):
        datagram = PyDatagram()
        datagram.addServerHeader(
            client_channel, self.ourChannel, CLIENTAGENT_ADD_INTEREST
        )
        datagram.addUint16(interest_id)
        datagram.addUint32(parent_id)
        datagram.addUint32(zone_id)
        self.send(datagram)
        if callback is not None:
            self._callbacks[(client_channel, interest_id)] = callback

    def client_add_interest_multiple(
        self, client_channel, interest_id, parent_id, zone_list, callback=None
    ):
        datagram = PyDatagram()
        datagram.addServerHeader(
            client_channel, self.ourChannel, CLIENTAGENT_ADD_INTEREST_MULTIPLE
        )
        datagram.addUint16(interest_id)
        datagram.addUint32(parent_id)
        datagram.addUint16(len(zone_list))
        for zone_id in zone_list:
            datagram.addUint32(zone_id)
        if callback is not None:
            self._callbacks[(client_channel, interest_id)] = callback
        self.send(datagram)

    def client_remove_interest(self, client_channel, interest_id, callback=None):
        datagram = PyDatagram()
        datagram.addServerHeader(
            client_channel, self.ourChannel, CLIENTAGENT_REMOVE_INTEREST
        )
        datagram.addUint16(interest_id)
        self.send(datagram)
        if callback is not None:
            self._callbacks[(client_channel, interest_id)] = callback

    def handle_client_agent_interest_done_resp(self, di):
        client_channel = di.getUint64()
        interest_id = di.getUint16()
        context = (client_channel, interest_id)
        if context not in self._callbacks:
            self.notify.warning(
                "Received unexpected CLIENTAGENT_DONE_INTEREST_RESP "
                f"(ctx: {context})"
            )
            return
        try:
            self._callbacks[context](client_channel, interest_id)
        finally:
            del self._callbacks[context]
