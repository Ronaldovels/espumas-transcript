"""Sincroniza o relógio da gravação (Craig) com o relógio da partida (API).

    tempo_na_gravação = tempo_na_partida + offset

Ordem de preferência para achar o offset:
1. manual   — o usuário informa em que segundo da gravação foi o momento combinado;
2. palavra  — a palavra de sinc ("espumas") falada no momento combinado. Vale UMA
              ocorrência só, perto do começo; qualquer repetição depois é ignorada;
3. relógio  — horário de início do Craig (info.txt) x horário de início da partida (API).

Depois, um ajuste fino opcional usa as mortes do nosso time: quem morre quase sempre fala
logo em seguida. O ajuste só é aplicado quando os dados concordam com folga.
"""

from __future__ import annotations

import unicodedata
from bisect import bisect_left
from datetime import datetime

from rapidfuzz import fuzz

from .models import Utterance


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s if c.isalnum())


def anchor_match_time(match: dict, cfg: dict) -> float:
    """Instante, no relógio da partida, do momento combinado (ex.: barreira no round 1)."""
    n = int(cfg["round"])
    rounds = match.get("rounds") or []
    if not 1 <= n <= len(rounds) or rounds[n - 1]["inicio_s"] is None:
        raise ValueError(f"Round {n} não existe nos dados da partida.")
    r0 = rounds[n - 1]["inicio_s"]
    buy = float(cfg["buy_fase_s"])
    restantes = float(cfg["restantes_s"])
    t0_is_buy = match.get("t0_round", "buy") == "buy"
    if cfg["fase"] == "buy":
        desde_inicio_buy = buy - restantes
        return r0 + desde_inicio_buy - (0 if t0_is_buy else buy)
    desde_barreira = 100 - restantes
    return r0 + (buy if t0_is_buy else 0) + desde_barreira


def clock_offset(rec_start: datetime | None, match_start: datetime | None) -> float | None:
    if not rec_start or not match_start:
        return None
    return (match_start - rec_start).total_seconds()


def find_word(timeline: list[Utterance], palavra: str, limiar: int = 80) -> list[dict]:
    """Todas as ocorrências da palavra (com tolerância a erro de transcrição)."""
    alvo = _norm(palavra)
    out = []
    for u in timeline:
        words = u.words or []
        for w in words:
            tok = _norm(w.text)
            if not tok or abs(len(tok) - len(alvo)) > 2:
                continue
            if tok == alvo or fuzz.ratio(tok, alvo) >= limiar:
                out.append({"t": round(w.start, 2), "jogador": u.player, "texto": u.text})
    out.sort(key=lambda c: c["t"])
    return out


def death_speech_score(offset: float, deaths: list[tuple[str, float]],
                       onsets: dict[str, list[float]], lo: float = 0.1,
                       hi: float = 2.0) -> float:
    """Fração das mortes em que o jogador que morreu começou a falar logo depois."""
    if not deaths:
        return 0.0
    hits = 0
    for player, t in deaths:
        arr = onsets.get(player) or []
        a = t + offset + lo
        i = bisect_left(arr, a)
        if i < len(arr) and arr[i] <= t + offset + hi:
            hits += 1
    return hits / len(deaths)


def _deaths_and_onsets(timeline: list[Utterance], match: dict,
                       riot_map: dict[str, str]) -> tuple[list, dict]:
    riot_to_player = {v.lower(): k for k, v in riot_map.items() if v}
    deaths = []
    for k in match.get("kills") or []:
        p = riot_to_player.get((k.get("vitima") or "").lower())
        if p:
            deaths.append((p, k["t_s"]))
    onsets: dict[str, list[float]] = {}
    for u in timeline:
        onsets.setdefault(u.player, []).append(u.start)
    for v in onsets.values():
        v.sort()
    return deaths, onsets


def refine(base: float, deaths, onsets, max_shift: float, step: float = 0.25) -> dict:
    base_score = death_speech_score(base, deaths, onsets)
    n = int(max_shift / step)
    grid = [base + i * step for i in range(-n, n + 1)]
    scores = [death_speech_score(off, deaths, onsets) for off in grid]
    best_score = max(scores) if scores else base_score
    # Vários deslocamentos vizinhos empatam (platô). Pega o platô mais perto do valor
    # original e usa o meio dele.
    runs, cur = [], []
    for off, sc in zip(grid, scores):
        if sc >= best_score - 1e-9:
            cur.append(off)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    run = min(runs, key=lambda r: min(abs(o - base) for o in r)) if runs else [base]
    best = (run[0] + run[-1]) / 2
    apply = (len(deaths) >= 6 and best_score >= 0.4 and best_score - base_score >= 0.15)
    return {
        "aplicado": apply,
        "delta_s": round(best - base, 2) if apply else 0.0,
        "sugestao_delta_s": round(best - base, 2),
        "mortes_avaliadas": len(deaths),
        "acerto_antes": round(base_score, 2),
        "acerto_depois": round(best_score if apply else base_score, 2),
    }


