"""Dados da partida via HenrikDev API (não oficial) e normalização para o pipeline.

Documentação: https://docs.henrikdev.xyz
- Lista:    GET /valorant/v4/matches/{regiao}/{plataforma}/{nome}/{tag}?size=N
- Detalhes: GET /valorant/v4/match/{regiao}/{match_id}
Autenticação: header Authorization com a chave.

Tempos: a API dá, para cada kill, o tempo dentro do round e o tempo desde o início da
partida. A diferença entre os dois é o instante (no relógio da partida) em que o round
"começa" para a API. Se esse zero é o início da fase de compra ou a barreira caindo é
detectado pelos próprios dados (ver `detect_round_t0`).
"""

from __future__ import annotations

import statistics
from datetime import datetime
from urllib.parse import quote

BASE_URL = "https://api.henrikdev.xyz"


class RiotAPIError(RuntimeError):
    pass


def split_riot_id(riot_id: str) -> tuple[str, str]:
    if "#" not in riot_id:
        raise ValueError("Riot ID precisa estar no formato Nome#TAG")
    name, tag = riot_id.rsplit("#", 1)
    return name.strip(), tag.strip()


def riot_key(p: dict | None) -> str:
    """{"name": "Fulano", "tag": "BR1"} -> "Fulano#BR1"."""
    if not p:
        return ""
    return f"{p.get('name', '')}#{p.get('tag', '')}"


