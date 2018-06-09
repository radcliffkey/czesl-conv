# coding=utf-8

"""
Conversion of Czesl XML to Manatee
"""

import argparse
import sys
import bs4
import traceback

from czeslconv import iotools
from czeslconv.iotools import MetaFile, MetaXml

from bs4 import BeautifulSoup
from collections import defaultdict, deque
from typing import Any, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional, Sequence, Union, Tuple

# Separator used when fitting multiple POS-tags within a single vertical field
POS_TAG_SEP = '|'

DEL_TOK_STR = '===NONE==='
DEL_TOK_ID = 'NA'


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
        self.linkIdsLower: List[str] = list(linkIdsLower) if linkIdsLower else []
        self.linkIdsHigher: List[str] = list(linkIdsHigher) if linkIdsHigher else []
        self.errors: List[ErrorData] = list(errors) if errors else []
        self.linksLower: List[Union[AnnotToken, DeletionToken]] = list(linksLower) if linksLower else []
        self.linksHigher: List[Union[AnnotToken, DeletionToken]] = list(linksHigher) if linksHigher else []

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

        if len(wTag.find_all(name='edge', recursive=False)) > 1:
            print(f'w-tag contains multiple edges: {wTag}', file=sys.stderr)
            errors = [ErrorData.fromTag(err) for edge in wTag.find_all(name='edge', recursive=False)
                    for err in edge.find_all(name='error')]
        else:
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
    """
    add references to higher and lower layers to tokens based on linked token IDs
    """
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
        for edge in aw.find_all(name='edge', recursive=False):
            # multi-edges are broken to simple edges between all vertices which may lead to information loss
            fromIds = [inEdge.string.split('#', maxsplit=1)[1] for inEdge in edge.find_all(name='from')]
            toIds = [awId] + [outEdge.string for outEdge in edge.find_all(name='to')]
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
    if not tokLayer:
        return

    for tok in tokLayer:
        currSentId = None

        if tok.linksHigher and not isinstance(tok.linksHigher[0], DeletionToken):
            currSentId = tok.linksHigher[0].sentenceId

        tok.sentenceId = currSentId

    firstOkIdx = None
    # in case there were unlinked nodes at the beginning
    for i, tok in enumerate(tokLayer):
        if tok.sentenceId:
            firstSentenceId = tok.sentenceId
            firstOkIdx = i
            break

    if firstOkIdx is None:
        print('could not assign sentence ID to tokens', ', '.join(t.tid for t in tokLayer), file=sys.stderr)
        for tok in tokLayer:
            tok.sentenceId = 'unknown'
        return

    for i in range(firstOkIdx):
        tokLayer.tokens[i].sentenceId = firstSentenceId

    for i, tok in enumerate(tokLayer):
        if tok.sentenceId is None:
            tok.sentenceId = tokLayer.tokens[i - 1].sentenceId
        assert tok.sentenceId


def _noErrors(tok: AnnotToken) -> bool:
    """
    True is the token does not fix any errors (that includes being a deletion node)
    """
    return not tok.errors and not isinstance(tok, DeletionToken)


def _noErrorsTransitive(wTok: AnnotToken) -> bool:
    """
    True is the whole annotation chain of a token from W to B layer does not contain errors
    """
    if len(wTok.linksHigher) != 1 or isinstance(wTok.linksHigher[0], DeletionToken):
        return False

    aTok = wTok.linksHigher[0]

    if aTok.errors or len(aTok.linksHigher) != 1 or isinstance(aTok.linksHigher[0], DeletionToken):
        return False

    bTok = aTok.linksHigher[0]

    if bTok.errors:
        return False

    return True


def getErrorTypeStr(tok: AnnotToken):
    return '|'.join('|'.join(e.tags) for e in tok.errors)


def inferErrors(tokLayer: TokenLayer):
    for token in tokLayer:
        if not token.errors and len(token.linksLower) == 1:
            lowerTok = token.linksLower[0]
            if lowerTok.baseToken.text != token.baseToken.text:
                token.errors = [ErrorData(tags=['unknown'], links=[])]


