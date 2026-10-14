import copy

import pytest

from espumas import exemplo
from espumas.config import DEFAULTS
from espumas.game import compute_game_metrics, phase_at, round_windows
from espumas.metrics import compute_metrics
from espumas.riot import normalize_match, summarize
from espumas.sync import anchor_match_time, find_word, synchronize
from espumas.timeline import merge_timeline

RIOT = "Ronaldovels#BR1"
OFFSET = 312.4  # gravação começou 312,4 s antes da partida
SINC = DEFAULTS["sinc"]
RIOT_MAP = {a: r for a, r, _ in exemplo.NOSSOS}


@pytest.fixture(params=["buy", "barreira"])
def match(request):
    return normalize_match(exemplo.raw_match(t0=request.param), RIOT)


@pytest.fixture
def timeline():
    raw = exemplo.raw_match()
    return merge_timeline(exemplo.call_sintetica(raw, OFFSET))


def test_normaliza_partida(match):
    assert match["mapa"] == "Ascent"
    assert match["nosso_time"] == "Blue"
    assert len(match["rounds"]) == 12
    assert sum(match["placar"]) == 12
    # O início do round 1 no relógio da partida depende do "zero" da API
    esperado = 45.0 if match["t0_round"] == "buy" else 75.0
    assert match["rounds"][0]["inicio_s"] == pytest.approx(esperado, abs=0.01)
    assert {r["ganhamos"] for r in match["rounds"]} <= {True, False}


def test_detecta_zero_do_round():
    assert normalize_match(exemplo.raw_match(t0="buy"), RIOT)["t0_round"] == "buy"
    assert normalize_match(exemplo.raw_match(t0="barreira"), RIOT)["t0_round"] == "barreira"


def test_ancora_barreira_round1_igual_nos_dois_formatos(match):
    # Barreira do round 1 = 45 s de espera + 30 s de compra, qualquer que seja o zero da API
    assert anchor_match_time(match, SINC) == pytest.approx(75.0, abs=0.01)
    cfg = {**SINC, "fase": "buy", "restantes_s": 25}  # "faltando 25s na compra"
    assert anchor_match_time(match, cfg) == pytest.approx(50.0, abs=0.01)


def test_resumo_lista():
    s = summarize(exemplo.raw_match(), RIOT)
    assert s["agente"] == "Sova" and s["mapa"] == "Ascent" and s["id"] == "demo-0001"


def test_acha_palavra_com_erro_de_transcricao(timeline):
    occ = find_word(timeline, "espumas")
    assert len(occ) >= 4  # lobby, âncora, repetições
    from espumas.models import Utterance, Word
    u = Utterance("X", 1, 2, "Espuma!", [Word(1, 2, " Espuma!")])
    assert find_word([u], "espumas")


def test_sinc_palavra_com_horario(match, timeline):
    rec = exemplo.craig_inicio(OFFSET, erro_s=25)  # horário do Craig 25 s errado
    s = synchronize(timeline, match, SINC, rec, exemplo.INICIO_PARTIDA, RIOT_MAP)
    assert s["metodo"] == "palavra"
    assert s["ancora"]["jogador"] == "Ronaldo"  # não o "bora espumas" do lobby
    assert s["offset_s"] == pytest.approx(OFFSET + 0.3, abs=0.6)
    motivos = {c["motivo"] for c in s["ignoradas"]}
    assert "fora do começo" in motivos  # repetições no meio da partida
    assert all(c["t"] != s["ancora"]["t"] for c in s["ignoradas"])


def test_sinc_palavra_sem_horario_ignora_lobby(match, timeline):
    s = synchronize(timeline, match, SINC, None, None, RIOT_MAP)
    assert s["metodo"] == "palavra"
    assert s["ancora"]["jogador"] == "Ronaldo"
    assert s["offset_s"] == pytest.approx(OFFSET + 0.3, abs=0.6)
    # nenhuma ocorrência depois da janela do começo foi usada
    assert s["ancora"]["t"] <= SINC["janela_inicio_s"]


