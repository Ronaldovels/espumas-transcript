"""Junta as transcrições das faixas numa linha do tempo única."""

from __future__ import annotations

from typing import Callable

from .models import Utterance, Word


def segments_to_utterances(player: str, segments: list[dict], gap_s: float,
                           corrector: Callable[[str], str] | None = None) -> list[Utterance]:
    """Quebra os segmentos do Whisper em falas pelas pausas entre palavras.

    O Whisper às vezes junta duas falas separadas por silêncio num segmento só;
    usar o tempo de cada palavra dá limites bem mais fiéis para medir sobreposição.
    """
    words: list[Word] = []
    for seg in segments:
        if seg.get("words"):
            words.extend(Word(**w) for w in seg["words"])
        else:  # sem tempo por palavra: trata o segmento inteiro como uma "palavra"
            words.append(Word(seg["start"], seg["end"], seg["text"]))
    words.sort(key=lambda w: w.start)

    utts: list[Utterance] = []
    cur: list[Word] = []
    for w in words:
        if cur and w.start - cur[-1].end > gap_s:
            utts.append(_make(player, cur, corrector))
            cur = []
        cur.append(w)
    if cur:
        utts.append(_make(player, cur, corrector))
    return [u for u in utts if u.text]


def _make(player: str, words: list[Word], corrector) -> Utterance:
    text = "".join(w.text if w.text.startswith(" ") else " " + w.text for w in words).strip()
    text = " ".join(text.split())
    if corrector:
        text = corrector(text)
    return Utterance(player=player, start=words[0].start, end=words[-1].end,
                     text=text, words=list(words))


def merge_timeline(per_player: dict[str, list[Utterance]]) -> list[Utterance]:
    allu = [u for utts in per_player.values() for u in utts]
    return sorted(allu, key=lambda u: (u.start, u.end, u.player))
