# coding=utf-8

"""
Tools for worikng with Czesl XML files
"""

import os
import os.path

from  collections import defaultdict
from os import DirEntry
from typing import Dict, Iterable, Mapping, NamedTuple


class MetaFile(NamedTuple):
    """
    Tuple of filenames belonging to the same annotated document
    """
    name: str
    wfile: str
    afile: str
    bfile: str


class MetaXml(NamedTuple):
    """
    Tuple of XML strings belonging to the same annotated document
    """
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


def _processFileGroups(baseNameToPaths: Mapping[str, Dict[str, str]]) -> Iterable[MetaFile]:
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
    """
    Find triples <doc>.w.xml, <doc>.a.xml, <doc>.b.xml in a list of file names
    @param filenames: iterable of file names
    @return: generator of MetaFiles, which group together triples mentioned above
    """
    fullPaths = frozenset(os.path.abspath(fn) for fn in filenames if fn.endswith('.xml'))

    baseNameToPaths: Mapping[str, Dict[str, str]] = defaultdict(dict)
    for path in fullPaths:
        fileName = os.path.basename(path)
        baseName = fileName[:fileName.find('.')]
        baseNameToPaths[baseName][fileName] = path

    yield from _processFileGroups(baseNameToPaths)


def getMetaFilesFromDir(dirName: str) -> Iterable[MetaFile]:
    """
    Find triples <doc>.w.xml, <doc>.a.xml, <doc>.b.xml in a directory
    @param dirName: directory path
    @return: generator of MetaFiles, which group together triples mentioned above
    """
    dirEntries: Iterable[DirEntry] = os.scandir(dirName)
    xmlEntries: Iterable[DirEntry] = (e for e in dirEntries if e.is_file() and e.name.endswith('.xml'))

    baseNameToPaths: Mapping[str, Dict[str, str]] = defaultdict(dict)
    for entry in xmlEntries:
        baseName = entry.name[:entry.name.find('.')]
        baseNameToPaths[baseName][entry.name] = entry.path

    yield from _processFileGroups(baseNameToPaths)
