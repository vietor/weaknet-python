#!/usr/bin/env python

from __future__ import division, print_function, with_statement


VERSION = "1.2.0"

DEFAULT_LOCAL_PORT = 51080
DEFAULT_REMOTE_PORT = 58080

################################################
import os
import sys
import time
import errno
import signal
import logging
import hashlib


def f4str(s):
    if bytes != str:
        if type(s) == bytes:
            return s.decode('utf-8')
    return str(s)


def f4bytes(s):
    if bytes != str:
        if type(s) == str:
            return s.encode('utf-8')
    return bytes(s)


def sha512(text):
    m = hashlib.sha512()
    m.update(f4bytes(text))
    return m.digest()


def errno_at_exc(e):
    if hasattr(e, 'errno'):
        return e.errno
    elif e.args:
        return e.args[0]
    else:
        return None


logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

################################################
import collections
from collections import defaultdict


class LRUCache(collections.MutableMapping):

    def __init__(self, timeout=60, callback=None, *args, **kwargs):
        self._timeout = timeout
        self._callback = callback

        self._kv = {}
        self._key_times = {}
        self._time_keys = defaultdict(list)
        self._histories = collections.deque()
        self.update(dict(*args, **kwargs))

    def _rfr_key(self, key):
        now = time.time()
        self._key_times[key] = now
        self._time_keys[now].append(key)
        self._histories.append(now)

    def _del_key(self, key):
        del self._kv[key]
        del self._key_times[key]

    def __getitem__(self, key):
        value = self._kv[key]
        if value:
            self._rfr_key(key)
        return value

    def __setitem__(self, key, value):
        self._rfr_key(key)
        self._kv[key] = value

    def __delitem__(self, key):
        self._del_key[key]

    def __iter__(self):
        return iter(self._kv)

    def __len__(self):
        return len(self._kv)

    def handle_timer(self):
        now = time.time()
        expire_keys = set()
        while len(self._histories) > 0:
            least = self._histories[0]
            if now - least < self._timeout:
                break
            for key in self._time_keys[least]:
                self._histories.popleft()
                if key not in self._kv:
                    continue
                if now - self._key_times[key] < self._timeout:
                    continue
                if key in expire_keys:
                    continue
                expire_keys.add(key)
                if not self._callback:
                    self._del_key(key)
                else:
                    value = self._kv[key]
                    self._del_key(key)
                    self._callback(value)

            del self._time_keys[least]


################################################
import select


POLL_NONE = 0x00
POLL_IN = 0x01
POLL_OUT = 0x04
POLL_ERR = 0x08
POLL_HUP = 0x10
POLL_NVAL = 0x20

TIMEOUT_OF_TIMER = 5
TIMEOUT_OF_ACTION = 7


class SelectAsPoll(object):

    def __init__(self):
        self._r_list = set()
        self._w_list = set()
        self._x_list = set()

    def poll(self, timeout):
        results = defaultdict(lambda: POLL_NONE)
        r, w, x = select.select(self._r_list, self._w_list, self._x_list,
                                timeout)
        for p in [(r, POLL_IN), (w, POLL_OUT), (x, POLL_ERR)]:
            for fd in p[0]:
                results[fd] |= p[1]
        return list(results.items())

    def register(self, fd, mode):
        if mode & POLL_IN:
            self._r_list.add(fd)
        if mode & POLL_OUT:
            self._w_list.add(fd)
        if mode & POLL_ERR:
            self._x_list.add(fd)

    def unregister(self, fd):
        if fd in self._r_list:
            self._r_list.remove(fd)
        if fd in self._w_list:
            self._w_list.remove(fd)
        if fd in self._x_list:
            self._x_list.remove(fd)

    def modify(self, fd, mode):
        self.unregister(fd)
        self.register(fd, mode)

    def close(self):
        pass


class KqueueAsPoll(object):

    def __init__(self):
        self._fds = {}
        self._kqueue = select.kqueue()

    def _control(self, fd, mode, flags):
        events = []
        if mode & POLL_IN:
            events.append(select.kevent(fd, select.KQ_FILTER_READ, flags))
        if mode & POLL_OUT:
            events.append(select.kevent(fd, select.KQ_FILTER_WRITE, flags))
        for e in events:
            self._kqueue.control([e], 0)

    def poll(self, timeout):
        results = defaultdict(lambda: POLL_NONE)
        events = self._kqueue.control(None, 2048,
                                      None if timeout < 0 else timeout)
        for e in events:
            fd = e.ident
            if e.filter == select.KQ_FILTER_READ:
                results[fd] |= POLL_IN
            elif e.filter == select.KQ_FILTER_WRITE:
                results[fd] |= POLL_OUT
        return list(results.items())

    def register(self, fd, mode):
        self._fds[fd] = mode
        self._control(fd, mode, select.KQ_EV_ADD)

    def unregister(self, fd):
        self._control(fd, self._fds[fd], select.KQ_EV_DELETE)
        del self._fds[fd]

    def modify(self, fd, mode):
        self.unregister(fd)
        self.register(fd, mode)

    def close(self):
        self._kqueue.close()


class LoopHandler(object):

    def handle_event(sock, fd, event):
        pass