def synchronize(timeline: list[Utterance], match: dict, cfg: dict, rec_start: datetime | None,
                match_start: datetime | None, riot_map: dict[str, str] | None = None,
                manual_anchor_s: float | None = None) -> dict:
    riot_map = riot_map or {}
    res: dict = {"metodo": "nenhum", "offset_s": None, "ancora": None, "ignoradas": [],
                 "relogio_offset_s": None, "ajuste": None, "avisos": []}
    try:
        t_anchor = anchor_match_time(match, cfg)
    except ValueError as e:
        res["avisos"].append(str(e))
        t_anchor = None

    clk = clock_offset(rec_start, match_start)
    res["relogio_offset_s"] = round(clk, 2) if clk is not None else None
    deaths, onsets = _deaths_and_onsets(timeline, match, riot_map)

    # 1. manual
    if manual_anchor_s is not None and t_anchor is not None:
        res.update(metodo="manual", offset_s=manual_anchor_s - t_anchor,
                   ancora={"t": manual_anchor_s, "jogador": None, "texto": "(informado)"})

    # 2. palavra — só uma ocorrência, perto do começo
    elif t_anchor is not None and cfg.get("palavra"):
        cands = find_word(timeline, cfg["palavra"])
        if clk is not None:
            esperado = t_anchor + clk
            j = float(cfg["janela_relogio_s"])
            lo, hi = esperado - j, esperado + j
            regra = f"±{int(j)}s de onde o round {cfg['round']} deveria estar pelo horário"
        else:
            esperado = None
            lo, hi = 0.0, float(cfg["janela_inicio_s"])
            regra = f"primeiros {int(hi // 60)} min da gravação"
        validos = [c for c in cands if lo <= c["t"] <= hi]
        escolhido = None
        if validos:
            if esperado is not None:
                escolhido = min(validos, key=lambda c: abs(c["t"] - esperado))
            else:
                escolhido = validos[0]  # a primeira do começo
            # Mais de um candidato na janela (ex.: "bora espumas" no lobby): se as mortes
            # apontarem claramente para um deles, fica com ele.
            if len(validos) > 1 and len(deaths) >= 6:
                scored = sorted(((death_speech_score(c["t"] - t_anchor, deaths, onsets), c)
                                 for c in validos), key=lambda x: -x[0])
                if scored[0][0] - scored[1][0] >= 0.15:
                    escolhido = scored[0][1]
        for c in cands:
            if c is escolhido:
                continue
            motivo = "repetição (só vale uma)" if lo <= c["t"] <= hi else "fora do começo"
            res["ignoradas"].append({**c, "motivo": motivo})
        if escolhido:
            res.update(metodo="palavra", offset_s=escolhido["t"] - t_anchor, ancora=escolhido)
            res["regra"] = regra
        else:
            res["avisos"].append(f"Palavra '{cfg['palavra']}' não encontrada ({regra}).")

    # 3. relógio
    if res["offset_s"] is None and clk is not None:
        res.update(metodo="relogio", offset_s=clk)
        res["avisos"].append("Sincronizado só pelo horário do Craig x API: pode ter erro de "
                             "dezenas de segundos. Usar a palavra de sinc ajuda muito.")

    if res["offset_s"] is None:
        res["avisos"].append("Sem sincronização: métricas por round não foram calculadas.")
        return res

    # Ajuste fino pelas mortes
    max_shift = float(cfg["ajuste_max_s"]) * (4 if res["metodo"] == "relogio" else 1)
    adj = refine(res["offset_s"], deaths, onsets, max_shift)
    res["ajuste"] = adj
    if adj["aplicado"]:
        res["offset_s"] += adj["delta_s"]
    elif deaths and abs(adj["sugestao_delta_s"]) >= 2 and res["metodo"] != "relogio":
        res["avisos"].append(
            f"As mortes sugerem deslocar {adj['sugestao_delta_s']:+.1f}s, mas sem confiança "
            "suficiente para aplicar sozinho.")
    res["offset_s"] = round(res["offset_s"], 2)
    return res
