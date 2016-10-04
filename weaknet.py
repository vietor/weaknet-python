#!/usr/bin/env python

from __future__ import division, print_function, with_statement


VERSION = "1.7.9"

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
import random


def xord(s):
    if type(s) == int:
        return s
    return ord(s)


def xchr(d):
    if bytes == str:
        return chr(d)
    return bytes([d])


def xstr(s):
    if bytes != str:
        if type(s) == bytes:
            return s.decode('utf-8')
    return s


def xbytes(s):
    if bytes != str:
        if type(s) == str:
            return s.encode('utf-8')
    return s


def md5(text, *more):
    m = hashlib.md5()
    m.update(xbytes(text))
    if len(more) > 0:
        for v in more:
            m.update(xbytes(v))
    return m.digest()


def sha512(text, *more):
    m = hashlib.sha512()
    m.update(xbytes(text))
    if len(more) > 0:
        for v in more:
            m.update(xbytes(v))
    return m.digest()


def errno_at_exc(e):
    if hasattr(e, 'errno'):
        return e.errno
    elif e.args:
        return e.args[0]
    else:
        return None


def random_string(length):
    return os.urandom(length)


def random_word(n, m):
    length = random.randint(n, m)
    return ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for i in range(length))


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

TIMEOUT_OF_TIMER = 8
TIMEOUT_OF_ACTION = TIMEOUT_OF_TIMER + 3


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

BUFFER_FIRST_SIZE = 8192

from ctypes import c_char_p, c_int, c_ulong, c_long, byref, create_string_buffer, c_void_p, c_ulonglong


def find_library(possible_lib_names, search_symbol):
    import ctypes.util
    from ctypes import CDLL

    if type(possible_lib_names) not in (list, tuple):
        possible_lib_names = [possible_lib_names]

    lib_names = []
    for lib_name in possible_lib_names:
        lib_names.append(lib_name)
        lib_names.append('lib' + lib_name)

    paths = []
    for name in lib_names:
        if os.name == "nt":
            dllpaths = os.environ['PATH'].split(os.pathsep)
            dllpaths.insert(0, sys.path[0])
            dllpaths.insert(0, os.getcwd())
            for directory in dllpaths:
                fname = os.path.join(directory, name)
                if os.path.isfile(fname):
                    paths.append(fname)
                if fname.lower().endswith(".dll"):
                    continue
                fname = fname + ".dll"
                if os.path.isfile(fname):
                    paths.append(fname)
        else:
            path = ctypes.util.find_library(name)
            if path:
                paths.append(path)
    if not paths:
        import glob
        for name in lib_names:
            patterns = [
                '/usr/local/lib*/lib%s.*' % name,
                '/usr/lib*/lib%s.*' % name,
                'lib%s.*' % name,
                '%s.dll' % name]
            for pat in patterns:
                files = glob.glob(pat)
                if files:
                    paths.extend(files)
    for path in paths:
        try:
            lib = CDLL(path)
            if hasattr(lib, search_symbol):
                return lib
            else:
                logging.warn('can\'t find symbol %s in %s',
                             search_symbol, path)
        except Exception:
            pass
    return None

libcrypto = find_library(('crypto', 'eay32'), 'EVP_get_cipherbyname')
if libcrypto:
    libcrypto_buf_size = BUFFER_FIRST_SIZE
    libcrypto_buf = create_string_buffer(libcrypto_buf_size)
    libcrypto.EVP_get_cipherbyname.restype = c_void_p
    libcrypto.EVP_CIPHER_CTX_new.restype = c_void_p
    libcrypto.EVP_CipherInit_ex.argtypes = (c_void_p, c_void_p,
                                            c_char_p, c_char_p, c_char_p, c_int)
    libcrypto.EVP_CipherUpdate.argtypes = (c_void_p, c_void_p,
                                           c_void_p, c_char_p, c_int)
    libcrypto.EVP_CIPHER_CTX_cleanup.argtypes = (c_void_p,)
    libcrypto.EVP_CIPHER_CTX_free.argtypes = (c_void_p,)
    if hasattr(libcrypto, 'OpenSSL_add_all_ciphers'):
        libcrypto.OpenSSL_add_all_ciphers()


class OpenSSLCrypto(object):

    @staticmethod
    def find_cipher(cipher_name):
        cipher_name = xbytes(cipher_name)
        cipher = libcrypto.EVP_get_cipherbyname(cipher_name)
        if not cipher:
            func_name = xstr('EVP_' + cipher_name.replace('-', '_'))
            func_cipher = getattr(libcrypto, func_name, None)
            if func_cipher:
                func_cipher.restype = c_void_p
                cipher = func_cipher()

        return cipher

    def __init__(self, cipher_name, key, iv, op):
        self._ctx = None
        cipher = OpenSSLCrypto.find_cipher(cipher_name)
        if not cipher:
            raise Exception('cipher %s not found in libcrypto' % cipher_name)
        key_ptr = c_char_p(key)
        iv_ptr = c_char_p(iv)
        self._ctx = libcrypto.EVP_CIPHER_CTX_new()
        if not self._ctx:
            raise Exception('can not create cipher context')
        r = libcrypto.EVP_CipherInit_ex(self._ctx, cipher, None,
                                        key_ptr, iv_ptr, c_int(op))
        if not r:
            self.clean()
            raise Exception('can not initialize cipher context')

    def update(self, data):
        global libcrypto_buf, libcrypto_buf_size

        size = len(data)
        cipher_out_len = c_long(0)
        if libcrypto_buf_size < size:
            libcrypto_buf_size = int(size * 2.5)
            libcrypto_buf = create_string_buffer(libcrypto_buf_size)

        libcrypto.EVP_CipherUpdate(self._ctx, byref(libcrypto_buf),
                                   byref(cipher_out_len), c_char_p(data), size)
        return libcrypto_buf.raw[:cipher_out_len.value]

    def __del__(self):
        self.clean()

    def clean(self):
        if self._ctx:
            libcrypto.EVP_CIPHER_CTX_cleanup(self._ctx)
            libcrypto.EVP_CIPHER_CTX_free(self._ctx)


