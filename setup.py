# coding=utf-8

from setuptools import setup

setup(
    name='czeslconv',
    version='1.0.1',

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
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Text Processing :: Linguistic'
    ],

    # Dependencies
    # lxml requries C libraries libxml2 and libxslt installed on your system
    install_requires=['beautifulsoup4>=4.6', 'lxml>=4.0'],

    packages=['czeslconv'],

    test_suite='czeslconv.test'
)
