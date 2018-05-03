'''
Python VXI-11 Server
Simuration for Instrument
'''
#from . import rpc
import random
import re
import struct
import time
import rpc

# VXI-11 RPC constants

# Device async
DEVICE_ASYNC_PROG = 0x0607b0
DEVICE_ASYNC_VERS = 1
DEVICE_ABORT      = 1

# Device core
DEVICE_CORE_PROG  = 0x0607af
DEVICE_CORE_VERS  = 1
CREATE_LINK       = 10
DEVICE_WRITE      = 11
DEVICE_READ       = 12
DEVICE_READSTB    = 13
DEVICE_TRIGGER    = 14
DEVICE_CLEAR      = 15
DEVICE_REMOTE     = 16
DEVICE_LOCAL      = 17
DEVICE_LOCK       = 18
DEVICE_UNLOCK     = 19
DEVICE_ENABLE_SRQ = 20
DEVICE_DOCMD      = 22
DESTROY_LINK      = 23
CREATE_INTR_CHAN  = 25
DESTROY_INTR_CHAN = 26

# Device intr
DEVICE_INTR_PROG  = 0x0607b1
DEVICE_INTR_VERS  = 1
DEVICE_INTR_SRQ   = 30

# Error states
ERR_NO_ERROR = 0
ERR_SYNTAX_ERROR = 1
ERR_DEVICE_NOT_ACCESSIBLE = 3
ERR_INVALID_LINK_IDENTIFIER = 4
ERR_PARAMETER_ERROR = 5
ERR_CHANNEL_NOT_ESTABLISHED = 6
ERR_OPERATION_NOT_SUPPORTED = 8
ERR_OUT_OF_RESOURCES = 9
ERR_DEVICE_LOCKED_BY_ANOTHER_LINK = 11
ERR_NO_LOCK_HELD_BY_THIS_LINK = 12
ERR_IO_TIMEOUT = 15
ERR_IO_ERROR = 17
ERR_INVALID_ADDRESS = 21
ERR_ABORT = 23
ERR_CHANNEL_ALREADY_ESTABLISHED = 29

# Flags
OP_FLAG_WAIT_BLOCK = 1
OP_FLAG_END = 8
OP_FLAG_TERMCHAR_SET = 128

RX_REQCNT = 1
RX_CHR = 2
RX_END = 4

# IEEE 488.1 interface device commands
CMD_SEND_COMMAND = 0x020000
CMD_BUS_STATUS   = 0x020001
CMD_ATN_CTRL     = 0x020002
CMD_REN_CTRL     = 0x020003
CMD_PASS_CTRL    = 0x020004
CMD_BUS_ADDRESS  = 0x02000A
CMD_IFC_CTRL     = 0x020010

CMD_BUS_STATUS_REMOTE = 1
CMD_BUS_STATUS_SRQ = 2
CMD_BUS_STATUS_NDAC = 3
CMD_BUS_STATUS_SYSTEM_CONTROLLER = 4
CMD_BUS_STATUS_CONTROLLER_IN_CHARGE = 5
CMD_BUS_STATUS_TALKER = 6
CMD_BUS_STATUS_LISTENER = 7
CMD_BUS_STATUS_BUS_ADDRESS = 8

GPIB_CMD_GTL = 0x01 # go to local
GPIB_CMD_SDC = 0x04 # selected device clear
GPIB_CMD_PPC = 0x05 # parallel poll config
GPIB_CMD_GET = 0x08 # group execute trigger
GPIB_CMD_TCT = 0x09 # take control
GPIB_CMD_LLO = 0x11 # local lockout
GPIB_CMD_DCL = 0x14 # device clear
GPIB_CMD_PPU = 0x15 # parallel poll unconfigure
GPIB_CMD_SPE = 0x18 # serial poll enable
GPIB_CMD_SPD = 0x19 # serial poll disable
GPIB_CMD_LAD = 0x20 # listen address (base)
GPIB_CMD_UNL = 0x3F # unlisten
GPIB_CMD_TAD = 0x40 # talk address (base)
GPIB_CMD_UNT = 0x5F # untalk
GPIB_CMD_SAD = 0x60 # my secondary address (base)
GPIB_CMD_PPE = 0x60 # parallel poll enable (base)
GPIB_CMD_PPD = 0x70 # parallel poll disable