def Rrc4md5Crypto(alg, key, iv, op, key_as_bytes=0, d=None, salt=None,
                  i=1, padding=1):
    return OpenSSLCrypto(b'rc4', md5(key, iv), b'', op)


libsodium = find_library('sodium', 'crypto_stream_salsa20_xor_ic')
if libsodium:
    libsodium_buf_size = BUFFER_FIRST_SIZE
    libsodium_buf = create_string_buffer(libsodium_buf_size)
    libsodium.crypto_stream_salsa20_xor_ic.restype = c_int
    libsodium.crypto_stream_salsa20_xor_ic.argtypes = (c_void_p, c_char_p,
                                                       c_ulonglong,
                                                       c_char_p, c_ulonglong,
                                                       c_char_p)
    libsodium.crypto_stream_chacha20_xor_ic.restype = c_int
    libsodium.crypto_stream_chacha20_xor_ic.argtypes = (c_void_p, c_char_p,
                                                        c_ulonglong,
                                                        c_char_p, c_ulonglong,
                                                        c_char_p)
    libsodium.crypto_stream_chacha20_ietf_xor_ic.restype = c_int
    libsodium.crypto_stream_chacha20_ietf_xor_ic.argtypes = (c_void_p, c_char_p,
                                                             c_ulonglong,
                                                             c_char_p, c_ulong,
                                                             c_char_p)


class SodiumCrypto(object):

    def __init__(self, cipher_name, key, iv, op):
        self.key = key
        self.iv = iv
        self.key_ptr = c_char_p(key)
        self.iv_ptr = c_char_p(iv)
        self.nbytes = 0
        self.block_size = 64
        if cipher_name == 'salsa20':
            self.cipher = libsodium.crypto_stream_salsa20_xor_ic
        elif cipher_name == 'chacha20':
            self.cipher = libsodium.crypto_stream_chacha20_xor_ic
        elif cipher_name == 'chacha20-ietf':
            self.cipher = libsodium.crypto_stream_chacha20_ietf_xor_ic
        else:
            raise Exception('cipher %s not enabled in libsodium' % cipher_name)

    def update(self, data):
        global libsodium_buf, libsodium_buf_size

        size = len(data)
        padding = self.nbytes % self.block_size
        padding_size = padding + size
        if libsodium_buf_size < padding_size:
            libsodium_buf_size = int(padding_size * 2.5)
            libsodium_buf = create_string_buffer(libsodium_buf_size)

        if padding:
            data = (b'\0' * padding) + data

        self.cipher(byref(libsodium_buf), c_char_p(data), padding_size,
                    self.iv_ptr, int(self.nbytes / self.block_size), self.key_ptr)
        self.nbytes += size
        return libsodium_buf.raw[padding:padding_size]


import string
if hasattr(string, 'maketrans'):
    maketrans = string.maketrans
    translate = string.translate
else:
    maketrans = bytes.maketrans
    translate = bytes.translate


cached_tables = {}


def make_table(key):
    a, b = struct.unpack('<QQ', md5(key))
    table = maketrans(b'', b'')
    table = [table[i: i + 1] for i in range(len(table))]
    for i in range(1, 1024):
        table.sort(key=lambda x: int(a % (ord(x) + i)))
    return table


def init_table(key):
    if key not in cached_tables:
        encrypt_table = b''.join(make_table(key))
        decrypt_table = maketrans(encrypt_table, maketrans(b'', b''))
        cached_tables[key] = [encrypt_table, decrypt_table]
    return cached_tables[key]


class TableCipher(object):

    def __init__(self, cipher_name, key, iv, op):
        self._encrypt_table, self._decrypt_table = init_table(key)
        self._op = op

    def update(self, data):
        if self._op:
            return translate(data, self._encrypt_table)
        else:
            return translate(data, self._decrypt_table)

secret_cached_keys = {}
secret_method_supported = {
    'table': (0, 0, TableCipher)
}
if libcrypto:
    secret_method_supported.update({
        'aes-128-cfb': (16, 16, OpenSSLCrypto),
        'aes-192-cfb': (24, 16, OpenSSLCrypto),
        'aes-256-cfb': (32, 16, OpenSSLCrypto),
        'aes-128-ofb': (16, 16, OpenSSLCrypto),
        'aes-192-ofb': (24, 16, OpenSSLCrypto),
        'aes-256-ofb': (32, 16, OpenSSLCrypto),
        'bf-cfb': (16, 8, OpenSSLCrypto),
        'cast5-cfb': (16, 8, OpenSSLCrypto),
        'des-cfb': (8, 8, OpenSSLCrypto),
        'rc2-cfb': (16, 8, OpenSSLCrypto),
        'rc4': (16, 0, OpenSSLCrypto),
        'rc4-md5': (16, 16, Rrc4md5Crypto),
        'seed-cfb': (16, 16, OpenSSLCrypto),
    })
    for key, value in {
        'idea-cfb': (16, 8, OpenSSLCrypto),
        'aes-128-ctr': (16, 16, OpenSSLCrypto),
        'aes-192-ctr': (24, 16, OpenSSLCrypto),
        'aes-256-ctr': (32, 16, OpenSSLCrypto),
        'camellia-128-cfb': (16, 16, OpenSSLCrypto),
        'camellia-192-cfb': (24, 16, OpenSSLCrypto),
        'camellia-256-cfb': (32, 16, OpenSSLCrypto),
    }.items():
        if OpenSSLCrypto.find_cipher(key):
            secret_method_supported[key] = value