class EventLoop(object):

    def __init__(self):
        if hasattr(select, 'epoll'):
            model = 'epoll'
            self._engine = select.epoll()
        elif hasattr(select, 'kqueue'):
            model = 'kqueue'
            self._engine = KqueueAsPoll()
        elif hasattr(select, 'select'):
            model = 'select'
            self._engine = SelectAsPoll()
        else:
            raise Exception('can not find any available functions in select')
        logging.debug('using event model: %s', model)
        self._stopping = False
        self._fd_handlers = {}
        self._last_time = time.time()
        self._timer_callbacks = []

    def __del__(self):
        self._engine.close()

    def poll(self, timeout=None):
        events = self._engine.poll(timeout)
        return [(self._fd_handlers[fd][0], fd, event) for fd, event in events]

    def add(self, f, mode, handler):
        fd = f.fileno()
        self._fd_handlers[fd] = (f, handler)
        self._engine.register(fd, mode)

    def remove(self, f):
        fd = f.fileno()
        del self._fd_handlers[fd]
        self._engine.unregister(fd)

    def modify(self, f, mode):
        fd = f.fileno()
        self._engine.modify(fd, mode)

    def stop(self):
        self._stopping = True

    def add_timer(self, callback):
        self._timer_callbacks.append(callback)

    def remove_timer(self, callback):
        self._timer_callbacks.remove(callback)

    def run(self):
        events = []
        while not self._stopping:
            run_timer = False
            try:
                events = self.poll(TIMEOUT_OF_TIMER)
            except (OSError, IOError) as e:
                if errno_at_exc(e) in (errno.EPIPE, errno.EINTR):
                    run_timer = True
                else:
                    logging.error('poll: %s', e)
                    continue

            for sock, fd, event in events:
                handler = self._fd_handlers.get(fd, None)
                if handler is not None:
                    handler = handler[1]
                    try:
                        handler.handle_event(sock, fd, event)
                    except (OSError, IOError) as e:
                        logging.error('loop handle: %s', e)

            if not run_timer:
                now = time.time()
                if now - self._last_time >= TIMEOUT_OF_TIMER:
                    run_timer = True
                    self._last_time = now

            if run_timer:
                for callback in self._timer_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logging.error('loop timer: %s', e)

################################################


class SecretFool(object):

    def __init__(self, secret):
        buff = sha512(secret)
        self._epos = 0
        self._dpos = 0
        self._bbuff = bytearray(buff)
        self._bsize = len(self._bbuff)
        self._qsize = int(self._bsize / 8)
        self._qbuff = struct.unpack("<" + str(self._qsize) + "Q", buff)

    def _xor(self, data, xpos):
        pos = 0
        size = len(data)
        dest = bytearray(size)

        if xpos > 0 and xpos % 8 != 0:
            qcnt = 8 - (xpos % 8)
            if qcnt <= size:
                pos += qcnt
                orig = bytearray(data[:qcnt])
                for i in range(qcnt):
                    dest[i] = orig[i] ^ self._bbuff[xpos]
                    xpos = (xpos + 1) % self._bsize

        if pos < size and size - pos > 8:
            qpos = int(xpos / 8)
            qcnt = int((size - pos) / 8)
            for i in range(qcnt):
                kq = self._qbuff[qpos]
                qpos = (qpos + 1) % self._qsize
                sq = struct.unpack_from("<1Q", data, pos)[0]
                struct.pack_into("<1Q", dest, pos, sq ^ kq)
                pos += 8

            xpos = qpos * 8

        if pos < size:
            qcnt = size - pos
            orig = bytearray(data[pos:])
            for i in range(qcnt):
                dest[pos + i] = orig[i] ^ self._bbuff[xpos]
                xpos = (xpos + 1) % self._bsize

        return (str(dest), xpos)

    def encrypt(self, data):
        dest, self._epos = self._xor(data, self._epos)
        return dest

    def decrypt(self, data):
        dest, self._dpos = self._xor(data, self._dpos)
        return dest


def make_secret(algorithm, secret):
    if(algorithm == "fool"):
        return SecretFool(secret)
    raise Exception("algorithm unsupport")


################################################
import socket
import struct
import random

QTYPE_ANY = 255
QTYPE_A = 1
QTYPE_AAAA = 28
QTYPE_CNAME = 5
QTYPE_NS = 2
QCLASS_IN = 1

STEP_INIT = 0
STEP_ADDRESS = 1
STEP_CONNECT = 2
STEP_RELAYING = 3
STEP_TRANSPORT = 4
STEP_TERMINATE = -1

STATUS_INIT = 0
STATUS_READ = 1
STATUS_WRITE = 2
STATUS_READWRITE = STATUS_READ | STATUS_WRITE

ACTION_SET = 0
ACTION_ADD = 1
ACTION_DEL = 2

TRAFFIC_OK = 0
TRAFFIC_BLOCK = 1


def is_ip(address):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, f4str(address))
            return family
        except (TypeError, ValueError, OSError, IOError) as e:
            pass
    return False


def get_local_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except (OSError, IOError):
        pass
    return "127.0.0.1"


def get_sock_error(sock):
    error_number = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    return socket.error(error_number, os.strerror(error_number))