class Packer(rpc.Packer):
    def pack_device_link(self, link):
        self.pack_int(link)

    def pack_create_link_parms(self, params):
        id, lock_device, lock_timeout, device = params
        self.pack_int(id)
        self.pack_bool(lock_device)
        self.pack_uint(lock_timeout)
        self.pack_string(device)

    def pack_device_write_parms(self, params):
        link, timeout, lock_timeout, flags, data = params
        self.pack_int(link)
        self.pack_uint(timeout)
        self.pack_uint(lock_timeout)
        self.pack_int(flags)
        self.pack_opaque(data)

    def pack_device_read_parms(self, params):
        link, request_size, timeout, lock_timeout, flags, term_char = params
        self.pack_int(link)
        self.pack_uint(request_size)
        self.pack_uint(timeout)
        self.pack_uint(lock_timeout)
        self.pack_int(flags)
        self.pack_int(term_char)

    def pack_device_generic_parms(self, params):
        link, flags, lock_timeout, timeout = params
        self.pack_int(link)
        self.pack_int(flags)
        self.pack_uint(lock_timeout)
        self.pack_uint(timeout)

    def pack_device_remote_func_parms(self, params):
        host_addr, host_port, prog_num, prog_vers, prog_family = params
        self.pack_uint(host_addr)
        self.pack_uint(host_port)
        self.pack_uint(prog_num)
        self.pack_uint(prog_vers)
        self.pack_int(prog_family)

    def pack_device_enable_srq_parms(self, params):
        link, enable, handle = params
        self.pack_int(link)
        self.pack_bool(enable)
        if len(handle) > 40:
            raise Vxi11Exception("array length too long")
        self.pack_opaque(handle)

    def pack_device_lock_parms(self, params):
        link, flags, lock_timeout = params
        self.pack_int(link)
        self.pack_int(flags)
        self.pack_uint(lock_timeout)

    def pack_device_docmd_parms(self, params):
        link, flags, timeout, lock_timeout, cmd, network_order, datasize, data_in = params
        self.pack_int(link)
        self.pack_int(flags)
        self.pack_uint(timeout)
        self.pack_uint(lock_timeout)
        self.pack_int(cmd)
        self.pack_bool(network_order)
        self.pack_int(datasize)
        self.pack_opaque(data_in)

    def pack_device_error(self, error):
        self.pack_int(error)

    def pack_device_srq_parms(self, params):
        handle = params
        self.pack_opaque(handle)

    def pack_create_link_resp(self, params):
        error, link, abort_port, max_recv_size = params
        self.pack_int(error)
        self.pack_int(link)
        self.pack_uint(abort_port)
        self.pack_uint(max_recv_size)

    def pack_device_write_resp(self, params):
        error, size = params
        self.pack_int(error)
        self.pack_uint(size)

    def pack_device_read_resp(self, params):
        error, reason, data = params
        self.pack_int(error)
        self.pack_int(reason)
        self.pack_opaque(data)

    def pack_device_read_stb_resp(self, params):
        error, stb = params
        self.pack_int(error)
        self.pack_uint(stb)

    def pack_device_docmd_resp(self, params):
        error, data_out = params
        self.pack_int(error)
        self.pack_opaque(data_out)

