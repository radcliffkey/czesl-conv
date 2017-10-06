# coding=utf-8

"""
Conversion of Czesl XML to Manatee
"""

import argparse
import sys
import bs4

from czeslconv import iotools
from czeslconv.iotools import MetaFile, MetaXml

from bs4 import BeautifulSoup
from collections import defaultdict
from typing import Any, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional, Sequence, Union, Tuple

# Separator used when fitting multiple POS-tags within a single vertical field
POS_TAG_SEP = '|'


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

    def get(self, tid:str) -> Optional[AnnotToken]:
        return self.idToToken.get(tid)

    def __iter__(self) -> Iterator[AnnotToken]:
        return iter(self.tokens)

    def __len__(self) -> int:
        return len(self.tokens)


def revertMapping(mapping: Mapping[Any, Iterable[Any]]) -> Mapping[Any, List[Any]]:
    revertedMap: Mapping[Any, List[Any]] = defaultdict(list)
    for k, vals in mapping.items():
        for v in vals:
            revertedMap[v].append(k)

    return revertedMap


def createWLayer(
        wPara: bs4.Tag,
        idMapWA: Mapping[str, List[str]],
        idToDelW: Mapping[str, DeletionToken]
) -> TokenLayer:

    tokens: List[AnnotToken] = []


    for wTag in wPara.find_all(name='w'):
        wid = wTag['id']

        delNode = idToDelW.get(wid)
        linkIdsHigher = idMapWA[wid]

        if not delNode and not linkIdsHigher:
            print(f'W-layer token with no links to A-layer: {wTag}', file=sys.stderr)
        elif delNode and linkIdsHigher:
            print(f'W-layer token with both deletion and non-deletion edges to A-layer: {wTag}', file=sys.stderr)

        tokens.append(AnnotToken(
            tid=wid,
            baseToken=WToken(wTag.token.string),
            layer='w',
            linkIdsHigher=linkIdsHigher,
            linksHigher=[delNode] if delNode else []
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

        delNode = idToDelA.get(wid)
        linkIdsHigher = idMapAB[wid]

        if not delNode and not linkIdsHigher:
            print(f'A-layer token with no links to B-layer: {wTag}', file=sys.stderr)
        elif delNode and linkIdsHigher:
            print(f'A-layer token with both deletion and non-deletion edges to B-layer: {wTag}', file=sys.stderr)

        tokens.append(AnnotToken(
            tid=wid,
            baseToken=AToken(text=wTag.token.string, morphs=morphs),
            layer='a',
            linkIdsLower=idMapAW[wid],
            linkIdsHigher=linkIdsHigher,
            linksHigher=[delNode] if delNode else [],
            errors=errors
        ))

    return TokenLayer.of('a', tokens)


def createBLayer(
        bPara: bs4.Tag,
        idMapBA: Mapping[str, List[str]],
) -> TokenLayer:

    tokens: List[AnnotToken] = []

    for sentTag in bPara.find_all(name='s', recursive=False):
        sentId = sentTag['id']
        for wTag in sentTag.find_all(name='w', recursive=False):
            wid = wTag['id']

            if not wTag.lex:
                print(f'skipping token with no lex tag: {wTag}', file=sys.stderr)
                continue

            assert len(wTag.find_all(name='lex', recursive=False)) == 1, f'B-layer w-tag contains multiple lex tags: {wTag}'
            morph = Morph.fromLexTag(wTag.lex)

            #assert len(wTag.find_all(name='edge', recursive=False)) <= 1, f'w-tag contains multiple edges: {wTag}'
            errors = [ErrorData.fromTag(err) for err in wTag.edge.find_all(name='error')] if wTag.edge else []

            tokens.append(AnnotToken(
                tid=wid,
                baseToken=BToken(text=wTag.token.string, morph=morph),
                layer='b',
                sentenceId=sentId,
                linkIdsLower=idMapBA[wid],
                errors=errors
            ))

    return TokenLayer.of('b', tokens)


def findTokensByIds(ids: Iterable[str], layer: TokenLayer) -> Tuple[List[AnnotToken], List[str]]:
    """
    find tokens by IDs in the given layer, return tuple of found token list and unmatched Ids
    """
    tokens = []
    unmatchedIds = []

    for tokId in ids:
        token = layer.get(tokId)
        if not token:
            unmatchedIds.append(tokId)
        else:
            tokens.append(token)

    return tokens, unmatchedIds


def linkLayers(wLayer: TokenLayer, aLayer: TokenLayer, bLayer: TokenLayer):
    for wToken in wLayer:
        if not wToken.linksHigher:
            wToken.linksHigher, unmatchedIds = findTokensByIds(wToken.linkIdsHigher, aLayer)
            for tokId in unmatchedIds:
                print(f'token "{tokId}" linked from w-layer token "{wToken.tid}" not found in a-layer')

    for aToken in aLayer:
        if not aToken.linksLower:
            aToken.linksLower, unmatchedIds = findTokensByIds(aToken.linkIdsLower, wLayer)
            for tokId in unmatchedIds:
                print(f'token "{tokId}" linked from a-layer token "{aToken.tid}" not found in w-layer')

        if not aToken.linksHigher:
            aToken.linksHigher, unmatchedIds = findTokensByIds(aToken.linkIdsHigher, bLayer)
            for tokId in unmatchedIds:
                print(f'token "{tokId}" linked from a-layer token "{aToken.tid}" not found in b-layer')

    for bToken in bLayer:
        if not bToken.linksLower:
            bToken.linksLower, unmatchedIds = findTokensByIds(bToken.linkIdsLower, aLayer)
            for tokId in unmatchedIds:
                print(f'token "{tokId}" linked from b-layer token "{bToken.tid}" not found in a-layer')


def createLinkedLayers(wPara: bs4.Tag, aPara: bs4.Tag, bPara: bs4.Tag) -> Tuple[TokenLayer, TokenLayer, TokenLayer]:
    """
    Add references to nodes in other layers.
    """
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

    linkLayers(wLayer, aLayer, bLayer)

    return wLayer, aLayer, bLayer


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


def assignSentenceIds(tokLayer: TokenLayer):
    """
    propagate sentence IDs to the given layer from a higher layer
    """
    for tok in tokLayer:
        currSentId = None

        if tok.linksHigher and not isinstance(tok.linksHigher[0], DeletionToken):
            currSentId = tok.linksHigher[0].sentenceId

        tok.sentenceId = currSentId

    # in case there were unlinked nodes at the beginning
    for i, tok in enumerate(tokLayer):
        if tok.sentenceId:
            firstSentenceId = tok.sentenceId
            firstOkIdx = i
            break

    for i in range(firstOkIdx):
        tokLayer.tokens[i].sentenceId = firstSentenceId


def _noErrors(wTok: AnnotToken) -> bool:
    if len(wTok.linksHigher) != 1 or isinstance(wTok.linksHigher[0], DeletionToken):
        return False

    aTok = wTok.linksHigher[0]

    if aTok.errors or len(aTok.linksHigher) != 1 or isinstance(aTok.linksHigher[0], DeletionToken):
        return False

    bTok = aTok.linksHigher[0]

    if bTok.errors:
        return False

    return True


def paraToVert(bPara: bs4.Tag, aDoc: bs4.Tag, wDoc: bs4.Tag) -> str:
    bParaId = bPara['id']
    commonId = bParaId.split('-', maxsplit=1)[1]

    aParaId = bPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    aPara = aDoc.find(name='para', id=aParaId, recursive=False)

    wParaId = aPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    wPara = wDoc.find(name='para', id=wParaId, recursive=False)

    wLayer, aLayer, bLayer = createLinkedLayers(wPara, aPara, bPara)
    assignSentenceIds(aLayer)
    assignSentenceIds(wLayer)

    currSentenceId = None
    vertBuffer: List[str] = []

    vertBuffer.append(f'<p id="{commonId}">')
    for wTok in wLayer:
        if wTok.sentenceId != currSentenceId:
            if currSentenceId:
                vertBuffer.append('</s>')
            currSentenceId = wTok.sentenceId
            vertBuffer.append(f'<s id={currSentenceId}>')

        if _noErrors(wTok):
            aTok = wTok.linksHigher[0]
            bTok = aTok.linksHigher[0]

            vertBuffer.append('\t'.join((
                wTok.baseToken.text,
                wTok.tid,
                aTok.tid,
                bTok.tid,
                bTok.baseToken.morph.lemma,
                POS_TAG_SEP.join(bTok.baseToken.morph.tags)
            )))
        else:
            pass
            #handle errors

    if currSentenceId:
        vertBuffer.append('</s>')

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

    metaFiles: Iterable[MetaFile] = iotools.getMetaFilesFromDir(args.dir) if args.dir else iotools.getMetaFiles(args.files)

    for metaFile in metaFiles:
        metaXml: MetaXml = iotools.readMetaFile(metaFile)
        vertStr: str = xmlToVert(metaXml)
        print(vertStr)
        print()


if __name__ == '__main__':
    main()
