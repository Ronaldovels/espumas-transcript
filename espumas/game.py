"""Cruza a call com a partida: fase do round, quem estava morto, resultado de cada round."""

from __future__ import annotations

import re
import statistics

from .metrics import site_mentions
from .models import Utterance

ROUND_S = 100.0  # duração do round após a barreira
SPIKE_S = 45.0  # tempo da spike após plantada


def round_windows(match: dict, offset: float, buy_s: float) -> list[dict]:
    """Janelas de cada round no relógio da GRAVAÇÃO."""
    t0_is_buy = match.get("t0_round", "buy") == "buy"
    kills_by_round: dict[int, list[dict]] = {}
    for k in match.get("kills") or []:
        kills_by_round.setdefault(k["round"], []).append(k)

    out = []
    for r in match.get("rounds") or []:
        if r["inicio_s"] is None:
            continue
        R = r["inicio_s"]
        buy_start, barrier = (R, R + buy_s) if t0_is_buy else (R - buy_s, R)
        ks = kills_by_round.get(r["n"], [])
        plant, defuse = r.get("plant"), r.get("defuse")
        if defuse and defuse.get("t_s") is not None:
            fim = defuse["t_s"]
        elif plant and plant.get("t_s") is not None and r.get("vencedor") == plant.get("time"):
            fim = plant["t_s"] + SPIKE_S  # explodiu (ou o time que plantou ganhou)
        elif ks:
            fim = max(k["t_s"] for k in ks)
        else:
            fim = barrier + ROUND_S
        limite = barrier + ROUND_S + (SPIKE_S if plant else 0)
        fim = min(max(fim, barrier), limite)
        out.append({
            "n": r["n"], "ganhamos": r.get("ganhamos"), "estimado": r.get("inicio_estimado"),
            "buy": buy_start + offset, "barreira": barrier + offset, "fim": fim + offset,
            "plant": (plant["t_s"] + offset) if plant and plant.get("t_s") is not None else None,
            "site": plant.get("site") if plant else None,
            "defuse": (defuse["t_s"] + offset) if defuse and defuse.get("t_s") is not None else None,
        })
    return out


def phase_at(t: float, wins: list[dict]) -> tuple[int | None, str]:
    """(round, fase) para um instante da gravação."""
    if not wins or t < wins[0]["buy"]:
        return None, "pre_jogo"
    for i, w in enumerate(wins):
        nxt = wins[i + 1]["buy"] if i + 1 < len(wins) else w["fim"] + 10
        if w["buy"] <= t < w["barreira"]:
            return w["n"], "buy"
        if w["barreira"] <= t <= w["fim"]:
            return w["n"], "ativo"
        if w["fim"] < t < nxt:
            return w["n"], "pos_round"
    return None, "pos_jogo"


FASE_LABEL = {"pre_jogo": "antes da partida", "buy": "fase de compra", "ativo": "round ativo",
              "pos_round": "fim de round", "pos_jogo": "depois da partida"}