if libsodium:
    secret_method_supported.update({
        'salsa20': (32, 8, SodiumCrypto),
        'chacha20': (32, 8, SodiumCrypto),
        'chacha20-ietf': (32, 12, SodiumCrypto),
    })


def EVP_BytesToKey(password, key_len, iv_len):
    cached_key = '%s-%d-%d' % (password, key_len, iv_len)
    r = secret_cached_keys.get(cached_key, None)
    if r:
        return r
    m = []
    i = 0
    while len(b''.join(m)) < (key_len + iv_len):
        data = password
        if i > 0:
            data = m[i - 1] + password

        i += 1
        m.append(md5(data))

    ms = b''.join(m)
    key = ms[:key_len]
    iv = ms[key_len:key_len + iv_len]
    secret_cached_keys[cached_key] = (key, iv)
    return key, iv


class SecretEngine(object):

    def __init__(self, method, key):
        self.key = xbytes(key)
        self.method = method
        self.iv = None
        self.iv_sent = False
        self.cipher_iv = b''
        self.decipher = None
        self._method_info = secret_method_supported.get(method)
        if self._method_info:
            self.cipher = self._get_cipher(
                1, random_string(self._method_info[1])
            )
        else:
            logging.error('method %s not supported' % method)
            sys.exit(1)

    def _get_cipher(self, op, iv):
        m = self._method_info
        if m[0] > 0:
            key, iv_ = EVP_BytesToKey(self.key, m[0], m[1])
        else:
            key, iv = self.key, b''

        iv = iv[:m[1]]
        if op == 1:
            self.cipher_iv = iv[:m[1]]
        return m[2](self.method, key, iv, op)

    def encrypt(self, buf):
        if len(buf) == 0:
            return buf
        if self.iv_sent:
            return self.cipher.update(buf)
        else:
            self.iv_sent = True
            return self.cipher_iv + self.cipher.update(buf)

    def decrypt(self, buf):
        if len(buf) == 0:
            return buf
        if self.decipher is None:
            decipher_iv_len = self._method_info[1]
            decipher_iv = buf[:decipher_iv_len]
            self.decipher = self._get_cipher(0, iv=decipher_iv)
            buf = buf[decipher_iv_len:]
            if len(buf) == 0:
                return buf
        return self.decipher.update(buf)


################################################
import socket
import struct


QTYPE_ANY = 255
QTYPE_A = 1
QTYPE_AAAA = 28
QTYPE_CNAME = 5
QTYPE_NS = 2
QCLASS_IN = 1

STEP_INIT = 0
STEP_WAITHDR = 1
STEP_WAITDNS = 2
STEP_CONNECT = 3
STEP_TRANSPORT = 4
STEP_TERMINATE = -1

STATUS_INIT = 0
STATUS_READ = 1
STATUS_WRITE = 2
STATUS_READWRITE = STATUS_READ | STATUS_WRITE

ACTION_SET = 0
ACTION_ADD = 1
ACTION_DEL = 2

TRAFFIC_IDLE = 0
TRAFFIC_BLOCK = 1

CONNECT_SUCCESS = 0
CONNECT_BADDNS = 1
CONNECT_TIMEOUT = 2
CONNECT_BADSOCK = 3


def is_ip(address):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, xstr(address))
            return family
        except (TypeError, ValueError, OSError, IOError) as e:
            pass
    return False


def inet_ntop(family, ipstr):
    if family == socket.AF_INET:
        return xbytes(socket.inet_ntoa(ipstr))
    elif family == socket.AF_INET6:
        import re
        v6addr = ':'.join(('%02X%02X' % (ord(i), ord(j))).lstrip('0')
                          for i, j in zip(ipstr[::2], ipstr[1::2]))
        v6addr = re.sub('::+', '::', v6addr, count=1)
        return xbytes(v6addr)
    else:
        raise RuntimeError("What family?")


