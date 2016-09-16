from setuptools import setup, find_packages

VERSION = '1.7.3'


setup(
    name='weaknet',
    version=VERSION,
    description='A limited network transport implementation',
    keywords='weaknet, shadowsocks, ss',
    author='Vietor Liu',
    author_email='vietor.liu@gmail.com',
    url='https://github.com/vietor/pyweaknet',
    download_url='https://github.com/vietor/pyweaknet/tarball/{0}'.format(VERSION),
    license='MIT',
    scripts=['bin/weaknet.py'],
    requires=[
        'python (>=2.6.0)',
    ]
)
