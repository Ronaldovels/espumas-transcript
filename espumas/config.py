"""Carrega a configuração (config.yaml) com valores padrão sensatos."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS: dict = {
    # Usuário do Discord -> apelido no relatório (texto) ou
    # {"apelido": "Ronaldo", "riot": "Nome#TAG"} para ligar com a partida.
    "jogadores": {},
    # Dados da partida via HenrikDev API (não oficial). Chave grátis no Discord deles.
    "riot": {
        "api_key": "",
        "riot_id": "",  # "Nome#TAG" de quem busca as partidas
        "regiao": "br",
        "plataforma": "pc",
    },
    # Sincronização da gravação com a partida.
    "sinc": {
        # Palavra falada na call no momento combinado (padrão: barreira caindo no round 1).
        "palavra": "espumas",
        "round": 1,
        "fase": "round",  # "round" (relógio do round) ou "buy" (relógio da fase de compra)
        "restantes_s": 100,  # quanto o relógio mostrava (100 = 1:40 = barreira caindo)
        # Só vale a primeira ocorrência no começo; repetições depois são ignoradas.
        "janela_inicio_s": 900,  # sem horário da partida: primeiros 15 min da gravação
        "janela_relogio_s": 240,  # com horário: ±4 min de onde o round 1 deveria estar
        "buy_fase_s": 30,
        # Ajuste fino automático pelas mortes (quem morre costuma falar logo depois).
        "ajuste_max_s": 20,
    },
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
    # Gera audio.webm (todas as faixas misturadas) para ouvir trechos no relatório.
    "audio_relatorio": True,
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


def save_config(cfg: dict, path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _entry(players: dict | None, discord: str):
    if not players:
        return None
    if discord in players:
        return players[discord]
    low = discord.lower()
    for k, v in players.items():
        # Aceita a chave escrita como no Discord ("ronaldo.vels") ou como no arquivo.
        if k.lower() == low or _safe(k).lower() == _safe(discord).lower():
            return v
    return None


def _safe(name: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]", "_", name)


def player_alias(players: dict | None, discord: str) -> str:
    e = _entry(players, discord)
    if isinstance(e, dict):
        return e.get("apelido") or discord
    return e or discord


def player_riot(players: dict | None, discord: str) -> str | None:
    e = _entry(players, discord)
    return e.get("riot") if isinstance(e, dict) else None
