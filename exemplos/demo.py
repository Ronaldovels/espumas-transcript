"""Gera um relatório de exemplo com uma call inventada (não precisa de GPU nem áudio).

Uso:  python exemplos/demo.py   ->  saida/demo/relatorio.html
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espumas.config import load_config  # noqa: E402
from espumas.models import Utterance, Word  # noqa: E402
from espumas.pipeline import build_outputs  # noqa: E402

JOGADORES = ["Ronaldo", "Kaio", "Bia", "Duda", "Léo"]
FALAS = {
    "Ronaldo": ["dois no B main um tapado", "roda pro B roda", "eu tô de Operator no mid",
                "Sova joga o drone no A", "segura o heaven", "vamo de execute no A"],
    "Kaio": ["mano para de pushar sozinho", "um no link", "boa boa", "ele tá lit cem",
             "vai pro A agora", "quem tem flash pra mim", "nossa que round horrível cara sério"],
    "Bia": ["Killjoy tá com a ult", "spike plantado default", "um no CT", "trade", "eco esse round"],
    "Duda": ["uhum", "ok", "vou lurkar no B", "Jett deu dash no short"],
    "Léo": ["tô sem grana", "força ou salva", "galera vamos focar ninguém tá falando nada de útil "
            "aqui sério a gente precisa trocar informação direito senão não dá"],
}


def _utt(player: str, start: float, text: str) -> Utterance:
    ws = text.split()
    dur = 0.32 * len(ws) + 0.2
    step = dur / len(ws)
    words = [Word(start + i * step, start + (i + 1) * step, " " + w) for i, w in enumerate(ws)]
    return Utterance(player, start, start + dur, text, words)


def main() -> None:
    random.seed(7)
    per_player: dict[str, list[Utterance]] = {p: [] for p in JOGADORES}
    duracao = 8 * 60.0
    t = 3.0
    while t < duracao - 10:
        p = random.choices(JOGADORES, weights=[5, 4, 3, 1, 2])[0]
        u = _utt(p, t, random.choice(FALAS[p]))
        if not per_player[p] or per_player[p][-1].end < u.start:
            per_player[p].append(u)
        t += random.choice([0.4, 0.9, 1.5, 2.5, 4, 6])  # às vezes entra por cima

    out = Path("saida/demo")
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg["transcricao"]["modelo"] = "demo (sem áudio)"
    html = build_outputs(per_player, JOGADORES, cfg, out, "Demo — Ascent 13-11", duracao)
    print(f"Relatório de exemplo: {html.resolve()}")


if __name__ == "__main__":
    main()