def test_repeticao_no_meio_nunca_vira_ancora(match):
    raw = exemplo.raw_match()
    per = exemplo.call_sintetica(raw, OFFSET)
    # Remove a âncora verdadeira: só sobram lobby e repetições no meio
    per["Ronaldo"] = [u for u in per["Ronaldo"] if u.text != "espumas"]
    tl = merge_timeline(per)
    cfg = {**SINC, "janela_inicio_s": OFFSET + 60}  # janela que cobre só o começo
    s = synchronize(tl, match, cfg, None, None, RIOT_MAP)
    assert s["ancora"] is None or s["ancora"]["t"] < OFFSET + 60
    assert all(c["motivo"] in ("fora do começo", "repetição (só vale uma)") for c in s["ignoradas"])


def test_sinc_so_relogio_com_ajuste_pelas_mortes(match):
    raw = exemplo.raw_match()
    per = exemplo.call_sintetica(raw, OFFSET)
    for p in per:
        per[p] = [u for u in per[p] if "espumas" not in u.text]
    tl = merge_timeline(per)
    rec = exemplo.craig_inicio(OFFSET, erro_s=-30)
    s = synchronize(tl, match, SINC, rec, exemplo.INICIO_PARTIDA, RIOT_MAP)
    assert s["metodo"] == "relogio"
    assert s["ajuste"]["aplicado"]
    assert s["offset_s"] == pytest.approx(OFFSET, abs=1.0)


def test_sinc_manual(match, timeline):
    s = synchronize(timeline, match, SINC, None, None, RIOT_MAP, manual_anchor_s=OFFSET + 75)
    assert s["metodo"] == "manual"
    assert s["offset_s"] == pytest.approx(OFFSET, abs=0.6)


def test_metricas_de_jogo(match, timeline):
    s = synchronize(timeline, match, SINC, None, None, RIOT_MAP)
    m = compute_metrics(timeline, [a for a, _, _ in exemplo.NOSSOS], DEFAULTS["metricas"])
    g = compute_game_metrics(timeline, match, s, RIOT_MAP, m["sobreposicoes"], SINC)
    assert len(g["rounds"]) == 12
    assert len(g["contexto_falas"]) == len(timeline)
    assert g["fala_de_morto"]["eventos"], "quem morre fala depois -> deve haver fala de morto"
    assert sum(r["kills"] + r["mortes"] for r in g["rounds"]) == len(match["kills"])
    # Frases de compra caem na fase de compra
    buy_ctx = [c for u, c in zip(timeline, g["contexto_falas"]) if u.text == "tô sem grana"]
    assert buy_ctx and all(c["fase"] == "buy" for c in buy_ctx)
    assert set(g["ganhos_x_perdidos"]) == {"interrupcoes", "fala_ativo_s", "fala_morto_s", "fala_buy_s"}


def test_fases(match):
    wins = round_windows(match, 100.0, 30.0)
    w = wins[0]
    assert phase_at(w["buy"] - 1, wins) == (None, "pre_jogo")
    assert phase_at(w["buy"] + 1, wins) == (1, "buy")
    assert phase_at(w["barreira"] + 1, wins) == (1, "ativo")
    assert phase_at(wins[-1]["fim"] + 60, wins)[1] == "pos_jogo"


def test_round_sem_kills_tem_inicio_estimado():
    raw = exemplo.raw_match()
    raw = copy.deepcopy(raw)
    raw["kills"] = [k for k in raw["kills"] if k["round"] != 4]
    m = normalize_match(raw, RIOT)
    r5 = m["rounds"][4]
    assert r5["inicio_estimado"] is True
    assert r5["inicio_s"] == pytest.approx(45 + 4 * exemplo.INTERVALO_S, abs=2)
