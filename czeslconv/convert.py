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
from typing import Any, Dict, Iterable, List, Mapping, NamedTuple, Sequence, Union

from bs4 import BeautifulSoup


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


class Morph(NamedTuple):
    lemma: str
    tags: Sequence[str]

    @staticmethod
    def fromLexTag(lex: bs4.Tag) -> 'Morph':
        assert len(lex.find_all(name='lemma', recursive=False)) == 1
        return Morph(lemma=lex.lemma.string, tags=[t.string for t in lex.find_all(name='mtag', recursive=False)])

class WToken(NamedTuple):
    text: str


class AToken(NamedTuple):
    text: str
    morphs: Sequence[Morph]


class BToken(NamedTuple):
    text: str
    morph: Morph


class ErrorData(NamedTuple):
    tags: Sequence[str]
    links: Sequence[str]

    @staticmethod
    def fromTag(error: bs4.Tag) -> 'ErrorData':
        tags = [t.string for t in error.find_all(name='tag')]
        links = [l.string for l in error.find_all(name='link')]
        return ErrorData(tags=tags, links=links)


class DeletionToken(NamedTuple):
    fromId: str
    errors: Sequence[ErrorData]


class AnnotToken:
    """
    Annotated token with link to other layers
    """

    def __init__(self,
            tid:str,
            baseToken: Union[WToken, AToken, BToken],
            *,
            layer:str= None,
            sentenceId: str=None,
            linkIdsLower: Iterable[str]=None,
            linkIdsHigher: Iterable[str]=None,
            errors: Iterable[ErrorData]=None,
            linksLower: Iterable[Union['AnnotToken', DeletionToken]]=None,
            linksHigher: Iterable[Union['AnnotToken', DeletionToken]]=None
    ) -> None:
        self.tid=tid
        self.baseToken = baseToken
        self.layer = layer
        self.sentenceId = sentenceId
        self.linkIdsLower = linkIdsLower
        self.linkIdsHigher = linkIdsHigher
        self.errors = errors if errors else []
        self.linksLower = linksLower if linksLower else []
        self.linksHigher = linksHigher if linksHigher else []

    def __str__(self) -> str:
        return f'Token(layer={self.layer}, id={self.tid}, morph={self.baseToken})'

    __repr__ = __str__


class TokenLayer(NamedTuple):
    name: str
    tokens: Sequence[AnnotToken]
    idToToken: Mapping[str, AnnotToken]

    @staticmethod
    def of(name:str, tokens: Sequence[AnnotToken]) -> 'TokenLayer':
        tokens = list(tokens)
        idToToken = {t.tid: t for t in tokens}
        return TokenLayer(name, tokens, idToToken)

    def get(self, tid:str) -> AnnotToken:
        return self.idToToken.get(tid)


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


def revertMapping(mapping: Mapping[Any, Iterable[Any]]) -> Mapping[Any, List[Any]]:
    revertedMap: Mapping[Any, List[Any]] = defaultdict(list)
    for k, vals in mapping.items():
        for v in vals:
            revertedMap[v].append(k)

    return revertedMap


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


def createWLayer(
        wPara: bs4.Tag,
        idMapWA: Mapping[str, List[str]],
        idToDelW: Mapping[str, DeletionToken]
) -> TokenLayer:

    tokens: List[AnnotToken] = []

    for wTag in wPara.find_all(name='w'):
        wid = wTag['id']
        tokens.append(AnnotToken(
            tid=wid,
            baseToken=WToken(wTag.token.string),
            layer='w',
            linkIdsHigher=idMapWA[wid],
            linksHigher=[idToDelW[wid]] if wid in idToDelW else []
        ))

    return TokenLayer.of('w', tokens)


def createALayer(
        aPara: bs4.Tag,
        idMapAW: Mapping[str, List[str]],
        idMapAB: Mapping[str, List[str]],
        idToDelA: Mapping[str, DeletionToken]
) -> TokenLayer:

    tokens: List[AnnotToken] = []

    for wTag in aPara.find_all(name='w'):
        wid = wTag['id']

        if not wTag.lex:
            print(f'skipping token with no lex tag: {wTag}', file=sys.stderr)
            continue

        morphs = [Morph.fromLexTag(lex) for lex in wTag.find_all(name='lex', recursive=False)]

        assert len(wTag.find_all(name='edge', recursive=False)) <= 1, f'w-tag contains multiple edges: {wTag}'
        errors = [ErrorData.fromTag(err) for err in wTag.edge.find_all(name='error')] if wTag.edge else []

        tokens.append(AnnotToken(
            tid=wid,
            baseToken=AToken(text=wTag.token.string, morphs=morphs),
            layer='a',
            linkIdsLower=idMapAW[wid],
            linkIdsHigher=idMapAB[wid],
            linksHigher=[idToDelA[wid]] if wid in idToDelA else [],
            errors=errors
        ))

    return TokenLayer.of('a', tokens)


