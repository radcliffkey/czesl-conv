# coding=utf-8

"""
Conversion of Czesl XML to Manatee
"""

import argparse
import os
import os.path
import sys

import bs4

from collections import defaultdict
from os import DirEntry
from typing import Dict, Iterable, List, Mapping, NamedTuple

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


def processFileGroups(baseNameToPaths: Mapping[str, Dict[str, str]]) -> Iterable[MetaFile]:
    for baseName, nameToPath in baseNameToPaths.items():
        try:
            wname = baseName + '.w.xml'
            wfile = nameToPath[wname]
        except KeyError:
            raise FileNotFoundError(f'File {wname} expected but not found')

        try:
            aname = baseName + '.a.xml'
            afile = nameToPath[aname]
        except KeyError:
            raise FileNotFoundError(f'File {aname} expected but not found')

        try:
            bname = baseName + '.b.xml'
            bfile = nameToPath[bname]
        except KeyError:
            raise FileNotFoundError(f'File {bname} expected but not found')

        yield MetaFile(name=baseName, wfile=wfile, afile=afile, bfile=bfile)


def getMetaFiles(filenames: Iterable[str]) -> Iterable[MetaFile]:
    fullPaths = frozenset(os.path.abspath(fn) for fn in filenames if fn.endswith('.xml'))

    baseNameToPaths: Mapping[str, Dict[str, str]] = defaultdict(dict)
    for path in fullPaths:
        fileName = os.path.basename(path)
        baseName = fileName[:fileName.find('.')]
        baseNameToPaths[baseName][fileName] = path

    yield from processFileGroups(baseNameToPaths)


def getMetaFilesFromDir(dirName: str) -> Iterable[MetaFile]:
    dirEntries: Iterable[DirEntry] = os.scandir(dirName)
    xmlEntries: Iterable[DirEntry] = (e for e in dirEntries if e.is_file() and e.name.endswith('.xml'))

    baseNameToPaths: Mapping[str, Dict[str, str]] = defaultdict(dict)
    for entry in xmlEntries:
        baseName = entry.name[:entry.name.find('.')]
        baseNameToPaths[baseName][entry.name] = entry.path

    yield from processFileGroups(baseNameToPaths)


def paraToVert(bPara: bs4.Tag, aDoc: bs4.Tag, wDoc: bs4.Tag) -> str:
    bParaId = bPara['id']
    commonId = bParaId.split('-', maxsplit=1)[1]

    aParaId = bPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    aPara = aDoc.find(name='para', id=aParaId, recursive=False)

    wParaId = aPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    wPara = wDoc.find(name='para', id=wParaId, recursive=False)



    vertBuffer: List[str] = []

    vertBuffer.append(f'<p id="{commonId}">')

    vertBuffer.append('</p>')

    return '\n'.join(vertBuffer)


def docToVert(bDoc: bs4.Tag, wLayer: bs4.Tag, aLayer: bs4.Tag) -> str:
    docId = bDoc['id']

    wDoc = wLayer.wdata.find(name='doc', id=docId, recursive=False)
    aDoc = aLayer.ldata.find(name='doc', id=docId, recursive=False)

    vertBuffer: List[str] = []

    vertBuffer.append(f'<doc t_id={docId}>')

    bParas: Iterable[bs4.Tag] = bDoc.find_all(name='para', recursive=False)

    for bPara in bParas:
        vertBuffer.append(paraToVert(bPara, aDoc, wDoc))

    vertBuffer.append('</doc>')

    return '\n'.join(vertBuffer)


def xmlToVert(metaXml: MetaXml) -> str:
    wLayer = BeautifulSoup(metaXml.wxml, 'lxml-xml')
    aLayer = BeautifulSoup(metaXml.axml, 'lxml-xml')
    bLayer = BeautifulSoup(metaXml.bxml, 'lxml-xml')

    bDocs: Iterable[bs4.Tag] = bLayer.ldata.find_all(name='doc', recursive=False)

    vertBuffer: List[str] = []

    for bDoc in bDocs:
        vertBuffer.append(docToVert(bDoc, wLayer, aLayer))

    return '\n'.join(vertBuffer)


def main():

    argparser = argparse.ArgumentParser()

    inputArgGrp = argparser.add_mutually_exclusive_group(required=True)
    inputArgGrp.add_argument('-f', '--files', nargs='+', metavar='FILE', help='files to process')
    inputArgGrp.add_argument('-d', '--dir', metavar='DIR', help='directory to process')

    args = argparser.parse_args()

    metaFiles: Iterable[MetaFile] = getMetaFilesFromDir(args.dir) if args.dir else getMetaFiles(args.files)

    for metaFile in metaFiles:
        metaXml: MetaXml = readMetaFile(metaFile)
        vertStr: str = xmlToVert(metaXml)
        print(vertStr)



if __name__ == '__main__':
    main()
