import sys
from setuptools import setup, find_packages

VERSION = '1.7.3'
GITHUB_URL = 'https://github.com/vietor/pyweaknet'

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    os.system('python setup.py bdist_wheel upload')
    sys.exit()

setup(
    name='weaknet',
    version=VERSION,
    keywords='weaknet, shadowsocks, ss',
    description='A limited network transport tool',
    author='Vietor Liu',
    author_email='vietor.liu@gmail.com',
    url=GITHUB_URL,
    download_url='{0}/tarball/{1}'.format(GITHUB_URL, VERSION),
    license='MIT',
    scripts=['bin/weaknet.py'],
    requires=[
        'python (>=2.6.0)',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Development Status :: 5 - Production/Stable',
        'Natural Language :: English',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License'
    ]
)
