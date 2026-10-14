"""Estruturas de dados compartilhadas pelo pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float = 1.0


@dataclass
class Utterance:
    """Um trecho contínuo de fala de um jogador."""

    player: str
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def n_words(self) -> int:
        return len(self.words) if self.words else len(self.text.split())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Utterance":
        words = [Word(**w) for w in d.get("words", [])]
        return cls(
            player=d["player"],
            start=float(d["start"]),
            end=float(d["end"]),
            text=d["text"],
            words=words,
        )


@dataclass
class Track:
    """Uma faixa de áudio de um jogador (ex.: arquivo do Craig)."""

    player: str  # nome exibido (apelido)
    path: str
    discord: str = ""  # usuário do Discord