def same_riot(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.strip().lower() == b.strip().lower()


class HenrikClient:
    def __init__(self, api_key: str, regiao: str = "br", plataforma: str = "pc",
                 http=None, timeout: float = 20.0):
        if not api_key:
            raise RiotAPIError("Falta a chave da HenrikDev API (configurações).")
        self.api_key = api_key
        self.regiao = regiao
        self.plataforma = plataforma
        if http is None:
            import httpx

            http = httpx.Client(base_url=BASE_URL, timeout=timeout)
        self.http = http
        self._cache: dict[str, dict] = {}

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self.http.get(path, params=params, headers={"Authorization": self.api_key})
        if r.status_code == 401 or r.status_code == 403:
            raise RiotAPIError("Chave da HenrikDev API recusada. Confira nas configurações.")
        if r.status_code == 404:
            raise RiotAPIError("Não encontrado na API (Riot ID ou partida errados?).")
        if r.status_code == 429:
            raise RiotAPIError("Limite de requisições da HenrikDev API. Tente em 1 minuto.")
        if r.status_code >= 400:
            raise RiotAPIError(f"Erro {r.status_code} na HenrikDev API.")
        return r.json()

    def list_matches(self, riot_id: str, size: int = 10) -> list[dict]:
        """Últimas partidas do jogador, já resumidas para mostrar numa lista."""
        name, tag = split_riot_id(riot_id)
        path = (f"/valorant/v4/matches/{self.regiao}/{self.plataforma}/"
                f"{quote(name, safe='')}/{quote(tag, safe='')}")
        data = self._get(path, {"size": size}).get("data") or []
        out = []
        for m in data:
            # Deathmatch e afins têm um "round" só: não servem para a análise.
            if m.get("rounds") is not None and len(m["rounds"]) <= 1:
                continue
            mid = (m.get("metadata") or {}).get("match_id")
            if mid and m.get("rounds") is not None:
                self._cache[mid] = m
            out.append(summarize(m, riot_id))
        return out

    def get_match(self, match_id: str) -> dict:
        if match_id in self._cache:
            return self._cache[match_id]
        data = self._get(f"/valorant/v4/match/{self.regiao}/{quote(match_id, safe='')}")
        m = data.get("data") or {}
        self._cache[match_id] = m
        return m


# --------------------------------------------------------------------------- normalização

def _team_of(raw: dict, riot_id: str | None) -> str | None:
    for p in raw.get("players") or []:
        if same_riot(riot_key(p), riot_id):
            return p.get("team_id")
    return None


def summarize(raw: dict, riot_id: str | None) -> dict:
    meta = raw.get("metadata") or {}
    team = _team_of(raw, riot_id)
    teams = {t.get("team_id"): t for t in raw.get("teams") or []}
    nosso = teams.get(team, {}).get("rounds", {}) if team else {}
    me = next((p for p in raw.get("players") or [] if same_riot(riot_key(p), riot_id)), {})
    stats = me.get("stats") or {}
    return {
        "id": meta.get("match_id"),
        "mapa": (meta.get("map") or {}).get("name"),
        "modo": (meta.get("queue") or {}).get("name") or (meta.get("queue") or {}).get("id"),
        "inicio": meta.get("started_at"),
        "duracao_s": round((meta.get("game_length_in_ms") or 0) / 1000),
        "placar": [nosso.get("won"), nosso.get("lost")] if nosso else None,
        "venceu": teams.get(team, {}).get("won") if team else None,
        "agente": (me.get("agent") or {}).get("name"),
        "kda": [stats.get("kills"), stats.get("deaths"), stats.get("assists")] if stats else None,
        "rounds": len(raw.get("rounds") or []) if raw.get("rounds") is not None else None,
    }


def detect_round_t0(kills: list[dict], buy_s: float = 30.0,
                    plants_s: list[float] | None = None) -> str:
    """Descobre se o "tempo no round" da API conta da fase de compra ou da barreira.

    Durante a compra ninguém morre nem planta (barreiras). Se a contagem começasse na
    compra, nenhuma kill ou plant teria tempo no round menor que ~30 s. Em partidas reais
    (out/2026) há plants com ~20 s, então o padrão sem evidência é "barreira".
    """
    early = sum(1 for k in kills if k["t_round_s"] < buy_s - 1)
    early += sum(1 for t in plants_s or [] if t < buy_s - 1)
    if early >= 1:
        return "barreira"
    tardias = [k["t_round_s"] for k in kills]
    # Muitas kills e nenhuma antes de 30 s: aí sim parece contar da compra.
    if len(tardias) >= 20 and min(tardias) >= buy_s:
        return "buy"
    return "barreira"


def _round_starts(raw_rounds: list[dict], kills: list[dict]) -> list[tuple[float | None, bool]]:
    by_round: dict[int, list[float]] = {}
    for k in kills:
        by_round.setdefault(k["round_idx"], []).append(k["t_s"] - k["t_round_s"])
    starts: list[float | None] = []
    for i in range(len(raw_rounds)):
        v = by_round.get(i)
        starts.append(statistics.median(v) if v else None)

    known = [(i, s) for i, s in enumerate(starts) if s is not None]
    if len(known) >= 2:
        durs = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(known, known[1:])]
        typical = statistics.median(durs)
    else:
        typical = 120.0
    out: list[tuple[float | None, bool]] = []
    for i, s in enumerate(starts):
        if s is not None:
            out.append((s, False))
            continue
        prev = next(((j, starts[j]) for j in range(i - 1, -1, -1) if starts[j] is not None), None)
        nxt = next(((j, starts[j]) for j in range(i + 1, len(starts)) if starts[j] is not None), None)
        if prev and nxt:
            est = prev[1] + (nxt[1] - prev[1]) * (i - prev[0]) / (nxt[0] - prev[0])
        elif prev:
            est = prev[1] + typical * (i - prev[0])
        elif nxt:
            est = nxt[1] - typical * (nxt[0] - i)
        else:
            est = None
        out.append((est, True))
    return out


