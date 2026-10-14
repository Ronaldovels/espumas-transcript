"""Gera um relatório de exemplo com partida e call inventadas (sem GPU, áudio ou API).

Uso:  python exemplos/demo.py   ->  saida/demo/relatorio.html
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espumas import exemplo  # noqa: E402
from espumas.config import load_config  # noqa: E402
from espumas.pipeline import build_outputs  # noqa: E402
from espumas.riot import normalize_match  # noqa: E402

OFFSET = 312.4


def main(out: Path = Path("saida/demo")) -> Path:
    raw = exemplo.raw_match()
    match = normalize_match(raw, exemplo.NOSSOS[0][1])
    per_player = exemplo.call_sintetica(raw, OFFSET)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg["transcricao"]["modelo"] = "demo (sem áudio)"
    meta = {
        "nome": "Demo — Ascent",
        "modelo": "demo (sem áudio)",
        "jogadores": [a for a, _, _ in exemplo.NOSSOS],
        "discord": {a: a.lower() for a, _, _ in exemplo.NOSSOS},
        "gravacao_inicio": exemplo.craig_inicio(OFFSET, erro_s=12).isoformat(),
        "riot_map": {a: r for a, r, _ in exemplo.NOSSOS},
    }
    duracao = OFFSET + match["duracao_s"] + 60
    _audio_de_exemplo(per_player, out, duracao)
    return build_outputs(per_player, cfg, out, meta, duracao, match)


def _audio_de_exemplo(per_player, out: Path, duracao: float) -> None:
    """Um tom diferente por jogador em cada fala, para testar o player do relatório."""
    try:
        import tempfile

        import numpy as np
        import soundfile as sf

        from espumas.audio import mix_tracks
    except ImportError:
        return
    sr = 16_000
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, (p, utts) in enumerate(per_player.items()):
            x = np.zeros(int(duracao * sr), dtype=np.float32)
            for u in utts:
                a, b = int(u.start * sr), int(u.end * sr)
                t = np.arange(b - a) / sr
                x[a:b] = 0.2 * np.sin(2 * np.pi * (220 + 70 * i) * t)
            f = Path(tmp) / f"{i + 1}-{p}.flac"
            sf.write(f, x, sr)
            paths.append(str(f))
        mix_tracks(paths, out)


if __name__ == "__main__":
    print(f"Relatório de exemplo: {main().resolve()}")