def paraToVert(bPara: bs4.Tag, aDoc: bs4.Tag, wDoc: bs4.Tag, guessErrors: bool=False) -> str:
    bParaId = bPara['id']
    commonId = bParaId.split('-', maxsplit=1)[1]

    aParaId = bPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    aPara = aDoc.find(name='para', id=aParaId, recursive=False)

    wParaId = aPara['lowerpara.rf'].split('#', maxsplit=1)[1]
    wPara = wDoc.find(name='para', id=wParaId, recursive=False)

    wLayer, aLayer, bLayer = createLinkedLayers(wPara, aPara, bPara)
    assignSentenceIds(aLayer)
    assignSentenceIds(wLayer)

    if guessErrors:
        inferErrors(aLayer)
        inferErrors(bLayer)

    currSentenceId = None
    vertBuffer: List[str] = []

    wToks = deque(wLayer)

    vertBuffer.append(f'<p id="{commonId}">')
    while wToks:
        wTok = wToks.popleft()
        if wTok.sentenceId != currSentenceId:
            if currSentenceId:
                vertBuffer.append('</s>')
            currSentenceId = wTok.sentenceId
            vertBuffer.append(f'<s id="{currSentenceId}">')

        if _noErrorsTransitive(wTok):
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
            if len(wTok.linksHigher) == 0 or isinstance(wTok.linksHigher[0], DeletionToken):
                deletionTok = wTok.linksHigher[0] if wTok.linksHigher else None
                errTier = '1'
                errTypeStr = getErrorTypeStr(deletionTok) if deletionTok else 'del'
                vertBuffer.append(f'<err level="{errTier}" type="{errTypeStr}">')
                vertBuffer.append('\t'.join((wTok.baseToken.text, wTok.tid, '', '', '', '')))
                vertBuffer.append('</err>')
                vertBuffer.append(f'<corr level="{errTier}" type="{errTypeStr}">')
                vertBuffer.append('\t'.join((DEL_TOK_STR, '', DEL_TOK_ID, DEL_TOK_ID, '', '')))
                vertBuffer.append('</corr>')
            else:
                aTok1 = wTok.linksHigher[0]
                if aTok1.errors:
                    errWToks = [wTok]
                    while wToks and (aTok1 in wToks[0].linksHigher):
                        errWToks.append(wToks.popleft())

                    errTier = '1'
                    errTypeStr = '|'.join('|'.join(e.tags) for e in aTok1.errors)

                    vertBuffer.append(f'<err level="{errTier}" type="{errTypeStr}">')
                    for errWTok in errWToks:
                        vertBuffer.append('\t'.join((errWTok.baseToken.text, errWTok.tid, '', '', '', '')))
                    vertBuffer.append('</err>')
                    vertBuffer.append(f'<corr level="{errTier}" type="{errTypeStr}">')

                    for aTok in wTok.linksHigher:
                        if len(aTok.linksHigher) == 1 and _noErrors(aTok.linksHigher[0]):
                            bTok = aTok.linksHigher[0]
                            vertBuffer.append('\t'.join((
                                aTok.baseToken.text,
                                '',
                                aTok.tid,
                                bTok.tid,
                                bTok.baseToken.morph.lemma,
                                POS_TAG_SEP.join(bTok.baseToken.morph.tags)
                            )))
                        elif len(aTok.linksHigher) >= 1 and not isinstance(aTok.linksHigher[0], DeletionToken):
                            bTok1 = aTok.linksHigher[0]
                            errTier = '2'
                            errTypeStr = '|'.join('|'.join(e.tags) for e in bTok1.errors)
                            vertBuffer.append(f'<err level="{errTier}" type="{errTypeStr}">')
                            aLemmas = '|'.join(m.lemma for m in aTok.baseToken.morphs)
                            aTags = '|+|'.join(POS_TAG_SEP.join(m.tags) for m in aTok.baseToken.morphs)
                            vertBuffer.append('\t'.join((aTok.baseToken.text, '', aTok.tid, '', aLemmas, aTags)))
                            vertBuffer.append('</err>')
                            vertBuffer.append(f'<corr level="{errTier}" type="{errTypeStr}">')
                            for bTok in aTok.linksHigher:
                                vertBuffer.append('\t'.join((
                                bTok.baseToken.text,
                                '',
                                '',
                                bTok.tid,
                                bTok.baseToken.morph.lemma,
                                POS_TAG_SEP.join(bTok.baseToken.morph.tags)
                            )))
                            vertBuffer.append('</corr>')
                        else:
                            print(f'skipping unhandled error (deletion) for token {aTok.tid} "{aTok.baseToken.text}"', file=sys.stderr)
                    vertBuffer.append('</corr>')

                elif len(wTok.linksHigher) == 1 and len(aTok1.linksHigher) >= 1 and not isinstance(aTok1.linksHigher[0], DeletionToken):
                    bTok1 = aTok1.linksHigher[0]
                    errTier = '2'
                    errTypeStr = '|'.join('|'.join(e.tags) for e in bTok1.errors)
                    aLemmas = '|'.join(m.lemma for m in aTok1.baseToken.morphs)
                    aTags = '|+|'.join(POS_TAG_SEP.join(m.tags) for m in aTok1.baseToken.morphs)
                    vertBuffer.append(f'<err level="{errTier}" type="{errTypeStr}">')
                    vertBuffer.append('\t'.join((wTok.baseToken.text, wTok.tid, aTok1.tid, '', aLemmas, aTags)))
                    vertBuffer.append('</err>')
                    vertBuffer.append(f'<corr level="{errTier}" type="{errTypeStr}">')
                    for bTok in aTok1.linksHigher:
                        vertBuffer.append('\t'.join((
                            bTok.baseToken.text,
                            '',
                            '',
                            bTok.tid,
                            bTok.baseToken.morph.lemma,
                            POS_TAG_SEP.join(bTok.baseToken.morph.tags)
                        )))
                    vertBuffer.append('</corr>')

                elif len(wTok.linksHigher) == 1 and (len(aTok1.linksHigher) == 0 or isinstance(aTok1.linksHigher[0], DeletionToken)):
                    deletionTok = aTok1.linksHigher[0] if aTok1.linksHigher else None
                    errTier = '2'
                    errTypeStr = getErrorTypeStr(deletionTok) if deletionTok else 'del'

                    aLemmas = '|'.join(m.lemma for m in aTok1.baseToken.morphs)
                    aTags = '|+|'.join(POS_TAG_SEP.join(m.tags) for m in aTok1.baseToken.morphs)
                    vertBuffer.append(f'<err level="{errTier}" type="{errTypeStr}">')
                    vertBuffer.append('\t'.join((wTok.baseToken.text, wTok.tid, aTok1.tid, '', aLemmas, aTags)))
                    vertBuffer.append('</err>')
                    vertBuffer.append(f'<corr level="{errTier}" type="{errTypeStr}">')
                    vertBuffer.append('\t'.join((DEL_TOK_STR, '', '', DEL_TOK_ID, '', '')))
                    vertBuffer.append('</corr>')
                else:
                    print(f'skipping unhandled error for token {wTok.tid} "{wTok.baseToken.text}"', file=sys.stderr)

            #handle errors

    if currSentenceId:
        vertBuffer.append('</s>')

    vertBuffer.append('</p>')

    return '\n'.join(vertBuffer)


