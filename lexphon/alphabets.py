from __future__ import annotations

import re

from .errors import UnsupportedAlphabetError

_ARPA_CONSONANTS = {
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p",
    "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}
_ARPA_VOWELS = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u", "AX": "ə", "AXR": "ɚ", "IX": "ɨ",
}
_ARPA_TOKEN = re.compile(r"^(?P<phoneme>[A-Z]+)(?P<stress>[012])?$")


def arpabet_to_ipa(value: str) -> str:
    """Convert CMU-style ARPABET to broad IPA.

    Stress is placed at the start of the approximate syllable onset: before the
    word for the first vowel, or before the consonant sequence following the
    previous vowel. This is deliberately a pronunciation normalization layer,
    not a full English syllabifier.
    """
    segments: list[str] = []
    vowel_indices: list[int] = []
    stressed: list[tuple[int, str]] = []
    for raw in value.split():
        match = _ARPA_TOKEN.fullmatch(raw.upper())
        if not match:
            raise UnsupportedAlphabetError(f"invalid ARPABET token: {raw!r}")
        symbol = match.group("phoneme")
        stress = match.group("stress")
        if symbol in _ARPA_VOWELS:
            ipa = _ARPA_VOWELS[symbol]
            if symbol == "AH" and stress == "0":
                ipa = "ə"
            elif symbol == "ER" and stress == "0":
                ipa = "ɚ"
            index = len(segments)
            segments.append(ipa)
            if stress in {"1", "2"}:
                stressed.append((len(vowel_indices), "ˈ" if stress == "1" else "ˌ"))
            vowel_indices.append(index)
        elif symbol in _ARPA_CONSONANTS:
            if stress is not None:
                raise UnsupportedAlphabetError(f"stress on ARPABET consonant: {raw!r}")
            segments.append(_ARPA_CONSONANTS[symbol])
        else:
            raise UnsupportedAlphabetError(f"unsupported ARPABET phoneme: {symbol}")

    insertions: dict[int, list[str]] = {}
    for vowel_ordinal, marker in stressed:
        position = 0 if vowel_ordinal == 0 else vowel_indices[vowel_ordinal - 1] + 1
        insertions.setdefault(position, []).append(marker)

    output: list[str] = []
    for index, segment in enumerate(segments):
        output.extend(insertions.get(index, ()))
        output.append(segment)
    output.extend(insertions.get(len(segments), ()))
    return "".join(output)


def to_ipa(value: str, encoding: str) -> str:
    key = encoding.casefold().replace("-", "")
    if key in {"ipa", "unicodeipa"}:
        return value
    if key in {"arpabet", "cmu", "cmudict"}:
        return arpabet_to_ipa(value)
    raise UnsupportedAlphabetError(f"unsupported pronunciation encoding: {encoding!r}")