def get_sock_byaddr(addr, port):
    try:
        addrs = socket.getaddrinfo(addr, port, 0, socket.SOCK_STREAM,
                                   socket.SOL_TCP)
        if len(addrs) != 0:
            af, socktype, proto, canonname, sa = addrs[0]
            return socket.socket(af, socktype, proto), sa
    except Exception as e:
        pass
    return None, None


class DNSResponse(object):
    __slots__ = ('hostname', 'questions', 'answers')

    def __init__(self):
        self.hostname = None
        self.questions = []  # each: (addr, type, class)
        self.answers = []  # each: (addr, type, class)

    def __str__(self):
        return '%s: %s' % (self.hostname, str(self.answers))


def dns_build_request(address, qtype):
    header = struct.pack('!BBHHHH', 1, 0, 1, 0, 0, 0)
    request_id = ''.join([chr(random.randint(0, 255)),
                          chr(random.randint(0, 255))])

    address = address.strip(b'.')
    labels = address.split(b'.')
    results = []
    for label in labels:
        l = len(label)
        if l > 63:
            raise Exception('dns address error')
        results.append(chr(l))
        results.append(label)

    results.append(b'\0')

    addr = b''.join(results)
    qtype_qclass = struct.pack('!HH', qtype, QCLASS_IN)
    return request_id + header + addr + qtype_qclass


def dns_parse_ip(addrtype, data, length, offset):
    if addrtype == QTYPE_A:
        return socket.inet_ntop(socket.AF_INET, data[offset:offset + length])
    elif addrtype == QTYPE_AAAA:
        return socket.inet_ntop(socket.AF_INET6, data[offset:offset + length])
    elif addrtype in [QTYPE_CNAME, QTYPE_NS]:
        return dns_parse_name(data, offset)[1]
    else:
        return data[offset:offset + length]


def dns_parse_name(data, offset):
    p = offset
    labels = []
    l = ord(data[p])
    while l > 0:
        if (l & (128 + 64)) == (128 + 64):
            pointer = struct.unpack('!H', data[p:p + 2])[0]
            pointer &= 0x3FFF
            r = dns_parse_name(data, pointer)
            labels.append(r[1])
            p += 2
            return p - offset, b'.'.join(labels)
        else:
            labels.append(data[p + 1:p + 1 + l])
            p += 1 + l

        l = ord(data[p])
    return p - offset + 1, b'.'.join(labels)


def dns_parse_record(data, offset, question=False):
    nlen, name = dns_parse_name(data, offset)
    if not question:
        record_type, record_class, record_ttl, record_rdlength = struct.unpack(
            '!HHiH', data[offset + nlen:offset + nlen + 10]
        )
        ip = dns_parse_ip(record_type, data, record_rdlength,
                          offset + nlen + 10)
        return nlen + 10 + record_rdlength, \
            (name, ip, record_type, record_class, record_ttl)
    else:
        record_type, record_class = struct.unpack(
            '!HH', data[offset + nlen:offset + nlen + 4]
        )
        return nlen + 4, (name, None, record_type, record_class, None, None)


def dns_parse_response(data):
    if len(data) < 12:
        return None
    try:
        header = struct.unpack('!HBBHHHH', data[:12])
        res_id = header[0]
        res_qr = header[1] & 128
        res_tc = header[1] & 2
        res_ra = header[2] & 128
        res_rcode = header[2] & 15
        res_qdcount = header[3]
        res_ancount = header[4]
        res_nscount = header[5]
        res_arcount = header[6]

        qds = []
        ans = []
        offset = 12
        for i in range(0, res_qdcount):
            l, r = dns_parse_record(data, offset, True)
            offset += l
            if r:
                qds.append(r)
        for i in range(0, res_ancount):
            l, r = dns_parse_record(data, offset)
            offset += l
            if r:
                ans.append(r)
        for i in range(0, res_nscount):
            l, r = dns_parse_record(data, offset)
            offset += l
        for i in range(0, res_arcount):
            l, r = dns_parse_record(data, offset)
            offset += l

        response = DNSResponse()
        if qds:
            response.hostname = qds[0][0]
        for an in qds:
            response.questions.append((an[1], an[2], an[3]))
        for an in ans:
            response.answers.append((an[1], an[2], an[3]))
        return response
    except Exception as e:
        return None


