"""Turning what somebody typed into a query plus a list of things to leave out."""

from __future__ import annotations

import re
from dataclasses import dataclass

from esn_engine.search.exclusions import CONCEPT_WORDS

# Naming these as strings first, otherwise the formatter puts every word on its own line.
_NEGATIONS = "no not without except excluding exclude avoid minus skip"
_FILLER = (
    "show me some give get find i want wanna need please of the a an for that would "
    "there is are and to stuff any something anything us my we"
)
_VIDEO = "video videos clip clips footage reel reels"
_PHOTO = "photo photos picture pictures pic pics image images shot shots"

NEGATIONS = frozenset(_NEGATIONS.split())
# People type these but they say nothing about what to retrieve.
FILLER = frozenset(_FILLER.split())
VIDEO_WORDS = frozenset(_VIDEO.split())
PHOTO_WORDS = frozenset(_PHOTO.split())

WORD = re.compile(r"[a-z0-9]+")

# How many words after a negation word are checked for something to exclude. "no booze" is
# one, "without any alcohol" is three.
NEGATION_WINDOW = 3


@dataclass(frozen=True)
class ParsedQuery:
    """What the search is actually going to run."""

    text: str
    excluded: tuple[str, ...]
    kind: str | None
    # Kept so the interface can show what was understood instead of guessing.
    dropped: tuple[str, ...]


def parse(raw: str) -> ParsedQuery:
    """Split a query into the part to search for and the parts to leave out.

    A brief like "happy volunteers, no booze" has to come out as text "happy volunteers" and
    excluded ("alcohol",). Miss the negation and the alcohol clips come straight back, so
    anything after a negation word is dropped from the positive text even when it does not
    map to a concept.
    """
    tokens = WORD.findall(raw.lower())

    excluded: list[str] = []
    dropped: list[str] = []
    keep: list[str] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in NEGATIONS:
            window = tokens[i + 1 : i + 1 + NEGATION_WINDOW]
            matched = False
            for offset, word in enumerate(window):
                concept = CONCEPT_WORDS.get(word)
                if concept is not None:
                    if concept not in excluded:
                        excluded.append(concept)
                    dropped.extend(tokens[i : i + 1 + offset + 1])
                    i += offset + 2
                    matched = True
                    break
            if matched:
                continue
            # A negation with nothing recognised after it. The word itself still goes, so
            # "no" does not end up in the tsquery as a search term.
            dropped.append(token)
            i += 1
            continue
        keep.append(token)
        i += 1

    kind = _kind_of(keep)
    text = " ".join(
        w for w in keep if w not in FILLER and w not in VIDEO_WORDS and w not in PHOTO_WORDS
    )
    # Every word was filler. Better to search the original than to search nothing.
    if not text:
        text = " ".join(keep) or raw.strip().lower()

    return ParsedQuery(
        text=text,
        excluded=tuple(excluded),
        kind=kind,
        dropped=tuple(dropped),
    )


def _kind_of(tokens: list[str]) -> str | None:
    wants_video = any(t in VIDEO_WORDS for t in tokens)
    wants_photo = any(t in PHOTO_WORDS for t in tokens)
    if wants_video and not wants_photo:
        return "video"
    if wants_photo and not wants_video:
        return "photo"
    # Both or neither, so do not filter.
    return None
