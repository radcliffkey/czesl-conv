# coding=utf-8

"""
Conversion of Czesl XML to Manatee
"""

import argparse
import os
import sys

from collections import defaultdict
from os import DirEntry
from typing import Dict, Iterable, NamedTuple, Mapping

from bs4 import BeautifulSoup

class MetaFile(NamedTuple):
    name: str
    wfile: str
    afile: str
    bfile: str


class MetaXml(NamedTuple):
    name: str
    wxml: str
    axml: str
    bxml: str


def readFile(fileName: str) -> str:
    with open(fileName, 'r', encoding='utf-8') as f:
        return f.read()


def readMetaFile(metaFile: MetaFile) -> MetaXml:
    return MetaXml(
        name=metaFile.name,
        wxml=readFile(metaFile.wfile),
        axml=readFile(metaFile.afile),
        bxml=readFile(metaFile.bfile)
    )


def getMetaFiles(dirName: str) -> Iterable[MetaFile]:
    dirEntries: Iterable[DirEntry] = os.scandir(dirName)
    xmlEntries: Iterable[DirEntry] = (e for e in dirEntries if e.is_file() and e.name.endswith('.xml'))

    baseNameToEntries: Mapping[str, Dict[str, DirEntry]] = defaultdict(dict)
    for entry in xmlEntries:
        baseName = entry.name[:entry.name.find('.')]
        baseNameToEntries[baseName][entry.name] = entry

    for baseName, nameToEntry in baseNameToEntries.items():
        try:
            wname = baseName + '.w.xml'
            wfile = nameToEntry[wname].path
        except KeyError:
            raise FileNotFoundError('Could not find file {} in directory {}'.format(wname, dirName))

        try:
            aname = baseName + '.a.xml'
            afile = nameToEntry[aname].path
        except KeyError:
            raise FileNotFoundError('Could not find file {} in directory {}'.format(aname, dirName))

        try:
            bname = baseName + '.b.xml'
            bfile = nameToEntry[bname].path
        except KeyError:
            raise FileNotFoundError('Could not find file {} in directory {}'.format(bname, dirName))

        yield MetaFile(name=baseName, wfile=wfile, afile=afile, bfile=bfile)

def xmlToVert(metaXml: MetaXml) -> str:
    wLayer = BeautifulSoup(metaXml.wxml, 'lxml-xml')
    aLayer = BeautifulSoup(metaXml.axml, 'lxml-xml')
    bLayer = BeautifulSoup(metaXml.bxml, 'lxml-xml')

    return ''

def main():

    argparser = argparse.ArgumentParser()
    argparser.add_argument('-d', '--dir', required=True, help='directory to process')

    args = argparser.parse_args()

    metaFiles: Iterable[MetaFile] = getMetaFiles(args.dir)

    for metaFile in metaFiles:
        metaXml: MetaXml = readMetaFile(metaFile)
        vertStr: str = xmlToVert(metaXml)

if __name__ == '__main__':
    main()
