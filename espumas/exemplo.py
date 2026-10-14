"""Dados sintéticos (partida no formato da HenrikDev v4 + call) para demo e testes."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .models import Utterance, Word

NOSSOS = [("Ronaldo", "Ronaldovels#BR1", "Sova"), ("Kaio", "kaiozin#0001", "Jett"),
          ("Bia", "biaa#GG", "Killjoy"), ("Duda", "dudinha#777", "Omen"),
          ("Léo", "leozera#BR2", "Raze")]
DELES = [("inimigo1#XX", "Reyna"), ("inimigo2#XX", "Cypher"), ("inimigo3#XX", "Fade"),
         ("inimigo4#XX", "Viper"), ("inimigo5#XX", "Breach")]

INICIO_PARTIDA = datetime(2026, 10, 14, 22, 10, 0, tzinfo=timezone.utc)
BUY_S = 30.0
INTERVALO_S = 128.0  # do início de uma compra até a próxima (aprox.)


def _p(riot: str, team: str) -> dict:
    name, tag = riot.split("#")
    return {"name": name, "tag": tag, "team": team, "puuid": riot}


def raw_match(n_rounds: int = 12, t0: str = "buy", seed: int = 3) -> dict:
    """Partida falsa no formato da resposta /valorant/v4/match (só os campos usados)."""
    rnd = random.Random(seed)
    players = [{"puuid": r, "name": r.split("#")[0], "tag": r.split("#")[1], "team_id": "Blue",
                "agent": {"name": a}, "stats": {"kills": 0, "deaths": 0, "assists": 0}}
               for _, r, a in NOSSOS]
    players += [{"puuid": r, "name": r.split("#")[0], "tag": r.split("#")[1], "team_id": "Red",
                 "agent": {"name": a}, "stats": {}} for r, a in DELES]
    rounds, kills = [], []
    placar = {"Blue": 0, "Red": 0}
    rnd_eco = random.Random(seed + 100)  # separado para não mudar o resto da partida
    for i in range(n_rounds):
        buy_start = 45.0 + i * INTERVALO_S  # no relógio da partida
        barreira = buy_start + BUY_S
        zero = buy_start if t0 == "buy" else barreira
        vivos = {"Blue": [r for _, r, _ in NOSSOS], "Red": [r for r, _ in DELES]}
        t = barreira + rnd.uniform(8, 25)
        vencedor = None
        while vivos["Blue"] and vivos["Red"] and t < barreira + 95:
            lado = "Blue" if rnd.random() < 0.5 else "Red"
            outro = "Red" if lado == "Blue" else "Blue"
            killer = rnd.choice(vivos[lado])
            vitima = rnd.choice(vivos[outro])
            vivos[outro].remove(vitima)
            kills.append({"round": i, "time_in_round_in_ms": int((t - zero) * 1000),
                          "time_in_match_in_ms": int(t * 1000),
                          "killer": _p(killer, lado), "victim": _p(vitima, outro),
                          "weapon": {"name": "Vandal"}})
            t += rnd.uniform(2, 14)
        if not vivos["Red"]:
            vencedor = "Blue"
        elif not vivos["Blue"]:
            vencedor = "Red"
        else:
            vencedor = "Red"
        placar[vencedor] += 1
        plant = None
        if rnd.random() < 0.4:
            plant = {"round_time_in_ms": int((barreira + 40 - zero) * 1000),
                     "site": rnd.choice("AB"), "player": _p(NOSSOS[0][1], "Blue")}
        rounds.append({"id": i, "result": "Elimination", "winning_team": vencedor,
                       "plant": plant, "defuse": None,
                       "stats": _stats_economia(i, rnd_eco)})
    return {
        "metadata": {"match_id": "demo-0001", "map": {"name": "Ascent"},
                     "queue": {"name": "Competitive"},
                     "started_at": INICIO_PARTIDA.isoformat().replace("+00:00", "Z"),
                     "game_length_in_ms": int((45 + n_rounds * INTERVALO_S) * 1000)},
        "players": players,
        "teams": [{"team_id": "Blue", "won": placar["Blue"] > placar["Red"],
                   "rounds": {"won": placar["Blue"], "lost": placar["Red"]}},
                  {"team_id": "Red", "won": placar["Red"] > placar["Blue"],
                   "rounds": {"won": placar["Red"], "lost": placar["Blue"]}}],
        "rounds": rounds,
        "kills": kills,
    }


COMPRAS = {  # padrão de compra do nosso time -> loadout de cada um
    "pistol": [800] * 5,
    "full": [3900, 4700, 3900, 4200, 3900],
    "eco": [400, 800, 0, 1200, 600],
    "forca": [2400, 2900, 2050, 2600, 2300],
    "dividida": [3900, 4700, 800, 400, 3900],
}


def padrao_compra(i: int) -> str:
    """Padrão de compra do round i (0-based) usado pela partida de exemplo."""
    if i == 0:
        return "pistol"
    return ["full", "eco", "dividida", "full", "forca", "full", "dividida", "full",
            "eco", "full", "full"][(i - 1) % 11]


def _stats_economia(i: int, rnd: random.Random) -> list[dict]:
    valores = COMPRAS[padrao_compra(i)]
    out = []
    for (_, r, _), v in zip(NOSSOS, valores):
        arma = "Vandal" if v >= 3900 else "Spectre" if v >= 2000 else "Classic"
        out.append({"player": _p(r, "Blue"),
                    "economy": {"loadout_value": v, "remaining": rnd.randint(0, 3000),
                                "weapon": {"name": arma}, "armor": None}})
    return out


FRASES = {
    "callout": ["dois no B main", "um no mid", "ele tá lit cem", "Jett deu dash no short",
                "roda pro B", "vai pro A agora", "segura o heaven", "trade", "um no CT"],
    "buy": ["tô sem grana", "força ou salva", "compra Vandal", "eco esse round",
            "vamo de execute no A", "dropa pra mim"],
    "morto": ["morri, ele tá no heaven", "foi o Cypher", "tava no canto, cuidado",
              "ele tá com vinte de vida", "nossa que round horrível cara sério"],
}


def _utt(player: str, start: float, text: str) -> Utterance:
    ws = text.split()
    dur = 0.3 * len(ws) + 0.2
    step = dur / len(ws)
    words = [Word(start + i * step, start + (i + 1) * step, " " + w) for i, w in enumerate(ws)]
    return Utterance(player, start, start + dur, text, words)


def call_sintetica(raw: dict, offset: float, seed: int = 5,
                   ancora_atraso_s: float = 0.3) -> dict[str, list[Utterance]]:
    """Call falsa coerente com a partida (gravação = partida + offset).

    Inclui: "bora espumas" no lobby, "espumas" na barreira do round 1 e repetições depois.
    """
    rnd = random.Random(seed)
    por_riot = {r: apelido for apelido, r, _ in NOSSOS}
    per: dict[str, list[Utterance]] = {a: [] for a, _, _ in NOSSOS}

    def add(p, t, txt):
        per[p].append(_utt(p, t, txt))

    # Lobby / seleção de agente
    add("Kaio", offset - 70, "bora espumas hoje vai")
    add("Ronaldo", offset - 40, "eu vou de Sova")
    # Âncora: barreira do round 1 (zero da partida + 45s de espera + 30s de compra)
    barreira1 = 45.0 + BUY_S
    add("Ronaldo", barreira1 + offset + ancora_atraso_s, "espumas")

    for i, r in enumerate(raw["rounds"]):
        buy = 45.0 + i * INTERVALO_S + offset
        for _ in range(rnd.randint(2, 5)):
            p = rnd.choice(list(per))
            add(p, buy + rnd.uniform(1, BUY_S - 4), rnd.choice(FRASES["buy"]))
        bar = buy + BUY_S
        for _ in range(rnd.randint(4, 9)):
            p = rnd.choice(list(per))
            add(p, bar + rnd.uniform(2, 80), rnd.choice(FRASES["callout"]))
    for k in raw["kills"]:
        vit = por_riot.get(f'{k["victim"]["name"]}#{k["victim"]["tag"]}')
        if vit and rnd.random() < 0.85:  # quem morre geralmente fala logo depois
            add(vit, k["time_in_match_in_ms"] / 1000 + offset + rnd.uniform(0.4, 1.6),
                rnd.choice(FRASES["morto"]))
    # Call de site na compra (às vezes a execução muda) e call de compra
    rnd2 = random.Random(seed + 7)
    falas_compra = {"full": "full buy galera", "eco": "eco esse round", "forca": "bora forçar",
                    "dividida": "força ou salva"}
    for i, r in enumerate(raw["rounds"]):
        buy = 45.0 + i * INTERVALO_S + offset
        pl = r.get("plant")
        site = (pl or {}).get("site") or rnd2.choice("AB")
        if rnd2.random() < 0.3:
            site = "B" if site == "A" else "A"
        add("Ronaldo", buy + 3, f"vamo de execute no {site}")
        pc = padrao_compra(i)
        if pc in falas_compra:
            add("Bia", buy + 9, falas_compra[pc])
    # Repetições da palavra no meio da partida (devem ser ignoradas)
    add("Léo", 5 * INTERVALO_S + offset, "vamo espumas")
    add("Bia", 9 * INTERVALO_S + offset + 20, "espumas espumas")
    # Uma pessoa não fala duas coisas ao mesmo tempo: descarta o que se sobrepõe.
    # As falas "importantes" (âncora e pós-morte) têm prioridade.
    prioridade = set(FRASES["morto"]) | {"espumas", "vamo de execute no A",
                                         "vamo de execute no B", "full buy galera",
                                         "eco esse round", "bora forçar", "força ou salva"}
    for p in per:
        utts = sorted(per[p], key=lambda u: (u.text not in prioridade, u.start))
        aceitas: list[Utterance] = []
        for u in utts:
            if all(u.end + 0.2 < a.start or a.end + 0.2 < u.start for a in aceitas):
                aceitas.append(u)
        per[p] = sorted(aceitas, key=lambda u: u.start)
    return per


def craig_inicio(offset: float, erro_s: float = 0.0) -> datetime:
    """Horário de início da gravação coerente com o offset (com erro opcional)."""
    return INICIO_PARTIDA - timedelta(seconds=offset + erro_s)