def createBLayer(
        bPara: bs4.Tag,
        idMapBA: Mapping[str, List[str]],
) -> TokenLayer:

    tokens: List[AnnotToken] = []

    for wTag in bPara.find_all(name='w'):
        wid = wTag['id']

        if not wTag.lex:
            print(f'skipping token with no lex tag: {wTag}', file=sys.stderr)
            continue

        assert len(wTag.find_all(name='lex', recursive=False)) == 1, f'w-tag contains multiple lex tags: {wTag}'
        morph = Morph.fromLexTag(wTag.lex)

        #assert len(wTag.find_all(name='edge', recursive=False)) <= 1, f'w-tag contains multiple edges: {wTag}'
        errors = [ErrorData.fromTag(err) for err in wTag.edge.find_all(name='error')] if wTag.edge else []

        tokens.append(AnnotToken(
            tid=wid,
            baseToken=BToken(text=wTag.token.string, morph=morph),
            layer='b',
            linkIdsLower=idMapBA[wid],
            errors=errors
        ))

    return TokenLayer.of('b', tokens)


def createLinkedLayers(wPara: bs4.Tag, aPara: bs4.Tag, bPara: bs4.Tag):
    idMapWA: Mapping[str, List[str]] = defaultdict(list)
    idMapAB: Mapping[str, List[str]] = defaultdict(list)

    for aw in aPara.find_all(name='w'):
        awId = aw['id']
        if aw.edge:
            fromIds = [inEdge.string.split('#', maxsplit=1)[1] for inEdge in aw.edge.find_all(name='from')]
            toIds = [awId] + [outEdge.string for outEdge in aw.edge.find_all(name='to')]
            for fromId in fromIds:
                idMapWA[fromId].extend(toIds)

    idToDelW = findDeletions(aPara)

    for bw in bPara.find_all(name='w'):
        bwId = bw['id']
        if bw.edge:
            fromIds = [inEdge.string.split('#', maxsplit=1)[1] for inEdge in bw.edge.find_all(name='from')]
            toIds = [bwId] + [outEdge.string for outEdge in bw.edge.find_all(name='to')]
            for fromId in fromIds:
                idMapAB[fromId].extend(toIds)

    idToDelA = findDeletions(bPara)

    idMapAW = revertMapping(idMapWA)
    idMapBA = revertMapping(idMapAB)

    wLayer = createWLayer(wPara=wPara, idMapWA=idMapWA, idToDelW=idToDelW)
    aLayer = createALayer(aPara=aPara, idMapAW=idMapAW, idMapAB=idMapAB, idToDelA=idToDelA)
    bLayer = createBLayer(bPara=bPara, idMapBA=idMapBA)
    print(bLayer)


def findDeletions(paragraph: bs4.Tag) -> Dict[str, DeletionToken]:
    idToDel = {}
    for delEdge in paragraph.find_all(name='edge', recursive=False):
        if delEdge.to:
            print(f'Unexpected non-deletion edge directly under <para>: {delEdge}', file=sys.stderr)
            continue
        fromIds = [inEdge.string.split('#', maxsplit=1)[1] for inEdge in delEdge.find_all(name='from')]
        errors = [ErrorData.fromTag(err) for err in delEdge.find_all(name='error')]

        for fromId in fromIds:
            idToDel[fromId] = DeletionToken(fromId=fromId, errors=errors)

    return idToDel


def paraToVert(bPara: bs4.Tag, aDoc: bs4.Tag, wDoc: bs4.Tag) -> str:
    bParaId = bPara['id']
    commonId = bParaId.split('-', maxsplit=1)[1]

    aParaId = bPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    aPara = aDoc.find(name='para', id=aParaId, recursive=False)

    wParaId = aPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    wPara = wDoc.find(name='para', id=wParaId, recursive=False)

    createLinkedLayers(wPara, aPara, bPara)

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