class DNSController(LoopHandler):

    def __init__(self, bufsize, servers=['8.8.4.4', '8.8.8.8']):
        self._loop = None
        self._servers = servers
        self._bufsize = bufsize * 1024
        self._cache = LRUCache(timeout=300)
        self._hostname_qtypes = {}
        self._hostname_callbacks = {}
        self._callback_hostnames = {}

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                   socket.SOL_UDP)
        self._sock.setblocking(False)

    def bind(self, loop):
        self._loop = loop
        self._loop.add(self._sock, POLL_IN | POLL_ERR, self)
        self._loop.add_timer(self.handle_timer)

    def close(self):
        if not self._sock:
            return
        logging.debug('DNS close')
        if self._loop:
            self._loop.remove_timer(self.handle_timer)
            self._loop.remove(self._sock)

        self._sock.close()
        self._sock = None

    def handle_timer(self):
        self._cache.handle_timer()

    def handle_event(self, sock, fd, event):
        if sock != self._sock:
            return
        if event & POLL_ERR:
            self._loop.remove(self._sock)
            self._sock.close()
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                       socket.SOL_UDP)
            self._sock.setblocking(False)
            self._loop.add(self._sock, POLL_IN | POLL_ERR, self)
        else:
            try:
                data, addr = sock.recvfrom(self._bufsize)
                if addr[0] not in self._servers:
                    logging.warn('received a packet unkonw dns')
                    return
                self._handle_read(data)
            except Exception as e:
                logging.error("dns handle: %s", e)

    def _handle_read(self, data):
        response = dns_parse_response(data)
        if not response or not response.hostname:
            return

        ip = None
        for answer in response.answers:
            if answer[1] in (QTYPE_A, QTYPE_AAAA) and \
               answer[2] == QCLASS_IN:
                ip = answer[0]
                break

        hostname = response.hostname
        if not ip and self._hostname_qtypes.get(hostname, QTYPE_AAAA) == QTYPE_A:
            self._hostname_qtypes[hostname] = QTYPE_AAAA
            self._send_req(hostname, QTYPE_AAAA)
        else:
            if ip:
                self._cache[hostname] = ip
                self._call_callback(hostname, ip)
            elif self._hostname_qtypes.get(hostname, None) == QTYPE_AAAA:
                for question in response.questions:
                    if question[1] == QTYPE_AAAA:
                        self._call_callback(hostname, None)
                        break

    def _call_callback(self, hostname, ip):
        for callback in self._hostname_callbacks.get(hostname, []):
            if callback in self._callback_hostnames:
                del self._callback_hostnames[callback]
            if ip:
                callback(hostname, ip)
            else:
                callback(hostname, None)

        if hostname in self._hostname_callbacks:
            del self._hostname_callbacks[hostname]

        if hostname in self._hostname_qtypes:
            del self._hostname_qtypes[hostname]

    def _send_req(self, hostname, qtype):
        req = dns_build_request(hostname, qtype)
        for server in self._servers:
            self._sock.sendto(req, (server, 53))

    def register(self, callback, hostname):
        if not hostname:
            callback(None, None)
        elif is_ip(hostname):
            callback(hostname, hostname)
        elif hostname in self._cache:
            callback(hostname, self._cache[hostname])
        else:
            arr = self._hostname_callbacks.get(hostname, None)
            if not arr:
                self._send_req(hostname, QTYPE_A)
                self._hostname_qtypes[hostname] = QTYPE_A
                self._hostname_callbacks[hostname] = [callback]
                self._callback_hostnames[callback] = hostname
            else:
                arr.append(callback)
                self._send_req(hostname, QTYPE_A)

    def unregister(self, callback):
        hostname = self._callback_hostnames.get(callback)
        if hostname:
            del self._callback_hostnames[callback]
            arr = self._hostname_callbacks.get(hostname, None)
            if arr:
                arr.remove(callback)
                if not arr:
                    del self._hostname_callbacks[hostname]
                    if hostname in self._hostname_qtypes:
                        del self._hostname_qtypes[hostname]


class TCPServiceSocket(object):

    def __init__(self, loop, service, bufsize):
        self._loop = loop
        self._service = service
        self._bufsize = bufsize * 1024
        self._sock = None
        self._status = STATUS_INIT
        self._data_to_write = []

    def attach(self, sock, status=STATUS_READ):
        if self._sock:
            raise Exception('sock already attach')

        self._sock = sock
        self._status = status
        self._loop.add(self._sock, self._make_event(status), self)

    def has_error(self):
        if not self._sock:
            return True
        return self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) != 0

    def send(self, data):
        self._write(data)

    def close(self):
        if not self._sock:
            return
        self._loop.remove(self._sock)
        self._sock.close()
        self._sock = None

    def handle_event(self, sock, fd, event):
        if self._sock and event & POLL_ERR:
            self._on_event_error()
        if self._sock and event & (POLL_IN | POLL_HUP):
            self._on_event_read()
        if self._sock and event & POLL_OUT:
            self._on_event_write()

    def _make_event(self, status):
        event = POLL_ERR
        if status & STATUS_WRITE:
            event |= POLL_OUT
        if status & STATUS_READ:
            event |= POLL_IN
        return event

    def set_status(self, status, action=ACTION_SET):
        if not self._sock:
            return
        self._update_status(status, action)

    def _update_status(self, status, action):
        update = self._status
        if action == ACTION_ADD:
            if update & status == status:
                return
            update |= status
        elif action == ACTION_DEL:
            if update & status == 0:
                return
            update &= ~status
        else:
            if update == status:
                return
            update = status

        self._status = update
        self._loop.modify(self._sock, self._make_event(update))

    def _write(self, data):
        if not data:
            return

        incomplete = False
        if len(self._data_to_write) > 0:
            incomplete = True
        else:
            try:
                l = len(data)
                s = self._sock.send(data)
                if s < l:
                    data = data[s:]
                    incomplete = True
            except (OSError, IOError) as e:
                if errno_at_exc(e) in \
                   (errno.EAGAIN, errno.EINPROGRESS, errno.EWOULDBLOCK):
                    incomplete = True
                else:
                    logging.error("sock write: %s", e)
                    self._service.terminate()
                    return

        if incomplete:
            self._data_to_write.append(data)

        self._service.handle_traffic(self,
                                     TRAFFIC_BLOCK if incomplete else TRAFFIC_OK)

    def _on_event_read(self):
        data = None
        try:
            data = self._sock.recv(self._bufsize)
        except (OSError, IOError) as e:
            if errno_at_exc(e) in \
               (errno.ETIMEDOUT, errno.EAGAIN, errno.EWOULDBLOCK):
                return
        if not data:
            self._service.terminate()
            return

        try:
            self._service.handle_read(self, data)
        except Exception as e:
            logging.error("data handle: %s", e)
            self._service.terminate()
            return

    def _on_event_write(self):
        self._service.handle_write(self)
        if not self._sock:
            return
        if len(self._data_to_write) > 0:
            data = b''.join(self._data_to_write)
            self._data_to_write = []
            self._write(data)
        else:
            self._service.handle_traffic(self, TRAFFIC_OK)

    def _on_event_error(self):
        if self._sock:
            logging.error("sock error: %s", get_sock_error(self._sock))
            self._service.terminate()