def compute_game_metrics(timeline: list[Utterance], match: dict, sync: dict,
                         riot_map: dict[str, str], overlaps: list[dict], cfg_sinc: dict) -> dict:
    offset = sync["offset_s"]
    buy_s = float(cfg_sinc["buy_fase_s"])
    wins = round_windows(match, offset, buy_s)
    our_team = match.get("nosso_time")
    riot_to_player = {v.lower(): k for k, v in riot_map.items() if v}

    # Mortes do nosso time (no relógio da gravação), por round
    deaths: dict[int, dict[str, float]] = {}
    kill_marks = []
    for k in match.get("kills") or []:
        t = k["t_s"] + offset
        nossa = k.get("killer_time") == our_team
        kill_marks.append({"t": round(t, 2), "nossa": nossa, "round": k["round"],
                           "killer": k["killer"], "vitima": k["vitima"]})
        p = riot_to_player.get((k.get("vitima") or "").lower())
        if p:
            deaths.setdefault(k["round"], {})[p] = t

    mapped = set(riot_to_player.values())

    contexto = []
    fase_s = {f: 0.0 for f in FASE_LABEL}
    morto_por_jog: dict[str, dict] = {}
    morto_eventos = []
    for u in timeline:
        rnd, fase = phase_at(u.start, wins)
        fase_s[fase] += u.duration
        morto = False
        if rnd is not None and fase == "ativo":
            td = deaths.get(rnd, {}).get(u.player)
            w = next(x for x in wins if x["n"] == rnd)
            vivos = [p for p in mapped if p != u.player
                     and deaths.get(rnd, {}).get(p, float("inf")) > u.start]
            if td is not None and td <= u.start <= w["fim"] and vivos:
                morto = True
                d = morto_por_jog.setdefault(u.player, {"falas": 0, "segundos": 0.0,
                                                        "por_cima_de_vivo": 0})
                d["falas"] += 1
                d["segundos"] += u.duration
                # Falou por cima de alguém vivo?
                por_cima = [o for o in timeline if o.player in vivos and o.start < u.end
                            and o.end > u.start
                            and deaths.get(rnd, {}).get(o.player, float("inf")) > o.start]
                if por_cima:
                    d["por_cima_de_vivo"] += 1
                morto_eventos.append({"t": round(u.start, 2), "round": rnd, "jogador": u.player,
                                      "texto": u.text, "duracao": round(u.duration, 1),
                                      "por_cima_de": sorted({o.player for o in por_cima})})
        contexto.append({"round": rnd, "fase": fase, "morto": morto})

    # Por round
    por_round = []
    for w in wins:
        n = w["n"]
        utts = [(u, c) for u, c in zip(timeline, contexto) if c["round"] == n]
        ativo = [u for u, c in utts if c["fase"] == "ativo"]
        ints = [e for e in overlaps if e["tipo"] == "interrupcao"
                and w["barreira"] <= e["start"] <= w["fim"]]
        ks = [k for k in kill_marks if k["round"] == n]
        por_round.append({
            "n": n,
            "ganhamos": w["ganhamos"],
            "site": w["site"],
            "fala_ativo_s": round(sum(u.duration for u in ativo), 1),
            "fala_buy_s": round(sum(u.duration for u, c in utts if c["fase"] == "buy"), 1),
            "interrupcoes": len(ints),
            "fala_morto_s": round(sum(u.duration for u, c in utts if c["morto"]), 1),
            "kills": sum(1 for k in ks if k["nossa"]),
            "mortes": sum(1 for k in ks if not k["nossa"]),
            "estimado": w["estimado"],
        })

    def media(rows, key):
        vals = [r[key] for r in rows]
        return round(statistics.mean(vals), 2) if vals else None

    ganhos = [r for r in por_round if r["ganhamos"] is True]
    perdidos = [r for r in por_round if r["ganhamos"] is False]
    comparacao = {
        k: {"ganhos": media(ganhos, k), "perdidos": media(perdidos, k)}
        for k in ("interrupcoes", "fala_ativo_s", "fala_morto_s", "fala_buy_s")
    }

    total = sum(fase_s.values()) or 1.0
    for d in morto_por_jog.values():
        d["segundos"] = round(d["segundos"], 1)

    res = {
        "rounds": por_round,
        "janelas": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in w.items()}
                    for w in wins],
        "kills": kill_marks,
        "fala_por_fase_pct": {f: round(100 * s / total, 1) for f, s in fase_s.items()},
        "fala_de_morto": {"por_jogador": morto_por_jog, "eventos": morto_eventos},
        "ganhos_x_perdidos": comparacao,
        "contexto_falas": contexto,
        "jogadores_sem_riot": sorted({u.player for u in timeline} - mapped),
    }
    our_roster = [p["riot"] for p in match.get("jogadores") or [] if p.get("time") == our_team]
    res["clutches"] = clutches(timeline, match, wins, offset, riot_map, our_roster)
    res["call_execucao"] = call_x_execucao(timeline, match, wins)
    res["compras"] = compras(timeline, match, wins)
    res["destaques"] = game_insights(res)
    return res


# ------------------------------------------------------------------ clutch

