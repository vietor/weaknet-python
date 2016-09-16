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
    license='MIT',
    package_dir={'': 'weaknet'},
    packages=find_packages('weaknet'),
    include_package_data=True,
    requires=[
        'python (>=2.6.0)',
    ],
    entry_points={
        'console_scripts': [
            'weaknet = weaknet.weaknet:main',
        ]
    },
    install_requires=[],
    data_files=[],
)