def normalize_match(raw: dict, riot_id: str | None, buy_s: float = 30.0) -> dict:
    """Converte a resposta da API num formato simples, do ponto de vista do nosso time."""
    meta = raw.get("metadata") or {}
    team = _team_of(raw, riot_id)
    raw_rounds = raw.get("rounds") or []

    # Índice do round: a API usa "round" nas kills e "id" nos rounds (0 ou 1-based).
    ids = [r.get("id", i) for i, r in enumerate(raw_rounds)]
    id_to_idx = {rid: i for i, rid in enumerate(ids)}
    base = min(ids) if ids else 0

    kills = []
    for k in raw.get("kills") or []:
        rid = k.get("round")
        idx = id_to_idx.get(rid, (rid - base) if isinstance(rid, int) else 0)
        killer, victim = k.get("killer") or {}, k.get("victim") or {}
        kills.append({
            "round_idx": idx,
            "round": idx + 1,
            "t_s": (k.get("time_in_match_in_ms") or 0) / 1000,
            "t_round_s": (k.get("time_in_round_in_ms") or 0) / 1000,
            "killer": riot_key(killer),
            "vitima": riot_key(victim),
            "killer_time": killer.get("team"),
            "vitima_time": victim.get("team"),
            "arma": (k.get("weapon") or {}).get("name"),
        })
    kills.sort(key=lambda k: k["t_s"])

    starts = _round_starts(raw_rounds, kills)
    rounds = []
    for i, r in enumerate(raw_rounds):
        inicio, estimado = starts[i]

        def ev(obj):
            if not obj:
                return None
            tr = (obj.get("round_time_in_ms") or 0) / 1000
            return {"t_round_s": tr, "t_s": (inicio + tr) if inicio is not None else None,
                    "site": obj.get("site"), "riot": riot_key(obj.get("player")),
                    "time": (obj.get("player") or {}).get("team")}

        rounds.append({
            "n": i + 1,
            "vencedor": r.get("winning_team"),
            "ganhamos": (r.get("winning_team") == team) if team else None,
            "resultado": r.get("result"),
            "inicio_s": inicio,
            "inicio_estimado": estimado,
            "plant": ev(r.get("plant")),
            "defuse": ev(r.get("defuse")),
            "economia": _economia(r, team),
        })

    lados = infer_sides(rounds, team, (meta.get("queue") or {}).get("id")
                        or (meta.get("queue") or {}).get("name"))
    for r, lado in zip(rounds, lados):
        r["lado"] = lado

    jogadores = [{
        "riot": riot_key(p), "puuid": p.get("puuid"), "time": p.get("team_id"),
        "agente": (p.get("agent") or {}).get("name"),
    } for p in raw.get("players") or []]

    s = summarize(raw, riot_id)
    return {
        "id": meta.get("match_id"),
        "mapa": s["mapa"],
        "modo": s["modo"],
        "inicio": meta.get("started_at"),
        "duracao_s": s["duracao_s"],
        "placar": s["placar"],
        "nosso_time": team,
        "riot_id": riot_id,
        "jogadores": jogadores,
        "rounds": rounds,
        "kills": kills,
        "t0_round": detect_round_t0(
            kills, buy_s, [(r.get("plant") or {}).get("round_time_in_ms", 0) / 1000
                           for r in raw_rounds if r.get("plant")]),
    }


def _economia(raw_round: dict, team: str | None) -> dict:
    """Compra de cada jogador do nosso time no round: {riot: {loadout, arma, restante}}."""
    out = {}
    for st in raw_round.get("stats") or []:
        p = st.get("player") or {}
        if team and p.get("team") != team:
            continue
        eco = st.get("economy") or {}
        out[riot_key(p)] = {
            "loadout": eco.get("loadout_value"),
            "arma": (eco.get("weapon") or {}).get("name"),
            "restante": eco.get("remaining"),
        }
    return out


def half_length(queue: str | None) -> int:
    q = (queue or "").lower()
    if "swift" in q:
        return 4
    if "spike" in q:
        return 3
    return 12


def side_from_first_half(n: int, first: str, half: int) -> str:
    """Lado no round n (1-based) sabendo o lado do 1º tempo."""
    outro = "defesa" if first == "ataque" else "ataque"
    if n <= half:
        return first
    if n <= 2 * half:
        return outro
    # Prorrogação: troca a cada round, começando pelo lado do 1º tempo.
    return first if (n - 2 * half - 1) % 2 == 0 else outro


def infer_sides(rounds: list[dict], team: str | None, queue: str | None) -> list[str | None]:
    """A API não diz o lado. Quem planta está atacando: com isso descobre o 1º tempo."""
    if not team:
        return [None] * len(rounds)
    half = half_length(queue)
    votos = {"ataque": 0, "defesa": 0}
    for r in rounds:
        pl = r.get("plant")
        if not pl or not pl.get("time"):
            continue
        lado_nesse = "ataque" if pl["time"] == team else "defesa"
        for first in ("ataque", "defesa"):
            if side_from_first_half(r["n"], first, half) == lado_nesse:
                votos[first] += 1
    if votos["ataque"] == votos["defesa"]:
        return [None] * len(rounds)
    first = max(votos, key=votos.get)
    return [side_from_first_half(r["n"], first, half) for r in rounds]


def match_start_datetime(match: dict) -> datetime | None:
    v = match.get("inicio")
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