class TCPService(object):

    def __init__(self, controller, conn, options):
        self._controller = controller
        self._step = STEP_INIT
        self._controller._services[id(self)] = self
        self._source = TCPServiceSocket(controller._loop, self,
                                        options.bufsize)
        self._source_addr = conn[1]
        self._target = TCPServiceSocket(controller._loop, self,
                                        options.bufsize)
        self._target_addr = None
        self._address_wait = 0
        self._connect_wait = 0

        sock = conn[0]
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self._source.attach(sock)

    def terminate(self):
        if self._step == STEP_TERMINATE:
            return

        self._clear_address_wait()
        self._clear_connect_wait()

        if self._step == STEP_CONNECT:
            self._controller._dnsc.unregister(self.address_complete)

        self._step = STEP_TERMINATE
        if self._source:
            self._source.close()
            self._source = None
        if self._target:
            self._target.close()
            self._target = None

        del self._controller._services[id(self)]

    def _clear_address_wait(self):
        if self._address_wait > 0:
            self._address_wait = 0
            self._controller._loop.remove_timer(self.address_timeout)

    def _clear_connect_wait(self):
        if self._connect_wait > 0:
            self._connect_wait = 0
            self._controller._loop.remove_timer(self.connect_timeout)

    def connect(self, addr, port):
        self._step = STEP_CONNECT
        self._target_addr = (addr, port)
        self._address_wait = time.time() + TIMEOUT_OF_ACTION
        self._controller._loop.add_timer(self.address_timeout)
        self._controller._dnsc.register(self.address_complete, addr)

    def handle_connect(self, error):
        pass

    def handle_traffic(self, ssock, flag):
        if flag == TRAFFIC_BLOCK:
            action = ACTION_DEL
        else:
            action = ACTION_ADD
        if ssock == self._source:
            self._target.set_status(STATUS_READ, action)
        elif ssock == self._target:
            self._source.set_status(STATUS_READ, action)

    def connect_timeout(self):
        if self._step == STEP_TERMINATE:
            return

        if self._step == STEP_CONNECT:
            if time.time() >= self._connect_wait:
                logging.debug("connect timeout")
                self.handle_connect(True)

    def handle_read(self, ssock, data):
        pass

    def handle_write(self, ssock):
        if self._step == STEP_TERMINATE:
            return
        if ssock == self._target:
            if self._step == STEP_CONNECT:
                self._clear_connect_wait()
                self.handle_connect(ssock.has_error())

    def address_complete(self, hostname, ip):
        if self._step == STEP_TERMINATE:
            return

        self._clear_address_wait()

        if not ip:
            logging.debug("dns error: %s", hostname)
            self.handle_connect(True)
            return

        sock, sa = get_sock_byaddr(ip, self._target_addr[1])
        if not sock:
            logging.error('addr error: %s:%d' % self._target_addr)
            self.handle_connect(True)
            return

        sock.setblocking(False)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self._target.attach(sock, STATUS_WRITE)
        self._connect_wait = time.time() + TIMEOUT_OF_ACTION
        self._controller._loop.add_timer(self.connect_timeout)
        try:
            sock.connect(sa)
        except (OSError, IOError) as e:
            if errno_at_exc(e) == errno.EINPROGRESS:
                pass
            else:
                logging.error("connect: %s, e")

    def address_timeout(self):
        if self._step == STEP_TERMINATE:
            return

        if self._step == STEP_CONNECT:
            if time.time() >= self._address_wait:
                logging.debug("dns timeout")
                self.handle_connect(True)


