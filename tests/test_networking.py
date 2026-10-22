import unittest
from unittest.mock import Mock, patch

from direct.directnotify.DirectNotifyGlobal import directNotify
from direct.distributed.ClientRepositoryBase import ClientRepositoryBase
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.PyDatagramIterator import PyDatagramIterator
from panda3d.direct import DCFile, DCPacker

from demo.constants import DC_FILE
from demo.networking.bulk_fields import handle_bulk_field_updates
from demo.networking.client_repository import AstronClientRepository
from demo.networking.database import AstronDatabaseInterface
from demo.networking.msgtypes import (
    DBSERVER_CREATE_OBJECT,
    DBSERVER_CREATE_OBJECT_RESP,
    DBSERVER_OBJECT_GET_ALL,
    DBSERVER_OBJECT_GET_ALL_RESP,
)


class AvatarProbe:
    def __init__(self, dclass, label, calls):
        self.dclass = dclass
        self.label = label
        self.calls = calls

    def setName(self, name):
        self.calls.append((self.label, "setName", name))

    def setPosition(self, x, y):
        self.calls.append((self.label, "setPosition", x, y))


class ClientRepositoryProbe(ClientRepositoryBase):
    pass


class DatagramIteratorProbe:
    def __init__(self, do_id):
        self.do_id = do_id

    def get_uint32(self):
        return self.do_id


class LeavingObjectProbe:
    def __init__(self):
        self.calls = []

    def disable(self):
        self.calls.append("disable")

    def delete(self):
        self.calls.append("delete")

    def deleteOrDelay(self):
        self.calls.append("deleteOrDelay")
        self.disable()
        self.delete()


def make_repository(dclass, do_id, visible=None, owner=None, deferred=None):
    repository = ClientRepositoryProbe.__new__(ClientRepositoryProbe)
    repository.doId2do = {do_id: visible} if visible is not None else {}
    repository.doId2ownerView = {do_id: owner} if owner is not None else {}
    repository.deferredDoIds = deferred or {}
    repository.dclassesByNumber = {dclass.getNumber(): dclass}
    repository.notify = directNotify.newCategory("BulkFieldTest")
    repository.identifyAvatar = lambda _do_id: None
    return repository


class ClientObjectLeavingTests(unittest.TestCase):
    def make_repository(self, objects=None):
        repository = AstronClientRepository.__new__(AstronClientRepository)
        repository.doId2do = objects or {}
        repository.cache = Mock()
        repository.cache.contains.return_value = False
        repository.isLocalId = lambda _do_id: False
        repository.notify = Mock()
        return repository

    def test_leave_uses_direct_delete_or_delay_lifecycle_once(self):
        do_id = 300012
        dist_obj = LeavingObjectProbe()
        repository = self.make_repository({do_id: dist_obj})

        with patch("demo.networking.client_repository.messenger.send") as send:
            repository.handle_object_leaving(DatagramIteratorProbe(do_id))

        self.assertNotIn(do_id, repository.doId2do)
        self.assertEqual(dist_obj.calls, ["deleteOrDelay", "disable", "delete"])
        send.assert_called_once_with("CLIENT_OBJECT_LEAVING", [do_id])

    def test_leave_for_missing_object_warns_without_raising(self):
        do_id = 300013
        repository = self.make_repository()

        with patch("demo.networking.client_repository.messenger.send") as send:
            repository.handle_object_leaving(DatagramIteratorProbe(do_id))

        repository.notify.warning.assert_called_once()
        send.assert_called_once_with("CLIENT_OBJECT_LEAVING", [do_id])


def bulk_datagram(do_id, dclass, updates):
    packer = DCPacker()
    for field_name, args in updates:
        field = dclass.getFieldByName(field_name)
        packer.rawPackUint16(field.getNumber())
        packer.beginPack(field)
        field.packArgs(packer, args)
        packer.endPack()

    datagram = PyDatagram()
    datagram.addUint32(do_id)
    datagram.addUint16(len(updates))
    datagram.appendData(bytes(packer.getBytes()))
    return datagram


class BulkFieldUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dc_file = DCFile()
        if not cls.dc_file.read(DC_FILE):
            raise RuntimeError(f"Could not read {DC_FILE}")
        cls.dclass = cls.dc_file.getClassByName("DemoAvatar")

    def test_updates_keep_wire_order_and_direct_owner_view_dispatch(self):
        do_id = 300010
        calls = []
        owner = AvatarProbe(self.dclass, "owner", calls)
        visible = AvatarProbe(self.dclass, "visible", calls)
        repository = make_repository(
            self.dclass, do_id, visible=visible, owner=owner
        )

        datagram = bulk_datagram(
            do_id,
            self.dclass,
            (
                ("setName", ("first",)),
                ("setPosition", (1.25, -2.5)),
                ("setName", ("last",)),
            ),
        )
        handle_bulk_field_updates(repository, PyDatagramIterator(datagram))

        self.assertEqual(
            calls,
            [
                ("owner", "setName", "first"),
                ("visible", "setName", "first"),
                ("owner", "setPosition", 1.25, -2.5),
                ("visible", "setPosition", 1.25, -2.5),
                ("owner", "setName", "last"),
                ("visible", "setName", "last"),
            ],
        )

    def test_updates_for_deferred_generate_replay_through_direct(self):
        do_id = 300011
        updates = (
            ("setName", ("before-generate",)),
            ("setPosition", (4.0, 3.0)),
        )
        generated_args = (5000, 1, self.dclass.getNumber(), do_id, None)
        deferred = {do_id: (generated_args, False, None, [])}
        repository = make_repository(
            self.dclass, do_id, deferred=deferred
        )

        datagram = bulk_datagram(do_id, self.dclass, updates)
        handle_bulk_field_updates(repository, PyDatagramIterator(datagram))

        queued = deferred[do_id][3]
        self.assertEqual(len(queued), len(updates))
        calls = []
        generated = AvatarProbe(self.dclass, "generated", calls)
        repository.doId2do[do_id] = generated
        for _datagram, iterator in queued:
            repository._ClientRepositoryBase__doUpdate(do_id, iterator, False)

        self.assertEqual(
            calls,
            [
                ("generated", "setName", "before-generate"),
                ("generated", "setPosition", 4.0, 3.0),
            ],
        )


class DatabaseProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dc_file = DCFile()
        if not dc_file.read(DC_FILE):
            raise RuntimeError(f"Could not read {DC_FILE}")
        cls.dc_file = dc_file
        cls.dclass = dc_file.getClassByName("DemoBeacon")

    def setUp(self):
        self.sent = []
        self.context = 70

        class FakeAir:
            ourChannel = 300001

            def __init__(air):
                air.dclassesByNumber = {self.dclass.getNumber(): self.dclass}
                air.sent = self.sent
                air.context = self.context

            def getContext(air):
                return air.context

            def send(air, datagram):
                air.sent.append(datagram)

        self.air = FakeAir()
        self.database = AstronDatabaseInterface(self.air)

    def test_create_object_packs_dc_fields_and_returns_created_id(self):
        callback_calls = []
        self.database.createObject(
            403000,
            self.dclass,
            {"setActivationCount": (7,)},
            callback_calls.append,
        )
        datagram = self.sent.pop()
        request = PyDatagramIterator(datagram)
        self.assertEqual(request.getUint8(), 1)
        self.assertEqual(request.getUint64(), 403000)
        self.assertEqual(request.getUint64(), 300001)
        self.assertEqual(request.getUint16(), DBSERVER_CREATE_OBJECT)
        self.assertEqual(request.getUint32(), self.context)
        self.assertEqual(request.getUint16(), self.dclass.getNumber())
        self.assertEqual(request.getUint16(), 1)
        payload = bytes(request.getRemainingBytes())
        unpacker = DCPacker()
        unpacker.setUnpackData(payload)
        field_id = unpacker.rawUnpackUint16()
        field = self.dclass.getFieldByIndex(field_id)
        unpacker.beginUnpack(field)
        self.assertEqual(field.unpackArgs(unpacker), (7,))
        unpacker.endUnpack()

        response = PyDatagram()
        response.addUint32(self.context)
        response.addUint32(500123)
        self.database.handleCreateObjectResp(PyDatagramIterator(response))
        self.assertEqual(callback_calls, [500123])

    def test_full_object_query_decodes_fields_for_callback(self):
        callback_calls = []
        self.database.queryObject(
            403000,
            500123,
            lambda dclass, fields: callback_calls.append((dclass, fields)),
        )
        datagram = self.sent.pop()
        request = PyDatagramIterator(datagram)
        self.assertEqual(request.getUint8(), 1)
        self.assertEqual(request.getUint64(), 403000)
        self.assertEqual(request.getUint64(), 300001)
        self.assertEqual(request.getUint16(), DBSERVER_OBJECT_GET_ALL)
        self.assertEqual(request.getUint32(), self.context)
        self.assertEqual(request.getUint32(), 500123)

        field = self.dclass.getFieldByName("setActivationCount")
        packer = DCPacker()
        packer.rawPackUint16(field.getNumber())
        packer.beginPack(field)
        field.packArgs(packer, (9,))
        packer.endPack()
        response = PyDatagram()
        response.addUint32(self.context)
        response.addUint8(1)
        response.addUint16(self.dclass.getNumber())
        response.addUint16(1)
        response.appendData(bytes(packer.getBytes()))

        self.database.handleQueryObjectResp(
            DBSERVER_OBJECT_GET_ALL_RESP,
            PyDatagramIterator(response),
        )
        self.assertEqual(
            callback_calls,
            [(self.dclass, {"setActivationCount": (9,)})],
        )



if __name__ == "__main__":
    unittest.main()
