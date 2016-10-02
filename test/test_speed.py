from __future__ import division, print_function, with_statement

import os
import sys

sys.path.append(os.path.abspath("../"))

import time
import random
import string
from weaknet import *


def randomBytes(size):
    return xbytes(''.join(random.choice(string.ascii_uppercase + string.digits + string.ascii_lowercase) for _ in range(size)))


def testAlgorithm(algorithm, secret, source):
    encrypt = make_secret(algorithm, secret).encrypt
    decrypt = make_secret(algorithm, secret).decrypt
    edata = encrypt(source)
    ddata = decrypt(edata)
    print(algorithm + " " + str(len(edata) - len(source)) +
          " " + str(source == ddata))
    sys.stdout.flush()


def stressTestAlgorithm(algorithm, secret, count, source):
    encrypt = make_secret(algorithm, secret).encrypt
    decrypt = make_secret(algorithm, secret).decrypt
    begin = time.time()
    for i in range(count):
        decrypt(encrypt(source))
    duration = time.time() - begin
    print(algorithm + " " + str(duration))
    sys.stdout.flush()


COUNTS_MAX = 100
SECRET_KEY = "secret key for test"
SOURCE_BUF = randomBytes(128 * 1024)
ALGORITHM_KEYS = sorted(secret_method_supported.keys())

stressTestAlgorithm("none", SECRET_KEY, COUNTS_MAX, SOURCE_BUF)
stressTestAlgorithm("xor", SECRET_KEY, COUNTS_MAX, SOURCE_BUF)
for key in ALGORITHM_KEYS:
    stressTestAlgorithm(key, SECRET_KEY, COUNTS_MAX, SOURCE_BUF)