class TCPController(LoopHandler):

    def __init__(self, options, service):
        self._loop = None
        self._dnsc = None
        self._options = options
        self._service = service

        sock, sa = get_sock_byaddr(options.bind_addr, options.bind_port)
        if not sock:
            raise Exception('bind addr error: %s:%d' %
                            (options.bind_addr, options.bind_port))

        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(sa)
        sock.setblocking(False)
        sock.listen(1024)
        logging.debug("TCP listen %s:%d" % sa)

        self._sock = sock
        self._closed = False
        self._services = {}

    def bind(self, loop, dnsc):
        self._loop = loop
        self._dnsc = dnsc
        self._loop.add(self._sock, POLL_IN | POLL_ERR, self)
        self._loop.add_timer(self.handle_timer)

    def _close(self):
        if self._loop:
            self._loop.remove_timer(self.handle_timer)
            self._loop.remove(self._sock)

        self._sock.close()
        self._sock = None

    def handle_event(self, sock, fd, event):
        if event & POLL_ERR:
            raise Exception('event error')
        try:
            conn = self._sock.accept()
            self._service(self, conn, self._options)
        except (OSError, IOError) as e:
            if errno_at_exc(e) in \
               (errno.EAGAIN, errno.EINPROGRESS, errno.EWOULDBLOCK):
                return
            else:
                logging.error('accept: %s', e)

    def handle_timer(self):
        if self._closed:
            if not self._sock:
                self._close()
                logging.info('TCP close completed')
            if not self._services:
                logging.info('stopping')
                self._loop.stop()

    def close(self, delay=False):
        logging.debug('TCP close')
        self._closed = True
        if delay:
            return
        self._close()
        for service in list(self._services.values()):
            service.terminate()

################################################


class RemoteService(TCPService):

    def __init__(self, controller, conn, options):
        self._secret = make_secret(options.algorithm, options.secret)
        super(RemoteService, self).__init__(controller, conn, options)

    def handle_read(self, ssock, data):
        if self._step == STEP_TERMINATE:
            return

        if ssock == self._source:
            if self._step == STEP_INIT:
                size = len(data)
                if size < 7 or f4str(data[:3]) != "GET":
                    raise Exception("http header")
                raw = data.find("\r\n\r\n")
                if raw < 0 or raw + 4 >= size:
                    raise Exception("http package")

                data = self._secret.decrypt(data[raw + 4:])

                size = len(data)
                if size < 7 or ord(data[0]) != 0x05 or ord(data[2]) != 0x00:
                    raise Exception("socks5 header")

                cmd = ord(data[1])
                if cmd != 1:  # CONNECT
                    raise Exception("socks5 command")

                atyp = ord(data[3])
                if atyp == 1:  # IPV4
                    apos = 4
                    ppos = apos + 4
                    rear = ppos + 2
                elif atyp == 3:  # Domain
                    apos = 5
                    ppos = apos + ord(data[4])
                    rear = ppos + 2
                elif atype == 4:  # IPV6
                    apos = 4
                    ppos = apos + 16
                    rear = ppos + 2
                else:
                    raise Exception("socks5 address")
                if rear != size:
                    raise Exception("socks5 request size")

                raw_addr = data[apos:ppos]
                if atyp == 3:
                    raw_addr = str(raw_addr)
                else:
                    raw_addr = socket.inet_ntoa(bytes(raw_addr))

                self._source.set_status(STATUS_WRITE)
                self.connect(raw_addr, struct.unpack('>H', data[ppos:rear])[0])

            elif self._step == STEP_TRANSPORT:
                self._target.send(self._secret.decrypt(data))

        elif ssock == self._target:
            if self._step == STEP_TRANSPORT:
                self._source.send(self._secret.encrypt(data))

    def handle_connect(self, error):
        if error:
            self._source.send(self._secret.encrypt(b'\x05\x04\00'))
            self.terminate()
            return

        self._step = STEP_TRANSPORT
        self._source.send(self._secret.encrypt(b'\x05\00\00'))
        self._source.set_status(STATUS_READWRITE)
        self._target.set_status(STATUS_READWRITE)


PROTOCOL_NONE = 0
PROTOCOL_SOCKS4 = 1
PROTOCOL_SOCKS4A = 2
PROTOCOL_SOCKS5 = 3
PROTOCOL_CONNECT = 4
PROTOCOL_PROXY = 5


def split_host(host):
    pos = host.rfind(":")
    if pos < 1 or pos >= len(host) - 1:
        return (host, 0)
    else:
        return (host[:pos], int(host[pos + 1:]))


