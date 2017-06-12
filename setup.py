# coding=utf-8

from setuptools import setup

setup(
    name='czeslconv',
    version='1.0.0',

    author='Radoslav Klic',
    author_email='radoslav.klic@gmail.com',
    description='Conversion of Czesl XML to Manatee format',
    keywords='Czesl XML Manatee corpus',
    url='https://github.com/radcliffkey/czesl-conv',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'License :: Apache License 2.0'
    ],

    # Dependencies
    install_requires=['beautifulsoup4>=4.6'],

    # Don't use find_packages() because it does not work well with namespace packages.
    packages=['czeslconv'],

    test_suite='czeslconv.test'
)
