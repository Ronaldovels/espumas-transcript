"""Carrega a configuração (config.yaml) com valores padrão sensatos."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS: dict = {
    # Mapeia o nome que aparece no arquivo do Craig -> apelido no relatório.
    # Ex.: {"ronaldovels": "Ronaldo"}. Jogadores não listados usam o nome do arquivo.
    "jogadores": {},
    "transcricao": {
        "modelo": "large-v3-turbo",
        "idioma": "pt",
        "dispositivo": "cuda",  # "cuda" ou "cpu"
        "compute_type": "float16",  # float16 (GPU), int8_float16 (GPU, menos VRAM), int8 (CPU)
        "beam_size": 5,
        # Descarta segmentos em que o modelo acha que não houve fala.
        "max_no_speech_prob": 0.6,
        "min_avg_logprob": -1.0,
    },
    # Termos extras somados ao glossário de Valorant embutido.
    "vocabulario": [],
    # Correções forçadas: "texto errado" -> "texto certo" (sem diferenciar maiúsculas).
    "correcoes": {},
    "metricas": {
        # Duas falas do mesmo jogador separadas por menos que isso viram uma só.
        "juntar_gap_s": 0.6,
        # Sobreposição menor que isso é ignorada (respirações, cortes de PTT).
        "min_sobreposicao_s": 0.3,
        # Fala curta que não conta como interrupção ("uhum", "ok", "boa").
        "backchannel_max_palavras": 2,
        "backchannel_max_s": 0.8,
        # Callout acima disso é marcado como longo.
        "callout_longo_s": 6.0,
        "callout_longo_palavras": 18,
        # Ordens de jogadores diferentes dentro dessa janela = possível conflito.
        "janela_ordens_s": 3.0,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> dict:
    if path is None:
        return copy.deepcopy(DEFAULTS)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config não encontrada: {p}")
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _merge(DEFAULTS, data)