class LocalService(TCPService):

    def __init__(self, controller, conn, options):
        self._protocol = PROTOCOL_NONE
        self._data_to_cache = None
        self._socks5_request = None
        self._remote_addr = options.remote_addr
        self._remote_port = options.remote_port
        self._secret = make_secret(options.algorithm, options.secret)
        super(LocalService, self).__init__(controller, conn, options)

    def handle_read(self, ssock, data):
        if self._step == STEP_TERMINATE:
            return

        if ssock == self._source:
            size = len(data)
            if self._step == STEP_INIT:
                ver = ord(data[0])
                # socks5
                if ver == 0x05:
                    if size < 3:
                        raise Exception("socks5 format")
                    self._protocol = PROTOCOL_SOCKS5
                    self._step = STEP_ADDRESS
                    self._source.send(b'\x05\00')

                # socks4
                elif ver == 0x04:
                    if size < 9 or ord(data[size - 1]) != 0x0:
                        raise Exception("socks4 format")
                    if ord(data[1]) != 1:  # CONNECT
                        raise Exception("socks4 command")
                    atyp = None
                    self._data_to_cache = data[2:8]
                    # socks4a
                    if ord(data[4]) == 0 and ord(data[5]) == 0 and ord(data[6]) == 0:
                        pos = 8
                        hhead = False
                        while pos < size:
                            pos = pos + 1
                            if ord(data[pos - 1]) == 0x00:
                                hhead = True
                                break
                        if not hhead or pos + 1 >= size:
                            raise Exception("socks4a header")
                        atyp = 0x03
                        addr = str(data[pos:size - 1])
                        self._protocol = PROTOCOL_SOCKS4A

                    else:
                        atyp = 0x01
                        addr = socket.inet_ntoa(data[4:8])
                        self._protocol = PROTOCOL_SOCKS4

                    self._socks5_request = b'\x05\01\00' + chr(atyp)
                    if atyp == 0x03:
                        self._socks5_request += chr(len(addr)) + addr
                    else:
                        self._socks5_request += socket.inet_aton(addr)

                    self._socks5_request += data[2:4]
                    self._source.set_status(STATUS_WRITE)
                    self.connect(self._remote_addr, self._remote_port)

                elif size > 24 and str(data[:8]) == "CONNECT ":
                    pos = data.find(" HTTP/1.1", 8)
                    if pos < 0:
                        raise Exception("connect header")
                    host = data[8:pos]
                    addr, port = split_host(host)
                    if port < 1:
                        raise Exception("connect host:port")

                    self._protocol = PROTOCOL_CONNECT
                    self._socks5_request = b'\x05\01\00\03' + \
                                           chr(len(addr)) + addr + \
                                           struct.pack('>H', port)
                    self._source.set_status(STATUS_WRITE)
                    self.connect(self._remote_addr, self._remote_port)

                elif size > 16:
                    pos = data.find(" HTTP/1.1")
                    if pos < 1:
                        raise Exception("proxy header")
                    head = data[:pos]
                    pos = head.find(" http://")
                    if pos > 0:
                        method = head[:pos]
                        pos += 8
                        port = 80
                    else:
                        pos = line.find(" https://")
                        if pos > 0:
                            method = head[:pos]
                            pos += 9
                            port = 443
                    if pos < 1:
                        raise Exception("proxy method")
                    epos = head.find("/", pos)
                    if epos < 1:
                        raise Exception("proxy path")
                    host = data[pos: epos]
                    addr, _port = split_host(host)
                    if _port > 0:
                        port = _port

                    self._protocol = PROTOCOL_PROXY
                    self._socks5_request = b'\x05\01\00\03' + \
                                           chr(len(addr)) + addr + \
                                           struct.pack('>H', port)
                    self._data_to_cache = method + " " + data[epos:]
                    self._source.set_status(STATUS_WRITE)
                    self.connect(self._remote_addr, self._remote_port)

                else:
                    raise Exception("proxy prototal")

            elif self._step == STEP_ADDRESS:
                if size < 7 or ord(data[0]) != 0x05:
                    raise Exception("socks5 header")

                self._data_to_cache = data[3:]
                self._socks5_request = data
                self._source.set_status(STATUS_WRITE)
                self.connect(self._remote_addr, self._remote_port)

            elif self._step == STEP_TRANSPORT:
                self._target.send(self._secret.encrypt(data))

        elif ssock == self._target:
            if self._step == STEP_RELAYING:
                data = self._secret.decrypt(data)
                size = len(data)
                if size < 3:
                    raise Exception("resp socks5 size")
                elif ord(data[0]) != 0x5:
                    raise Exception("resp socks5 version")
                elif ord(data[2]) != 0x0:
                    self._connect_error()
                else:
                    self._connect_success()

            elif self._step == STEP_TRANSPORT:
                self._source.send(self._secret.decrypt(data))

    def _connect_error(self):
        data = None
        if self._protocol in (PROTOCOL_SOCKS4, PROTOCOL_SOCKS4A):
            data = b'\x00\x5b' + self._data_to_cache
        elif self._protocol == PROTOCOL_SOCKS5:
            data = b'\x05\x04\00' + self._data_to_cache
        elif self._protocol in (PROTOCOL_CONNECT, PROTOCOL_PROXY):
            data = f4bytes("HTTP/1.1 407 Unauthorized\r\n\r\n")

        if data:
            self._source.send(data)

        self._data_to_cache = None
        self.terminate()

    def _connect_success(self):
        data = None
        if self._protocol in (PROTOCOL_SOCKS4, PROTOCOL_SOCKS4A):
            data = b'\x00\x5a' + self._data_to_cache
        elif self._protocol == PROTOCOL_SOCKS5:
            data = b'\x05\00\00' + self._data_to_cache
        elif self._protocol == PROTOCOL_CONNECT:
            data = f4bytes("HTTP/1.1 200 Connection Established\r\n\r\n")
        elif self._protocol == PROTOCOL_PROXY:
            self._target.send(self._secret.encrypt(self._data_to_cache))

        self._step = STEP_TRANSPORT
        if data:
            self._source.send(data)

        self._data_to_cache = None
        self._source.set_status(STATUS_READWRITE)
        self._target.set_status(STATUS_READWRITE)

    def handle_connect(self, error):
        if error:
            self._connect_error()
        else:
            data = f4bytes("GET / HTTP 1.1" +
                           "\r\nAccept: */*" +
                           "\r\n\r\n")
            self._step = STEP_RELAYING
            self._target.send(data +
                              self._secret.encrypt(self._socks5_request))
            self._socks5_request = None
            self._target.set_status(STATUS_READ, ACTION_ADD)


