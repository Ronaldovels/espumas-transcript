"""Cruza a call com a partida: fase do round, quem estava morto, resultado de cada round."""

from __future__ import annotations

import statistics

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
    res["destaques"] = game_insights(res)
    return res


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
    if g["jogadores_sem_riot"]:
        out.append("Sem ligação com a conta da Riot (fala de morto não calculada): "
                   + ", ".join(g["jogadores_sem_riot"]) + ".")
    return out