def clutches(timeline: list[Utterance], match: dict, wins: list[dict], offset: float,
             riot_map: dict[str, str], roster: list[str]) -> list[dict]:
    """Momentos com um só vivo do nosso time: quanto os outros falaram (e por cima dele)."""
    our_team = match.get("nosso_time")
    riot_to_player = {v.lower(): k for k, v in riot_map.items() if v}
    out = []
    for w in wins:
        ks = [k for k in match.get("kills") or [] if k["round"] == w["n"]]
        mortos, inimigos_mortos = [], 0
        inicio = None
        for k in ks:
            if k.get("vitima_time") == our_team:
                mortos.append(k["vitima"])
            else:
                inimigos_mortos += 1
            if len(mortos) == len(roster) - 1 and inimigos_mortos < 5 and inicio is None:
                inicio = k["t_s"] + offset
                contra = 5 - inimigos_mortos
                break
        if inicio is None or len(roster) < 2 or w["fim"] - inicio < 1.0:
            continue
        vivo_riot = next((r for r in roster if r not in mortos), None)
        vivo = riot_to_player.get((vivo_riot or "").lower())
        fim = max(w["fim"], inicio)
        outros = [u for u in timeline if u.player != vivo and u.end > inicio and u.start < fim]
        fala_outros = sum(min(u.end, fim) - max(u.start, inicio) for u in outros)
        dele = [u for u in timeline if u.player == vivo and u.end > inicio and u.start < fim]
        por_cima = sum(1 for o in outros if any(o.start < d.end and o.end > d.start for d in dele))
        out.append({
            "round": w["n"], "t": round(inicio, 2), "duracao_s": round(fim - inicio, 1),
            "jogador": vivo, "riot": vivo_riot, "contra": contra, "ganhamos": w["ganhamos"],
            "fala_outros_s": round(fala_outros, 1), "falas_outros": len(outros),
            "por_cima_dele": por_cima,
            "silencio_ok": fala_outros < 1.5 and por_cima == 0,
        })
    return out


# ------------------------------------------------------------------ call x execução

_CALL_RE = re.compile(r"(?<!\w)(vamo|vamos|bora|vai|vão|execute|exec|executa|rush|fake|entra|"
                      r"plant[ao]|roda|gira|rotate|joga)(?!\w)", re.IGNORECASE)


def call_x_execucao(timeline: list[Utterance], match: dict, wins: list[dict]) -> list[dict]:
    """Nos rounds de ataque: o site chamado bate com onde a spike foi plantada?"""
    rounds = {r["n"]: r for r in match.get("rounds") or []}
    out = []
    for i, w in enumerate(wins):
        r = rounds.get(w["n"], {})
        if r.get("lado") != "ataque":
            continue
        ini = wins[i - 1]["fim"] if i > 0 else w["buy"] - 20
        plant = r.get("plant") if (r.get("plant") or {}).get("time") == match.get("nosso_time") else None
        ate = w["plant"] if plant and w.get("plant") is not None else w["fim"]
        calls = []
        for u in timeline:
            if ini <= u.start <= ate and _CALL_RE.search(u.text):
                for site in site_mentions(u.text):
                    calls.append({"t": round(u.start, 2), "jogador": u.player, "site": site,
                                  "texto": u.text})
        distintos = list(dict.fromkeys(c["site"] for c in calls))
        final = calls[-1]["site"] if calls else None
        site_plant = plant.get("site") if plant else None
        if not calls:
            status = "sem call"
        elif not site_plant:
            status = "sem plant"
        elif site_plant == final:
            status = "seguiu a call" if len(distintos) == 1 else "mudou a call e seguiu"
        else:
            status = "plantou em outro site"
        out.append({"round": w["n"], "ganhamos": w["ganhamos"], "calls": calls,
                    "call_inicial": calls[0]["site"] if calls else None, "call_final": final,
                    "site_plant": site_plant, "status": status})
    return out


# ------------------------------------------------------------------ compras

ECO_MAX = 1600  # loadout abaixo disso = economizando
FULL_MIN = 3500  # loadout a partir disso = compra completa

_COMPRA_RE = [
    ("forca", re.compile(r"(?<!\w)(for[cç]a|for[cç]ar|forçando|force|forcing)(?!\w)", re.I)),
    ("eco", re.compile(r"(?<!\w)(eco|salva|salvar|save|economiza)(?!\w)", re.I)),
    ("full", re.compile(r"(?<!\w)(full|compra tudo|full buy|compra completa)(?!\w)", re.I)),
]


def classe_compra(loadout: int | None) -> str | None:
    if loadout is None:
        return None
    if loadout < ECO_MAX:
        return "eco"
    if loadout >= FULL_MIN:
        return "full"
    return "meio"


def _pistol_rounds(match: dict) -> set[int]:
    from .riot import half_length

    half = half_length(match.get("modo"))
    return {1, half + 1}