class Unpacker(rpc.Unpacker):
    def unpack_device_link(self):
        return self.unpack_int()

    def unpack_create_link_parms(self):
        id = self.unpack_int()
        lock_device = self.unpack_bool()
        lock_timeout = self.unpack_uint()
        device = self.unpack_string()
        return id, lock_device, lock_timeout, device

    def unpack_device_write_parms(self):
        link = self.unpack_int()
        timeout = self.unpack_uint()
        lock_timeout = self.unpack_uint()
        flags = self.unpack_int()
        data = self.unpack_opaque()
        return link, timeout, lock_timeout, flags, data

    def unpack_device_read_parms(self):
        link = self.unpack_int()
        request_size = self.unpack_uint()
        timeout = self.unpack_uint()
        lock_timeout = self.unpack_uint()
        flags = self.unpack_int()
        term_char = self.unpack_int()
        return link, request_size, timeout, lock_timeout, flags, term_char

    def unpack_device_generic_parms(self):
        link = self.unpack_int()
        flags = self.unpack_int()
        lock_timeout = self.unpack_uint()
        timeout = self.unpack_uint()
        return link, flags, lock_timeout, timeout

    def unpack_device_remote_func_parms(self):
        host_addr = self.unpack_uint()
        host_port = self.unpack_uint()
        prog_num = self.unpack_uint()
        prog_vers = self.unpack_uint()
        prog_family = self.unpack_int()
        return host_addr, host_port, prog_num, prog_vers, prog_family

    def unpack_device_enable_srq_parms(self):
        link = self.unpack_int()
        enable = self.unpack_bool()
        handle = self.unpack_opaque()
        return link, enable, handle

    def unpack_device_lock_parms(self):
        link = self.unpack_int()
        flags = self.unpack_int()
        lock_timeout = self.unpack_uint()
        return link, flags, lock_timeout

    def unpack_device_docmd_parms(self):
        link = self.unpack_int()
        flags = self.unpack_int()
        timeout = self.unpack_uint()
        lock_timeout = self.unpack_uint()
        cmd = self.unpack_int()
        network_order = self.unpack_bool()
        datasize = self.unpack_int()
        data_in = self.unpack_opaque()
        return link, flags, timeout, lock_timeout, cmd, network_order, datasize, data_in

    def unpack_device_error(self):
        return self.unpack_int()

    def unpack_device_srq_params(self):
        handle = self.unpack_opaque()
        return handle

    def unpack_create_link_resp(self):
        error = self.unpack_int()
        link = self.unpack_int()
        abort_port = self.unpack_uint()
        max_recv_size = self.unpack_uint()
        return error, link, abort_port, max_recv_size

    def unpack_device_write_resp(self):
        error = self.unpack_int()
        size = self.unpack_uint()
        return error, size

    def unpack_device_read_resp(self):
        error = self.unpack_int()
        reason = self.unpack_int()
        data = self.unpack_opaque()
        return error, reason, data

    def unpack_device_read_stb_resp(self):
        error = self.unpack_int()
        stb = self.unpack_uint()
        return error, stb

    def unpack_device_docmd_resp(self):
        error = self.unpack_int()
        data_out = self.unpack_opaque()
        return error, data_out

    def done(self):
        # ignore any trailing bytes
        pass



class CoreServer(rpc.TCPServer):
    def __init__(self, host, port=0):
        self.packer = Packer()
        self.unpacker = Unpacker('')
        rpc.TCPServer.__init__(self, host, DEVICE_CORE_PROG, DEVICE_CORE_VERS, port)


class DeviceMoc(object):
    '''VXI-11 Device Moc'''
    def __init__(self, host, name = None, client_id = None, term_char = None):

        self.server = None
        self.abort_server = None

        self.host = host
        self.name = name
        self.client_id = client_id
        self.term_char = term_char
        self.lock_timeout = 10
        self.timeout = 10
        self.abort_port = 0
        self.link = None
        self.max_recv_size = 0
        self.max_read_len = 128*1024*1024
        self.locked = False

    def __del__(self):
        if self.link is not None:
            self.close()

    def open(self):
        "Open connection to VXI-11 device"
        if self.link is not None:
            return

        if self.server is None:
            self.server = CoreServer(self.host,port=111)

        self.server.sock.settimeout(self.timeout+1)
        error = self.server.loop()

        print("Connected")
        self.server.register()
        print("register")

        #if error:
        #    raise Vxi11Exception(error, 'open')

        #self.abort_port = abort_port

        #self.link = link
        #self.max_recv_size = min(max_recv_size, 1024*1024)

    def mainloop(self):
        self.server.loop()

    def close(self):
        "Close connection"
        if self.link is None:
            return

        self.client.destroy_link(self.link)
        self.client.close()
        self.link = None
        self.client = None


if __name__ == '__main__':
    inst = DeviceMoc("127.0.0.1")
    inst.open()
    inst.mainloop()