def docToVert(bDoc: bs4.Tag, wLayer: bs4.Tag, aLayer: bs4.Tag, guessErrors: bool=False) -> str:
    bDocId = bDoc['id']
    # Use reference to lower layers to get lower layer doc IDs.
    # If the attribute 'lowerdoc.rf' is missing,
    # try two doc ID formats: 1) the same in all layers 2) prefixed by the layer name

    aDocId = bDoc['lowerdoc.rf'][2:] if bDoc.has_attr('lowerdoc.rf') else 'a' + bDocId[1:]
    aDoc = (aLayer.ldata.find(name='doc', id=aDocId, recursive=False)
            or aLayer.ldata.find(name='doc', id=bDocId, recursive=False))

    wDocId = aDoc['lowerdoc.rf'][2:] if aDoc.has_attr('lowerdoc.rf') else 'w' + bDocId[1:]
    wDoc = (wLayer.wdata.find(name='doc', id=wDocId, recursive=False)
            or wLayer.wdata.find(name='doc', id=bDocId, recursive=False))

    aTokCnt = len(aDoc.find_all(name='w', recursive=True))
    bTokCnt = len(bDoc.find_all(name='w', recursive=True))

    if bTokCnt == 0 and aTokCnt > 0:
        raise ValueError('B-layer annotation missing')


    vertBuffer: List[str] = []

    outDocId = bDocId[2:]
    vertBuffer.append(f'<doc id="{outDocId}">')

    bParas: Iterable[bs4.Tag] = bDoc.find_all(name='para', recursive=False)

    for bPara in bParas:
        vertBuffer.append(paraToVert(bPara, aDoc, wDoc, guessErrors=guessErrors))

    vertBuffer.append('</doc>')

    return '\n'.join(vertBuffer)


def xmlToVert(metaXml: MetaXml, guessErrors: bool=False) -> str:
    wLayer = BeautifulSoup(metaXml.wxml, 'lxml-xml')
    aLayer = BeautifulSoup(metaXml.axml, 'lxml-xml')
    bLayer = BeautifulSoup(metaXml.bxml, 'lxml-xml')

    bDocs: Iterable[bs4.Tag] = bLayer.ldata.find_all(name='doc', recursive=False)

    vertBuffer: List[str] = []

    for bDoc in bDocs:
        vertBuffer.append(docToVert(bDoc, wLayer, aLayer, guessErrors=guessErrors))

    return '\n'.join(vertBuffer)


def main():

    argparser = argparse.ArgumentParser()

    inputArgGrp = argparser.add_mutually_exclusive_group(required=True)
    inputArgGrp.add_argument('-f', '--files', nargs='+', metavar='FILE', help='files to process')
    inputArgGrp.add_argument('-d', '--dir', metavar='DIR', help='directory to process')
    argparser.add_argument('-g', '--guessErrors', action='store_true', help='detect errors by comparing token texts')

    args = argparser.parse_args()

    metaFiles: Iterable[MetaFile] = iotools.getMetaFilesFromDir(args.dir) if args.dir else iotools.getMetaFiles(args.files)

    for metaFile in metaFiles:
        print(f'processing {metaFile}', file=sys.stderr)
        metaXml: MetaXml = iotools.readMetaFile(metaFile)
        try:
            vertStr: str = xmlToVert(metaXml, guessErrors=args.guessErrors)
        except Exception as e:
            print(f'Failed to process files {metaFile}', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue

        print(vertStr)
        print()


if __name__ == '__main__':
    main()