def compras(timeline: list[Utterance], match: dict, wins: list[dict]) -> list[dict]:
    """O que foi combinado na compra x o que cada um comprou de verdade."""
    rounds = {r["n"]: r for r in match.get("rounds") or []}
    pistols = _pistol_rounds(match)
    out = []
    for i, w in enumerate(wins):
        r = rounds.get(w["n"], {})
        eco = r.get("economia") or {}
        if not eco or w["n"] in pistols:
            continue
        classes = {riot: classe_compra(v.get("loadout")) for riot, v in eco.items()}
        cont = {c: sum(1 for x in classes.values() if x == c) for c in ("full", "meio", "eco")}
        ini = wins[i - 1]["fim"] if i > 0 else w["buy"]
        call = None
        for u in timeline:
            if ini <= u.start < w["barreira"]:
                tipos = [nome for nome, rx in _COMPRA_RE if rx.search(u.text)]
                # "força ou salva?" é pergunta, não combinado: ignora falas ambíguas.
                if len(tipos) == 1:
                    call = {"tipo": tipos[0], "jogador": u.player, "texto": u.text,
                            "t": round(u.start, 2)}
        dividida = cont["eco"] >= 2 and cont["full"] >= 2
        maioria = max(cont, key=cont.get)
        seguiu = None
        if call:
            alvo = {"forca": ("meio", "full"), "eco": ("eco",), "full": ("full",)}[call["tipo"]]
            seguiu = sum(cont[a] for a in alvo) >= 4
        out.append({"round": w["n"], "ganhamos": w["ganhamos"], "contagem": cont,
                    "maioria": maioria, "dividida": dividida, "call": call, "seguiu": seguiu,
                    "jogadores": {riot: {"classe": classes[riot], **v} for riot, v in eco.items()}})
    return out


def game_insights(g: dict) -> list[str]:
    out = []
    cmp_ = g["ganhos_x_perdidos"]
    i = cmp_["interrupcoes"]
    if i["ganhos"] is not None and i["perdidos"] is not None and i["perdidos"] >= i["ganhos"] + 1:
        out.append(f"Rounds perdidos tiveram em média {i['perdidos']} interrupções durante o round, "
                   f"contra {i['ganhos']} nos ganhos.")
    m = cmp_["fala_morto_s"]
    if m["ganhos"] is not None and m["perdidos"] is not None and m["perdidos"] >= m["ganhos"] + 2:
        out.append(f"Nos rounds perdidos, mortos falaram {m['perdidos']}s por round em média "
                   f"(nos ganhos: {m['ganhos']}s).")
    pj = g["fala_de_morto"]["por_jogador"]
    if pj:
        top = max(pj.items(), key=lambda kv: kv[1]["por_cima_de_vivo"])
        if top[1]["por_cima_de_vivo"] >= 3:
            out.append(f"{top[0]} falou depois de morrer por cima de jogador vivo "
                       f"{top[1]['por_cima_de_vivo']} vezes.")
    buy = g["fala_por_fase_pct"].get("buy", 0)
    if buy >= 45:
        out.append(f"{buy}% da fala aconteceu na fase de compra — o round ativo ficou mais limpo.")
    cl = g.get("clutches") or []
    if cl:
        barulho = [c for c in cl if not c["silencio_ok"]]
        if barulho:
            out.append(f"Em {len(barulho)} de {len(cl)} clutches o time falou enquanto um jogava "
                       f"sozinho (média de {statistics.mean(c['fala_outros_s'] for c in barulho):.1f}s).")
        else:
            out.append(f"Nos {len(cl)} clutches o time ficou em silêncio. Boa.")
    ce = [c for c in g.get("call_execucao") or [] if c["status"] in
          ("seguiu a call", "mudou a call e seguiu", "plantou em outro site")]
    outro = [c for c in ce if c["status"] == "plantou em outro site"]
    if outro:
        out.append(f"Em {len(outro)} de {len(ce)} rounds de ataque com call e plant, a spike foi "
                   "plantada em outro site.")
    div = [c for c in g.get("compras") or [] if c["dividida"]]
    if div:
        perdidos = sum(1 for c in div if c["ganhamos"] is False)
        out.append(f"{len(div)} round(s) com compra dividida (parte comprou, parte salvou); "
                   f"{perdidos} perdido(s).")
    if g["jogadores_sem_riot"]:
        out.append("Sem ligação com a conta da Riot (fala de morto não calculada): "
                   + ", ".join(g["jogadores_sem_riot"]) + ".")
    return out