################################################


def main(options):
    logging.debug("Local ip: %s", get_local_ip())
    if options.role == "local":
        relay = TCPController(options, LocalService)
    else:
        relay = TCPController(options, RemoteService)

    def run_worker():
        try:
            loop = EventLoop()
            dnsc = DNSController(options.dns_bufsize)

            dnsc.bind(loop)
            relay.bind(loop, dnsc)

            def sgint_handler(signum, _):
                sys.exit(1)

            def sigquit_handler(signum, _):
                logging.warn('received SIGQUIT, shutting down..')
                relay.close(delay=True)

            signal.signal(signal.SIGINT, sgint_handler)
            signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM),
                          sigquit_handler)

            loop.run()
        except Exception as e:
            logging.error("shutodwn on exception: %s", e)
            sys.exit(1)

    if options.workers < 2 or os.name != 'posix':
        run_worker()
    else:
        children = []
        is_child = False
        for i in range(options.workers):
            pid = os.fork()
            if pid == 0:
                logging.info('worker started')
                is_child = True
                break
            else:
                children.append(pid)

        if is_child:
            run_worker()
        else:
            def quit_handler(signum, _):
                for pid in children:
                    try:
                        os.kill(pid, signum)
                        os.waitpid(pid, 0)
                    except OSError:
                        pass

                sys.exit(0)

            signal.signal(signal.SIGTERM, quit_handler)
            signal.signal(signal.SIGQUIT, quit_handler)
            signal.signal(signal.SIGINT, quit_handler)

            relay.close()
            for pid in children:
                os.waitpid(pid, 0)


################################################
from optparse import *


def daemonize():
    try:
        pid = os.fork()
        if pid:
            sys.exit(0)
    except OSError as e:
        logging.error("fork #1: %s", e)
        sys.exit(1)

    os.setsid()
    os.chdir("/")
    os.umask(0)
    try:
        pid = os.fork()
        if pid:
            sys.exit(0)
    except OSError as e:
        logging.error("fork #2: %s", e)
        sys.exit(1)

    dnull = file("/dev/null", "rw")
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(dnull.fileno(), sys.stdin.fileno())
    os.dup2(dnull.fileno(), sys.stdout.fileno())
    os.dup2(dnull.fileno(), sys.stderr.fileno())


if __name__ == '__main__':
    parser = OptionParser(version="%prog " + VERSION)
    role_choices = ["remote", "local"]
    parser.add_option("-r", "--role",
                      type="choice", dest="role",
                      choices=role_choices,
                      help="server role: " + ", ".join(role_choices))
    parser.add_option("-b", "--bind-addr",
                      dest="bind_addr", default="0.0.0.0",
                      help="net address for bind")
    parser.add_option("-p", "--bind-port",
                      type="int", dest="bind_port", default="0",
                      help="net port for bind")
    algorithm_choices = ["fool"]
    parser.add_option("-m", "--algorithm",
                      type="choice", dest="algorithm", default="fool",
                      choices=algorithm_choices,
                      help="algorithm for transport: " + ", ".join(algorithm_choices) + " [default: %default]")
    parser.add_option("-s", "--secret",
                      dest="secret",
                      help="secret for transport")
    parser.add_option("-w", "--workers",
                      type="int", dest="workers", default=2,
                      help="start worker count (Unix/Linux) [default: %default]")
    parser.add_option("-B", "--bufsize",
                      type="int", dest="bufsize", default=16,
                      help="network buffer size (KB) [default: %default]")
    parser.add_option("-D", "--dns-bufsize",
                      type="int", dest="dns_bufsize", default=4,
                      help="DNS buffer size (KB) [default: %default]")
    parser.add_option("-d", "--daemon",
                      action="store_true", dest="daemon", default=False,
                      help="start as daemon process (Unix/Linux)")
    lgroup = OptionGroup(parser, "local server")
    lgroup.add_option("-R", "--remote-addr",
                      dest="remote_addr",
                      help="remote server net address")
    lgroup.add_option("-P", "--remote-port", default="0",
                      type="int", dest="remote_port",
                      help="remote server net port")
    parser.add_option_group(lgroup)
    (options, args) = parser.parse_args()

    if not options.secret:
        raise Exception("lost options: -s or --secret")
    if options.role == "local":
        if options.bind_port == 0:
            options.bind_port = DEFAULT_LOCAL_PORT

        if not options.remote_addr:
            raise Exception("lost options: -R or --remote_addr")
        if not options.remote_port:
            options.remote_port = DEFAULT_REMOTE_PORT

    elif options.role == "remote":
        if options.bind_port == 0:
            options.bind_port = DEFAULT_REMOTE_PORT

    if not options.daemon or os.name != "posix":
        main(options)
    else:
        daemonize()
        main(options)
