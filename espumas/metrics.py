"""Métricas de "poluição" da comunicação a partir da linha do tempo."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass

from .models import Utterance

# Verbos/expressões de comando típicos de call. Usados para achar ordens simultâneas.
_ORDENS = [
    "vai", "vamo", "vamos", "bora", "roda", "rotaciona", "rotate", "gira", "segura",
    "espera", "recua", "volta", "push", "entra", "joga", "planta", "defusa", "salva",
    "save", "força", "force", "compra", "pega", "segue", "fica", "sai", "retake",
    "executa", "trade", "tradeia",
]
_ORDENS_RE = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, _ORDENS)) + r")(?!\w)",
                        re.IGNORECASE)
# "vai pro B", "rotate A", "roda pra C", "site A" — letra do site em maiúscula.
_SITE_RE = re.compile(
    r"(?:(?<!\w)(?:pro|pra|para o|no|na|site|bomb|rotate|roda|gira|vai|entra)\s+)([ABC])(?!\w)"
)

SIMULTANEO_S = 0.3  # começaram a falar juntos (ninguém "cortou" ninguém)


@dataclass
class OverlapEvent:
    start: float
    end: float
    duration: float
    primeiro: str  # quem já estava falando
    segundo: str  # quem entrou por cima
    tipo: str  # "interrupcao" | "backchannel" | "simultaneo"
    texto_primeiro: str
    texto_segundo: str


def is_backchannel(u: Utterance, cfg: dict) -> bool:
    return (u.n_words <= cfg["backchannel_max_palavras"]
            and u.duration <= cfg["backchannel_max_s"])


def _union_length(intervals: list[tuple[float, float]]) -> float:
    total, cur_s, cur_e = 0.0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def _time_with_n_speakers(timeline: list[Utterance]) -> dict[int, float]:
    """Segundos em que exatamente N jogadores falavam ao mesmo tempo."""
    events = []
    for u in timeline:
        events.append((u.start, 1, u.player))
        events.append((u.end, -1, u.player))
    events.sort(key=lambda e: (e[0], e[1]))  # fim antes de início no mesmo instante
    active: dict[str, int] = defaultdict(int)
    out: dict[int, float] = defaultdict(float)
    last_t = None
    for t, delta, p in events:
        if last_t is not None:
            n = sum(1 for c in active.values() if c > 0)
            out[n] += t - last_t
        active[p] += delta
        last_t = t
    return dict(out)


def find_overlaps(timeline: list[Utterance], cfg: dict) -> list[OverlapEvent]:
    events: list[OverlapEvent] = []
    tl = sorted(timeline, key=lambda u: u.start)
    for i, a in enumerate(tl):
        for b in tl[i + 1:]:
            if b.start >= a.end:
                break
            if b.player == a.player:
                continue
            s, e = max(a.start, b.start), min(a.end, b.end)
            if e - s < cfg["min_sobreposicao_s"]:
                continue
            # `a` começou antes (ou junto). `b` é quem entrou por cima.
            if b.start - a.start <= SIMULTANEO_S:
                tipo = "simultaneo"
            elif is_backchannel(b, cfg):
                tipo = "backchannel"
            else:
                tipo = "interrupcao"
            events.append(OverlapEvent(
                start=round(s, 2), end=round(e, 2), duration=round(e - s, 2),
                primeiro=a.player, segundo=b.player, tipo=tipo,
                texto_primeiro=a.text, texto_segundo=b.text,
            ))
    return events


def has_order(text: str) -> bool:
    return bool(_ORDENS_RE.search(text))


def sites_in(text: str) -> set[str]:
    return set(_SITE_RE.findall(text))


def find_conflicting_orders(timeline: list[Utterance], cfg: dict) -> list[dict]:
    """Ordens de jogadores diferentes muito próximas no tempo.

    Marca como `conflito_site` quando apontam sites diferentes (ex.: "vai A" x "roda B").
    """
    window = cfg["janela_ordens_s"]
    orders = [u for u in sorted(timeline, key=lambda u: u.start) if has_order(u.text)]
    out = []
    for i, a in enumerate(orders):
        for b in orders[i + 1:]:
            if b.start - a.start > window:
                break
            if b.player == a.player or b.text.strip().lower() == a.text.strip().lower():
                continue
            sa, sb = sites_in(a.text), sites_in(b.text)
            out.append({
                "start": round(a.start, 2),
                "jogadores": [a.player, b.player],
                "textos": [a.text, b.text],
                "conflito_site": bool(sa and sb and sa.isdisjoint(sb)),
            })
    return out


def long_callouts(timeline: list[Utterance], cfg: dict) -> list[dict]:
    return [
        {"start": round(u.start, 2), "jogador": u.player, "duracao": round(u.duration, 1),
         "palavras": u.n_words, "texto": u.text}
        for u in timeline
        if u.duration >= cfg["callout_longo_s"] or u.n_words >= cfg["callout_longo_palavras"]
    ]


def compute_metrics(timeline: list[Utterance], players: list[str], cfg: dict,
                    duracao_total: float | None = None) -> dict:
    duracao_total = max(duracao_total or 0.0, max((u.end for u in timeline), default=0.0))
    players = list(dict.fromkeys(list(players) + [u.player for u in timeline]))

    overlaps = find_overlaps(timeline, cfg)
    n_speakers = _time_with_n_speakers(timeline)
    tempo_com_fala = _union_length([(u.start, u.end) for u in timeline])

    por_jogador: dict[str, dict] = {}
    for p in players:
        utts = [u for u in timeline if u.player == p]
        tempo = sum(u.duration for u in utts)
        por_jogador[p] = {
            "tempo_fala_s": round(tempo, 1),
            "falas": len(utts),
            "palavras": sum(u.n_words for u in utts),
            "media_fala_s": round(tempo / len(utts), 2) if utts else 0.0,
            "interrompeu": 0,
            "foi_interrompido": 0,
            "falou_junto": 0,
            "callouts_longos": 0,
        }
    total_fala = sum(d["tempo_fala_s"] for d in por_jogador.values()) or 1.0
    for d in por_jogador.values():
        d["participacao_pct"] = round(100 * d["tempo_fala_s"] / total_fala, 1)

    for ev in overlaps:
        if ev.tipo == "interrupcao":
            por_jogador[ev.segundo]["interrompeu"] += 1
            por_jogador[ev.primeiro]["foi_interrompido"] += 1
        elif ev.tipo == "simultaneo":
            por_jogador[ev.primeiro]["falou_junto"] += 1
            por_jogador[ev.segundo]["falou_junto"] += 1

    longos = long_callouts(timeline, cfg)
    for c in longos:
        por_jogador[c["jogador"]]["callouts_longos"] += 1

    ordens = find_conflicting_orders(timeline, cfg)

    t_sobreposto = sum(v for k, v in n_speakers.items() if k >= 2)
    resumo = {
        "duracao_s": round(duracao_total, 1),
        "tempo_com_fala_s": round(tempo_com_fala, 1),
        "silencio_pct": round(100 * (1 - tempo_com_fala / duracao_total), 1) if duracao_total else 0.0,
        "tempo_sobreposto_s": round(t_sobreposto, 1),
        "sobreposicao_pct_da_fala": round(100 * t_sobreposto / tempo_com_fala, 1) if tempo_com_fala else 0.0,
        "tempo_3mais_falando_s": round(sum(v for k, v in n_speakers.items() if k >= 3), 1),
        "interrupcoes": sum(1 for e in overlaps if e.tipo == "interrupcao"),
        "falas_simultaneas": sum(1 for e in overlaps if e.tipo == "simultaneo"),
        "backchannels": sum(1 for e in overlaps if e.tipo == "backchannel"),
        "callouts_longos": len(longos),
        "ordens_proximas": len(ordens),
        "conflitos_de_site": sum(1 for o in ordens if o["conflito_site"]),
    }

    return {
        "resumo": resumo,
        "jogadores": por_jogador,
        "sobreposicoes": [asdict(e) for e in overlaps],
        "callouts_longos": longos,
        "ordens_proximas": ordens,
        "destaques": insights(resumo, por_jogador),
    }


def insights(resumo: dict, por_jogador: dict[str, dict]) -> list[str]:
    """Frases curtas em português com o que mais chama atenção."""
    out: list[str] = []
    if not por_jogador:
        return out
    jog = list(por_jogador.items())

    top_int = max(jog, key=lambda kv: kv[1]["interrompeu"])
    if top_int[1]["interrompeu"] >= 3:
        out.append(f"{top_int[0]} entrou por cima de alguém {top_int[1]['interrompeu']} vezes "
                   "— maior número de interrupções da call.")

    vit = max(jog, key=lambda kv: kv[1]["foi_interrompido"])
    if vit[1]["foi_interrompido"] >= 3:
        out.append(f"{vit[0]} foi cortado {vit[1]['foi_interrompido']} vezes; "
                   "vale checar se callouts dele se perderam.")

    dom = max(jog, key=lambda kv: kv[1]["participacao_pct"])
    if len(jog) >= 3 and dom[1]["participacao_pct"] >= 40:
        out.append(f"{dom[0]} concentrou {dom[1]['participacao_pct']}% de toda a fala.")

    quieto = min(jog, key=lambda kv: kv[1]["participacao_pct"])
    if len(jog) >= 3 and quieto[1]["participacao_pct"] <= 8:
        out.append(f"{quieto[0]} quase não falou ({quieto[1]['participacao_pct']}% da fala).")

    if resumo["sobreposicao_pct_da_fala"] >= 15:
        out.append(f"{resumo['sobreposicao_pct_da_fala']}% do tempo com fala teve mais de uma "
                   "pessoa falando ao mesmo tempo.")
    if resumo["tempo_3mais_falando_s"] >= 5:
        out.append(f"{resumo['tempo_3mais_falando_s']}s com 3 ou mais pessoas falando juntas.")

    longos = max(jog, key=lambda kv: kv[1]["callouts_longos"])
    if longos[1]["callouts_longos"] >= 3:
        out.append(f"{longos[0]} teve {longos[1]['callouts_longos']} falas longas; "
                   "callouts mais curtos tendem a funcionar melhor em round.")

    if resumo["conflitos_de_site"]:
        out.append(f"{resumo['conflitos_de_site']} momento(s) com ordens apontando sites diferentes.")

    if not out:
        out.append("Nenhum padrão forte de poluição encontrado nesta partida.")
    return out