def inet_pton(family, addr):
    addr = xstr(addr)
    if family == socket.AF_INET:
        return socket.inet_aton(addr)
    elif family == socket.AF_INET6:
        if '.' in addr:  # a v4 addr
            v4addr = addr[addr.rindex(':') + 1:]
            v4addr = socket.inet_aton(v4addr)
            v4addr = map(lambda x: ('%02X' % ord(x)), v4addr)
            v4addr.insert(2, ':')
            newaddr = addr[:addr.rindex(':') + 1] + ''.join(v4addr)
            return inet_pton(family, newaddr)
        dbyts = [0] * 8  # 8 groups
        grps = addr.split(':')
        for i, v in enumerate(grps):
            if v:
                dbyts[i] = int(v, 16)
            else:
                for j, w in enumerate(grps[::-1]):
                    if w:
                        dbyts[7 - j] = int(w, 16)
                    else:
                        break
                break
        return b''.join((chr(i // 256) + chr(i % 256)) for i in dbyts)
    else:
        raise RuntimeError("What family?")


if not hasattr(socket, 'inet_pton'):
    socket.inet_pton = inet_pton
if not hasattr(socket, 'inet_ntop'):
    socket.inet_ntop = inet_ntop


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
    request_id = random_string(2)
    address = address.strip(b'.')
    labels = address.split(b'.')
    results = []
    for label in labels:
        l = len(label)
        if l > 63:
            raise Exception('dns address error')
        results.append(xchr(l))
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
    l = xord(data[p])
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

        l = xord(data[p])
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

    def __init__(self, bufsize):
        self._loop = None
        self._servers = []
        self._bufsize = bufsize * 1024
        self._cache = LRUCache(timeout=300)
        self._hostname_qtypes = {}
        self._hostname_callbacks = {}
        self._callback_hostnames = {}
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                   socket.SOL_UDP)
        self._sock.setblocking(False)

        try:
            with open('/etc/resolv.conf', 'rb') as f:
                content = f.readlines()
                for line in content:
                    line = line.strip()
                    if not line:
                        continue
                    if not line.startswith(b'nameserver'):
                        continue
                    parts = line.split()
                    if len(parts) < 2 \
                       or is_ip(parts[1]) != socket.AF_INET:
                        continue
                    self._servers.append(xstr(parts[1]))
        except IOError:
            pass
        if not self._servers:
            self._servers = ['8.8.4.4', '8.8.8.8']

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
        self._traffic = TRAFFIC_IDLE
        self._data_to_write = []
        self._nbytes_to_write = 0
        self._event_on_write = False

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
        if not self._event_on_write:
            self._write(data)
        else:
            self._cache(data)

    def close(self):
        if not self._sock:
            return
        self._loop.remove(self._sock)
        self._sock.close()
        self._sock = None

    def getsockname(self):
        return self._sock.getsockname()

    def getpeername(self):
        return self._sock.getpeername()

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
        self._set_status(status, action)

    def _set_status(self, status, action):
        update = self._status
        if action == ACTION_ADD:
            if update & status == status:
                return
            update |= status
        elif action == ACTION_DEL:
            if update & status == 0:
                return
            update &= (~status)
        else:
            if update == status:
                return
            update = status

        self._status = update
        self._loop.modify(self._sock, self._make_event(update))

    def _update_traffic(self, traffic):
        if self._traffic == traffic:
            return
        self._traffic = traffic
        self._service.handle_traffic(self, traffic)

    def _cache(self, data):
        self._data_to_write.append(data)
        self._nbytes_to_write += len(data)

    def _write(self, data):
        incomplete = False
        if self._nbytes_to_write > 0:
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

        if not incomplete:
            self._update_traffic(TRAFFIC_IDLE)
        else:
            self._cache(data)
            self._set_status(STATUS_WRITE, ACTION_ADD)
            self._update_traffic(TRAFFIC_BLOCK)

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
        self._event_on_write = True
        self._service.handle_write(self)
        self._event_on_write = False
        if not self._sock:
            return
        if self._nbytes_to_write > 0:
            data = b''.join(self._data_to_write)
            self._data_to_write = []
            self._nbytes_to_write = 0
            self._write(data)
        else:
            self._set_status(STATUS_WRITE, ACTION_DEL)

    def _on_event_error(self):
        if not self._sock:
            return
        logging.error("sock error: %s", get_sock_error(self._sock))
        self._service.terminate()


class NetAddr(object):
    __slots__ = ('host', 'port', 'ip')

    def __init__(self, host, port=None):
        if port is None:
            self.host = host[0]
            self.port = host[1]
        else:
            self.host = host
            self.port = port

        self.ip = self.host

    def __str__(self):
        if self.host == self.ip:
            return '{0}:{1}'.format(self.host, self.port)
        else:
            return '{0}({1}):{2}'.format(self.host, self.ip, self.port)

    def set_ip(self, ip):
        self.ip = ip


class TCPService(object):

    def __init__(self, controller, conn, options):
        self._controller = controller
        self._step = STEP_INIT
        self._controller._services[id(self)] = self
        self._source = TCPServiceSocket(controller._loop, self,
                                        options.bufsize)
        self._source_addr = NetAddr(conn[1])
        self._target = TCPServiceSocket(controller._loop, self,
                                        options.bufsize)
        self._target_addr = None
        self._address_wait = 0
        self._connect_wait = 0

        sock = conn[0]
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self._source.attach(sock)
        self._controller._loop.add_timer(self.handle_timer)

    def terminate(self):
        if self._step == STEP_TERMINATE:
            return
        self._step = STEP_TERMINATE
        self._controller._loop.remove_timer(self.handle_timer)
        if self._source:
            self._source.close()
            self._source = None
        if self._target:
            self._target.close()
            self._target = None

        del self._controller._services[id(self)]

    def connect(self, addr, port):
        self._step = STEP_WAITDNS
        self._address_wait = time.time() + TIMEOUT_OF_ACTION
        self._target_addr = NetAddr(addr, port)
        self._controller._dnsc.register(self.address_complete, addr)

    def handle_timer(self):
        if self._step == STEP_TERMINATE:
            return
        if self._step == STEP_WAITDNS:
            if self._address_wait > 0 and time.time() >= self._address_wait:
                logging.debug("dns timeout %s", self._target_addr)
                self.handle_connect(CONNECT_TIMEOUT)
        elif self._step == STEP_CONNECT:
            if self._connect_wait > 0 and time.time() >= self._connect_wait:
                logging.debug("connect timeout %s", self._target_addr)
                self.handle_connect(CONNECT_TIMEOUT)

    def handle_connect(self, code):
        pass

    def handle_traffic(self, ssock, traffic):
        if traffic == TRAFFIC_BLOCK:
            if ssock == self._source:
                self._target.set_status(STATUS_READ, ACTION_DEL)
            elif ssock == self._target:
                self._source.set_status(STATUS_READ, ACTION_DEL)
        elif traffic == TRAFFIC_IDLE:
            if ssock == self._source:
                self._target.set_status(STATUS_READ, ACTION_ADD)
            elif ssock == self._target:
                self._source.set_status(STATUS_READ, ACTION_ADD)

    def handle_read(self, ssock, data):
        pass

    def handle_write(self, ssock):
        if self._step == STEP_TERMINATE:
            return
        if ssock == self._target:
            if self._step == STEP_CONNECT:
                self._connect_wait = 0
                if ssock.has_error():
                    code = CONNECT_BADSOCK
                else:
                    code = CONNECT_SUCCESS

                self.handle_connect(code)

    def address_complete(self, hostname, ip):
        if self._step == STEP_TERMINATE:
            return
        self._address_wait = 0
        self._step = STEP_CONNECT
        if not ip:
            logging.debug("dns bad: %s", hostname)
            self.handle_connect(CONNECT_BADDNS)
            return
        self._target_addr.set_ip(ip)
        sock, sa = get_sock_byaddr(ip, self._target_addr.port)
        if not sock:
            logging.error('addr bad: %s', self._target_addr)
            self.handle_connect(CONNECT_BADDNS)
            return
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        self._target.attach(sock, STATUS_WRITE)
        self._connect_wait = time.time() + TIMEOUT_OF_ACTION
        try:
            sock.connect(sa)
        except (OSError, IOError) as e:
            if errno_at_exc(e) == errno.EINPROGRESS:
                pass


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
import base64

HTTP_HASBODY = ("POST")
HTTP_METHODS = ("HEAD", "GET", "POST")


def make_http_request():
    method = HTTP_METHODS[random.randint(1, len(HTTP_METHODS)) - 1]
    title = method + " /" + random_word(1, 8) + " HTTP/1.1"
    if method not in HTTP_HASBODY:
        data = title \
            + "\r\nAccept: */*"
    else:
        size = random.randint(30, 100) * 1024 * 1024
        data = title \
            + "\r\nContent-Length: " + str(size) \
            + "\r\nContent-Type: application/octet-stream"

    return data + "\r\n\r\n"


class MiniHttpRequest(object):
    __slots__ = ('method', 'path', 'version',
                 '_headers', '_header_ks', 'length')

    def __init__(self):
        self._headers = {}
        self._header_ks = {}

    def __str__(self):
        lines = []
        lines.append(self.method + " " + self.path + " " + self.version)
        for key, value in self._headers.items():
            lines.append(self._header_ks[key] + ": " + value)
        return "\r\n".join(lines) + "\r\n\r\n"

    def add_header(self, key, value):
        lkey = key.lower()
        self._headers[lkey] = value
        self._header_ks[lkey] = key

    def remove_header(self, key):
        lkey = key.lower()
        if lkey in self._header_ks:
            del self._headers[lkey]
            del self._header_ks[lkey]

    def makeBytes(self, data):
        if data:
            return xbytes(self.__str__())
        else:
            return xbytes(self.__str__()) + data


def parse_http_request(data, size):
    request = MiniHttpRequest()
    pos = data.find(b" ", 0, 8)
    if pos < 1:
        raise Exception("http method")
    request.method = xstr(data[:pos])
    last = pos + 1
    pos = data.find(b" HTTP/1.", last)
    if pos < 1 or pos + 9 >= size:
        raise Exception("http version")
    request.path = xstr(data[last: pos])
    last = pos + 1
    rear = data.find(b"\r\n\r\n", pos + 9)
    if rear < 1:
        raise Exception("http headers")
    request.length = rear + 4
    pos = data.find(b"\r\n", last + 8, rear)
    if pos < 0:
        pos = rear
    elif pos < 1 or pos + 2 >= size:
        raise Exception("http version")
    request.version = xstr(data[last: pos])
    last = pos + 2
    if last < rear:
        for line in xstr(data[last: rear]).split("\r\n"):
            pos = line.find(":")
            if pos > 0:
                request.add_header(line[:pos], line[pos + 1:].lstrip())
    return request


class RemoteService(TCPService):

    def __init__(self, controller, conn, options):
        self._data_to_cache = []
        self._secret = SecretEngine(options.algorithm, options.secret)
        super(RemoteService, self).__init__(controller, conn, options)

    def handle_read(self, ssock, data):
        if self._step == STEP_TERMINATE:
            return

        if ssock == self._source:
            if self._step == STEP_TRANSPORT:
                self._target.send(self._secret.decrypt(data))

            elif self._step == STEP_INIT:
                try:
                    request = parse_http_request(data, len(data))
                    data = data[request.length:]
                except:
                    pass
                data = self._secret.decrypt(data)
                if not data:
                    raise Exception("proxy secret #1")
                size = len(data)
                if size < 2:
                    raise Exception("proxy secret #2")
                atyp = xord(data[0])
                if atyp == 1:  # IPV4
                    apos = 1
                    ppos = apos + 4
                    rear = ppos + 2
                elif atyp == 3:  # Domain
                    apos = 2
                    ppos = apos + xord(data[1])
                    rear = ppos + 2
                elif atyp == 4:  # IPV6
                    apos = 1
                    ppos = apos + 16
                    rear = ppos + 2
                else:
                    raise Exception("proxy secret #3")
                if rear < size:
                    self._data_to_cache.append(data[rear:])

                addr = data[apos:ppos]
                port = struct.unpack('>H', data[ppos:rear])[0]
                if atyp != 3:
                    addr = socket.inet_ntoa(addr)

                self._source.set_status(STATUS_READWRITE)
                self.connect(addr, port)

            elif self._step == STEP_WAITDNS or self._step == STEP_CONNECT:
                self._data_to_cache.append(self._secret.decrypt(data))

        elif ssock == self._target:
            if self._step == STEP_TRANSPORT:
                self._source.send(self._secret.encrypt(data))

    def handle_connect(self, code):
        if code != CONNECT_SUCCESS:
            self.terminate()
        else:
            self._step = STEP_TRANSPORT
            if len(self._data_to_cache) > 0:
                self._target.send(b''.join(self._data_to_cache))
                self._data_to_cache = []

            self._target.set_status(STATUS_READWRITE)


PROTOCOL_NONE = 0
PROTOCOL_SOCKS4 = 1
PROTOCOL_SOCKS4A = 2
PROTOCOL_SOCKS5 = 3
PROTOCOL_CONNECT = 4
PROTOCOL_PROXY = 5
PROTOCOL_WEBFILE = 6


def split_host(host):
    pos = host.rfind(":")
    if pos < 1 or pos >= len(host) - 1:
        return (host, 0)
    else:
        return (host[:pos], int(host[pos + 1:]))


def make_socks5_addr(atyp, addr, port):
    data = xchr(atyp)
    if atyp == 0x03:
        data += xchr(len(addr)) + xbytes(addr)
    else:
        data += socket.inet_aton(addr)
    if type(port) != int:
        return data + port
    else:
        return data + struct.pack(">H", port)

PACFILE_TOP = """
var proxyDirect = "DIRECT";
var proxyActive = "PROXY {0}:{1}";
var proxyRules = [
"""
PACFILE_BOTTOM = """
];

var T_HOST = 0, T_PATH = 1, T_URL = 2;
var E_EQ = 0, E_EL = 1, E_ER = 2, E_IN = 3, E_RE = 4;

function reWapper(str) {
    return str.replace(/\//g, "\\\\/")
        .replace(/\./g, "\\\\.")
        .replace(/\*/g, ".*");
}

function execTextEQ(str, text) {
    return str == text;
}

function execTextEL(str, text) {
    var len1 = str.length;
    var len2 = text.length;
    return len1 <= len2 && text.substring(0, len1) == str;
}

function execTextER(str, text) {
    var len1 = str.length;
    var len2 = text.length;
    return len1 <= len2 && text.substring(len2 - len1) == str;
}

function execTextIN(str, text) {
    return text.indexOf(str) >= 0;
}

function execTextRE(str, text) {
    return (new RegExp(str)).test(text);
}

function testRule(rules, host, path, url) {
    for(var i = 0; i< rules.length; ++i) {
        var text;
        var rule = rules[i];
        if(rule.t == T_HOST)
            text = host;
        else if(rule.t == T_PATH)
            text = path;
        else if(rule.t == T_URL)
            text = url;
        if(text) {
            var succ = false;
            if(rule.e == E_EQ)
                succ = execTextEQ(rule.s, text);
            else if(rule.e == E_EL)
                succ = execTextEL(rule.s, text);
            else if(rule.e == E_ER)
                succ = execTextER(rule.s, text);
            else if(rule.e == E_IN)
                succ = execTextIN(rule.s, text);
            else if(rule.e == E_RE)
                succ = execTextRE(rule.s, text);
            if(succ)
                return true;
        }
    }
    return false;
}

function wrapRule(rule, str) {
    if(rule.e == E_RE || str.indexOf("*") < 0)
        rule.s = str;
    else {
        if(rule.e == E_EQ)
            rule.s = "^" + reWapper(str) + "$";
        else if(rule.e == E_EL)
            rule.s = "^" + reWapper(str);
        else if(rule.e == E_ER)
            rule.s = reWapper(str) + "$";
        else
            rule.s = reWapper(str);
        rule.e = E_RE;
    }
    return rule;
}

function parseRule(rules, rule) {
    if(rule.substring(0, 2) == "||") {
        rule = rule.substring(2);
        if(rule) {
            if(rule.indexOf("/") < 0) {
                if(rule.length > 1 && rule.charAt(0) == ".")
                    rules.push(wrapRule({t: T_HOST, e: E_EQ}, rule.substring(1)));
                rules.push(wrapRule({t: T_HOST, e: E_ER}, rule));
            }
            else {
                if(rule.length > 1 && rule.charAt(0) == ".")
                    rules.push(wrapRule({t: T_PATH, e: E_IN}, "://" + rule.substring(1)));
                rules.push({t: T_PATH, e: E_IN, re: reWapper(rule)});
            }
        }
    }
    else if(rule.charAt(0) == "|") {
        rule = rule.substring(1);
        if(rule)
            rules.push(wrapRule({t: T_PATH, e: E_EL}, rule));
    }
    else if(rule.length < 2)
        rules.push(wrapRule({t: T_URL, e: E_IN}, rule));
    else if(rule.charAt(0) == "/" && rule.charAt(rule.length - 1) == "/")
        rules.push(wrapRule({t: T_URL, e: E_RE}, rule.substring(1, rule.length - 1)));
    else
        rules.push(wrapRule({t: T_URL, e: E_IN}, rule));
}

var ruleInclude = [];
var ruleExclude = [];
for(var i = 0; i< proxyRules.length; ++i) {
    var rule = proxyRules[i].trim();
    if(rule && rule.charAt(0) != "!" && rule.charAt(0) != "[") {
        if(rule.substring(0, 2) != "@@")
            parseRule(ruleInclude, rule);
        else {
            rule = rule.substring(2);
            if(rule)
                parseRule(ruleExclude, rule);
        }
    }
}
proxyRules = [];

function proxyMatch(host, path, url) {
    var proxy = ruleInclude.length < 1 || testRule(ruleInclude, host, path, url);
    if(proxy)
        proxy = !testRule(ruleExclude, host, path, url);
    return proxy;
}

function FindProxyForURL(url, host) {
    var path = null;
    if(url) {
        var hpos = url.indexOf("://");
        if(hpos < 0)
            path = url;
        else {
            hpos += 3;
            if(!host) {
                pos = url.indexOf("/", hpos);
                if(pos < 0)
                    host = url.substring(hpos);
                else
                    host = url.substring(hpos, pos);
            }
            pos = url.indexOf("?", hpos);
            if(pos < 0)
                path = url;
            else
                path = url.substring(0, pos);
        }
    }
    if(!proxyMatch(host, path, url))
        return proxyDirect;
    else
        return proxyActive;
}
"""


class LocalService(TCPService):

    def __init__(self, controller, conn, options):
        self._protocol = PROTOCOL_NONE
        self._protocol_data = None
        self._socks5_addr = None
        self._data_to_cache = None
        self._rulelist = options.rulelist
        self._remote_addr = options.remote_addr
        self._remote_port = options.remote_port
        self._shadowsocks = options.shadowsocks
        self._secret = SecretEngine(options.algorithm, options.secret)
        super(LocalService, self).__init__(controller, conn, options)

    def handle_read(self, ssock, data):
        if self._step == STEP_TERMINATE:
            return

        if ssock == self._source:
            if self._step == STEP_TRANSPORT:
                self._target.send(self._secret.encrypt(data))

            elif self._step == STEP_INIT:
                size = len(data)
                ver = xord(data[0])
                # socks5
                if ver == 0x05:
                    if size < 3:
                        raise Exception("socks5 format")
                    self._protocol = PROTOCOL_SOCKS5
                    self._step = STEP_WAITHDR
                    self._source.send(b'\x05\00')

                # socks4
                elif ver == 0x04:
                    if size < 9 or xord(data[size - 1]) != 0x0:
                        raise Exception("socks4 format")
                    if xord(data[1]) != 1:  # CONNECT
                        raise Exception("socks4 command")
                    pos = 7
                    found = False
                    while pos < size:
                        if xord(data[pos]) == 0x00:
                            found = True
                            break
                        pos = pos + 1
                    if not found:
                        raise Exception("socks4 userid")
                    rear = pos + 1
                    # socks4a
                    if xord(data[4]) == 0 and xord(data[5]) == 0 and xord(data[6]) == 0:
                        pos = rear
                        found = False
                        while pos < size:
                            if xord(data[pos]) == 0x00:
                                found = True
                                break
                            pos = pos + 1
                        if not found:
                            raise Exception("socks4a hosthame")
                        atyp = 0x03
                        addr = xstr(data[rear:pos])
                        self._protocol = PROTOCOL_SOCKS4A
                        rear = pos + 1

                    else:
                        atyp = 0x01
                        addr = socket.inet_ntoa(data[4:8])
                        self._protocol = PROTOCOL_SOCKS4

                    if rear < size:
                        self._data_to_cache = data[rear:]

                    self._socks5_addr = make_socks5_addr(
                        atyp, addr, data[2:4])
                    self._source.set_status(STATUS_WRITE)
                    self.connect(self._remote_addr, self._remote_port)

                else:
                    try:
                        request = parse_http_request(data, size)
                    except:
                        self._step = STEP_WAITHDR
                        self._protocol_data = data
                    else:
                        self._process_http_proxy(request, data)

            elif self._step == STEP_WAITHDR:
                if self._protocol == PROTOCOL_SOCKS5:
                    size = len(data)
                    if size < 7 or xord(data[0]) != 0x05:
                        raise Exception("socks5 header")
                    if xord(data[1]) != 1:  # CONNECT
                        raise Exception("socks5 command")
                    atyp = xord(data[3])
                    if atyp == 0x01:
                        rear = 10
                    elif atyp == 0x03:
                        rear = 7 + xord(data[4])
                    elif atyp == 0x04:
                        rear = 22
                    else:
                        raise Exception("socks5 address")
                    if rear > size:
                        raise Exception("socks5 length")
                    if rear == size:
                        self._socks5_addr = data[3:]
                    else:
                        self._socks5_addr = data[3:rear]
                        self._data_to_cache = data[rear:]

                    self._source.set_status(STATUS_WRITE)
                    self.connect(self._remote_addr, self._remote_port)

                else:
                    try:
                        datax = self._protocol_data + data
                        self._protocol_data = None
                        request = parse_http_request(datax, len(datax))
                    except:
                        self._protocol_data = datax
                    else:
                        self._process_http_proxy(request, datax)

        elif ssock == self._target:
            if self._step == STEP_TRANSPORT:
                self._source.send(self._secret.decrypt(data))

    def _process_http_proxy(self, request, data):
        if request.method == "CONNECT":
            addr, port = split_host(request.path)
            if port < 1:
                raise Exception("connect host:port")
            self._protocol = PROTOCOL_CONNECT
            self._protocol_data = request.version

        elif request.path.startswith("/"):
            self._protocol = PROTOCOL_WEBFILE

        else:
            pos = request.path.find("://", 0, 8)
            if pos < 1 or request.path[:pos].lower() != "http":
                raise Exception("proxy path #1")
            pos = request.path.find("/", 8)
            if pos < 1:
                raise Exception("proxy path #2")
            addr, _port = split_host(request.path[7: pos])
            if _port > 0:
                port = _port
            else:
                port = 80

            request.path = request.path[pos:]
            request.add_header("Connection", "close")
            request.remove_header("Proxy-Connection")
            self._protocol = PROTOCOL_PROXY
            self._data_to_cache = request.makeBytes(
                data[request.length:])

        if self._protocol != PROTOCOL_WEBFILE:
            self._socks5_addr = make_socks5_addr(
                0x03, addr, port)
            self._source.set_status(STATUS_WRITE)
            self.connect(self._remote_addr, self._remote_port)

        else:
            if request.path != "/proxy.pac":
                data = xbytes(request.version + " 404 Not Found"
                              + "\r\nConnection: close"
                              + "\r\n\r\n")
            else:
                laddr = self._source.getsockname()
                filedata = PACFILE_TOP.format(laddr[0], laddr[1]) \
                    + self._rulelist + PACFILE_BOTTOM
                filedata = xbytes(filedata)
                netheader = request.version + " 200 OK" \
                    + "\r\nConnection: close" \
                    + "\r\nContent-Type: application/octet-stream" \
                    + "\r\nContent-Length: " + str(len(filedata)) \
                    + "\r\n\r\n"
                data = xbytes(netheader) + filedata

            self._source.send(data)

    def _connect_error(self):
        data = None
        if self._protocol in (PROTOCOL_SOCKS4, PROTOCOL_SOCKS4A):
            data = b'\x00\x5b\x00\x00\x00\x00\x10\x10'
        elif self._protocol == PROTOCOL_SOCKS5:
            data = b'\x05\x04\00\x01\x00\x00\x00\x00\x10\x10'
        elif self._protocol == PROTOCOL_CONNECT:
            data = xbytes(self._protocol_data +
                          " 407 Unauthorized\r\n\r\n")

        if data:
            self._source.send(data)

        self.terminate()

    def _connect_success(self):
        data = None
        if self._protocol in (PROTOCOL_SOCKS4, PROTOCOL_SOCKS4A):
            data = b'\x00\x5a\x00\x00\x00\x00\x10\x10'
        elif self._protocol == PROTOCOL_SOCKS5:
            data = b'\x05\x00\x00\x01\x00\x00\x00\x00\x10\x10'
        elif self._protocol == PROTOCOL_CONNECT:
            data = xbytes(self._protocol_data +
                          " 200 Connection Established\r\n\r\n")

        if data:
            self._source.send(data)

        self._step = STEP_TRANSPORT
        self._source.set_status(STATUS_READWRITE)

    def handle_connect(self, code):
        if code != CONNECT_SUCCESS:
            self._connect_error()
        else:
            data = self._socks5_addr
            if self._data_to_cache:
                data += self._data_to_cache
                self._data_to_cache = None

            data = self._secret.encrypt(data)
            self._socks5_addr = None
            if self._shadowsocks:
                request = data
            else:
                request = xbytes(make_http_request()) + data

            self._target.send(request)
            self._target.set_status(STATUS_READWRITE)
            self._connect_success()


################################################


def execute(options):
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
            logging.error("shutdown on exception: %s", e)
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

    rnull = open("/dev/null", "r")
    wnull = open("/dev/null", "w")
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(rnull.fileno(), sys.stdin.fileno())
    os.dup2(wnull.fileno(), sys.stdout.fileno())
    os.dup2(wnull.fileno(), sys.stderr.fileno())


def direct_main():
    algorithmes = sorted(secret_method_supported.keys())
    parser = OptionParser("%prog [options]", version=VERSION,
                          description="Tiny safety network proxy tool")
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
    parser.add_option("-m", "--algorithm",
                      type="choice", dest="algorithm", default="table",
                      choices=algorithmes,
                      help="algorithm for transport: " + ", ".join(algorithmes) + " [default: %default]")
    parser.add_option("-s", "--secret",
                      dest="secret",
                      help="secret for transport")
    parser.add_option("-w", "--workers",
                      type="int", dest="workers", default=2,
                      help="start worker count (Unix/Linux) [default: %default]")
    parser.add_option("-B", "--bufsize",
                      type="int", dest="bufsize", default=32,
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
    lgroup.add_option("-S", "--shadowsocks",
                      action="store_true", dest="shadowsocks", default=False,
                      help="usage shadowsocks compatible mode")
    lgroup.add_option("-F", "--rulelist",
                      dest="rulelist",
                      help="file of proxy.pac rule list, encode by base64")
    parser.add_option_group(lgroup)

    if len(sys.argv) > 1:
        sys_argv = sys.argv
    else:
        sys_argv = [sys.argv[0], "--help"]

    (options, args) = parser.parse_args(sys_argv)

    if not options.secret:
        raise Exception("lost options: -s or --secret")
    if options.role == "local":
        if options.bind_port == 0:
            options.bind_port = DEFAULT_LOCAL_PORT

        if not options.remote_addr:
            raise Exception("lost options: -R or --remote_addr")
        if not options.remote_port:
            options.remote_port = DEFAULT_REMOTE_PORT

        rulelist = []
        if options.rulelist:
            try:
                with open(options.rulelist, 'r') as f:
                    data = f.read(-1).replace("\n", "")
                    for line in xstr(base64.b64decode(data)).split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith('#'):
                            continue
                        if line.startswith('!'):
                            continue
                        if line.startswith('['):
                            continue
                        line = line.replace("\\", "\\\\")
                        line = line.replace("/", "\\/")
                        rulelist.append(line)
            except IOError as e:
                pass

        options.rulelist = ""
        if len(rulelist) > 0:
            options.rulelist = "    \"" + ("\",\n    \"").join(rulelist) + "\""

    elif options.role == "remote":
        if options.bind_port == 0:
            options.bind_port = DEFAULT_REMOTE_PORT

    if not options.daemon or os.name != "posix":
        execute(options)
    else:
        daemonize()
        execute(options)


def main():
    try:
        direct_main()
    except Exception as e:
        print(e)

if __name__ == '__main__':
    main()
