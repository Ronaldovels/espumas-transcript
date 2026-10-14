"""Junta todas as análises salvas para mostrar a evolução do time e de cada jogador."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

# (chave, rótulo, unidade, melhor quando) — "menor" ou "maior"
METRICAS_TIME = [
    ("interrupcoes_round", "Interrupções por round", "", "menor"),
    ("sobreposicao_pct", "Fala sobreposta", "%", "menor"),
    ("fala_morto_round", "Fala de morto por round", "s", "menor"),
    ("clutch_silencio_pct", "Clutches em silêncio", "%", "maior"),
    ("call_seguida_pct", "Call seguida na execução", "%", "maior"),
    ("compra_dividida_pct", "Rounds com compra dividida", "%", "menor"),
]
METRICAS_JOGADOR = [
    ("participacao_pct", "Participação na fala", "%", None),
    ("interrompeu_round", "Interrompeu por round", "", "menor"),
    ("cortado_round", "Foi cortado por round", "", "menor"),
    ("fala_morto_round", "Fala de morto por round", "s", "menor"),
    ("falas_longas", "Falas longas", "", "menor"),
]


def _r(v, n=2):
    return None if v is None else round(v, n)


def _pct(parte, total):
    return None if not total else 100.0 * parte / total


def resumo_partida(aid: str, d: dict) -> dict:
    meta = d.get("meta") or {}
    met = d.get("metricas") or {}
    res = met.get("resumo") or {}
    p = d.get("partida") or {}
    jogo = d.get("jogo") or {}
    rounds = len(jogo.get("rounds") or []) or None

    clutch = jogo.get("clutches") or []
    ce = [c for c in jogo.get("call_execucao") or []
          if c["status"] in ("seguiu a call", "mudou a call e seguiu", "plantou em outro site")]
    cp = jogo.get("compras") or []
    morto_pj = (jogo.get("fala_de_morto") or {}).get("por_jogador") or {}

    placar = p.get("placar")
    venceu = None
    if placar and None not in placar and placar[0] != placar[1]:
        venceu = placar[0] > placar[1]

    time_ = {
        "interrupcoes_round": _r(res.get("interrupcoes") / rounds) if rounds else None,
        "sobreposicao_pct": res.get("sobreposicao_pct_da_fala"),
        "fala_morto_round": _r(sum(x["segundos"] for x in morto_pj.values()) / rounds)
        if rounds and jogo else None,
        "clutch_silencio_pct": _r(_pct(sum(1 for c in clutch if c["silencio_ok"]), len(clutch)), 1),
        "call_seguida_pct": _r(_pct(sum(1 for c in ce if c["status"] != "plantou em outro site"),
                                    len(ce)), 1),
        "compra_dividida_pct": _r(_pct(sum(1 for c in cp if c["dividida"]), len(cp)), 1),
    }
    jogadores = {}
    for nome, j in (met.get("jogadores") or {}).items():
        if not j.get("falas") and not j.get("tempo_fala_s"):
            continue
        jogadores[nome] = {
            "participacao_pct": j.get("participacao_pct"),
            "interrompeu_round": _r(j["interrompeu"] / rounds) if rounds else None,
            "cortado_round": _r(j["foi_interrompido"] / rounds) if rounds else None,
            "fala_morto_round": _r(morto_pj.get(nome, {}).get("segundos", 0) / rounds)
            if rounds and jogo else None,
            "falas_longas": j.get("callouts_longos"),
        }
    data = p.get("inicio") or meta.get("criado_em")
    return {
        "id": aid, "nome": meta.get("nome") or aid, "data": data, "mapa": p.get("mapa"),
        "placar": placar, "venceu": venceu, "rounds": rounds, "time": time_,
        "jogadores": jogadores,
    }


def _tendencia(valores: list[float | None], melhor: str | None) -> dict | None:
    """Média das 3 últimas partidas x média das anteriores."""
    vals = [v for v in valores if v is not None]
    if len(vals) < 4 or not melhor:
        return None
    recentes, antes = vals[-3:], vals[:-3]
    a, b = statistics.mean(antes), statistics.mean(recentes)
    if a == b:
        direcao = "igual"
    else:
        subiu = b > a
        direcao = "melhorou" if subiu == (melhor == "maior") else "piorou"
    # Variação pequena (menos de 10% e menos que 0,05 absoluto) conta como estável
    if abs(b - a) < max(0.05, 0.1 * abs(a)):
        direcao = "estavel"
    return {"antes": _r(a), "recentes": _r(b), "direcao": direcao}


def coletar(saida: str | Path) -> dict:
    partidas = []
    for f in Path(saida).glob("*/analise.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        partidas.append(resumo_partida(f.parent.name, d))
    partidas.sort(key=lambda p: (p["data"] or "", p["id"]))

    time_ = []
    for chave, rotulo, unidade, melhor in METRICAS_TIME:
        serie = [p["time"][chave] for p in partidas]
        vals = [v for v in serie if v is not None]
        time_.append({"chave": chave, "rotulo": rotulo, "unidade": unidade, "melhor": melhor,
                      "serie": serie, "media": _r(statistics.mean(vals)) if vals else None,
                      "tendencia": _tendencia(serie, melhor)})

    nomes = []
    for p in partidas:
        for n in p["jogadores"]:
            if n not in nomes:
                nomes.append(n)
    # Ordem fixa por quem mais aparece: a cor segue a pessoa, não a posição no ranking.
    nomes.sort(key=lambda n: -sum(1 for p in partidas if n in p["jogadores"]))
    jogadores = []
    for n in nomes:
        metricas = {}
        for chave, rotulo, unidade, melhor in METRICAS_JOGADOR:
            serie = [p["jogadores"].get(n, {}).get(chave) for p in partidas]
            vals = [v for v in serie if v is not None]
            metricas[chave] = {"serie": serie, "media": _r(statistics.mean(vals)) if vals else None,
                               "tendencia": _tendencia(serie, melhor)}
        jogadores.append({"nome": n, "partidas": sum(1 for p in partidas if n in p["jogadores"]),
                          "metricas": metricas})

    mapas: dict[str, dict] = {}
    for p in partidas:
        if not p["mapa"]:
            continue
        m = mapas.setdefault(p["mapa"], {"mapa": p["mapa"], "partidas": 0, "vitorias": 0,
                                         "_v": {k: [] for k, *_ in METRICAS_TIME}})
        m["partidas"] += 1
        m["vitorias"] += 1 if p["venceu"] else 0
        for k, *_ in METRICAS_TIME:
            if p["time"][k] is not None:
                m["_v"][k].append(p["time"][k])
    lista_mapas = []
    for m in sorted(mapas.values(), key=lambda m: -m["partidas"]):
        v = m.pop("_v")
        m["medias"] = {k: (_r(statistics.mean(x)) if x else None) for k, x in v.items()}
        lista_mapas.append(m)

    return {
        "partidas": [{k: p[k] for k in ("id", "nome", "data", "mapa", "placar", "venceu", "rounds")}
                     for p in partidas],
        "time": time_,
        "jogadores": jogadores,
        "metricas_jogador": [{"chave": k, "rotulo": r, "unidade": u, "melhor": b}
                             for k, r, u, b in METRICAS_JOGADOR],
        "mapas": lista_mapas,
    }
