"""Clutch, call x execução, compras, lados e áudio."""

import pytest

from espumas import exemplo
from espumas.config import DEFAULTS
from espumas.game import (call_x_execucao, classe_compra, clutches, compras,
                          compute_game_metrics)
from espumas.metrics import compute_metrics, site_mentions
from espumas.models import Utterance, Word
from espumas.riot import infer_sides, normalize_match, side_from_first_half
from espumas.sync import synchronize
from espumas.timeline import merge_timeline

RIOT = "Ronaldovels#BR1"
OFFSET = 312.4
RIOT_MAP = {a: r for a, r, _ in exemplo.NOSSOS}


def U(p, s, text):
    ws = text.split()
    return Utterance(p, s, s + 0.3 * len(ws), text,
                     [Word(s + 0.3 * i, s + 0.3 * (i + 1), " " + w) for i, w in enumerate(ws)])


@pytest.fixture
def jogo():
    raw = exemplo.raw_match()
    m = normalize_match(raw, RIOT)
    tl = merge_timeline(exemplo.call_sintetica(raw, OFFSET))
    s = synchronize(tl, m, DEFAULTS["sinc"], None, None, RIOT_MAP)
    met = compute_metrics(tl, list(RIOT_MAP), DEFAULTS["metricas"])
    return m, tl, s, compute_game_metrics(tl, m, s, RIOT_MAP, met["sobreposicoes"], DEFAULTS["sinc"])


def test_lados():
    assert [side_from_first_half(n, "ataque", 12) for n in (1, 12, 13, 24, 25, 26)] == \
        ["ataque", "ataque", "defesa", "defesa", "ataque", "defesa"]
    rounds = [{"n": n, "plant": {"time": "Blue" if n <= 12 else "Red"}} for n in range(1, 25)]
    assert infer_sides(rounds, "Blue", "competitive")[0] == "ataque"
    assert infer_sides(rounds, "Blue", "competitive")[12] == "defesa"
    assert infer_sides(rounds, "Red", "competitive")[0] == "defesa"
    assert infer_sides([{"n": 1, "plant": None}], "Blue", None) == [None]
    # Swiftplay troca de lado no round 5
    assert side_from_first_half(5, "ataque", 4) == "defesa"


def test_economia_normalizada():
    m = normalize_match(exemplo.raw_match(), RIOT)
    eco = m["rounds"][1]["economia"]
    assert len(eco) == 5 and eco[RIOT]["loadout"] == 3900 and eco[RIOT]["arma"] == "Vandal"
    assert classe_compra(800) == "eco" and classe_compra(2500) == "meio" and classe_compra(3900) == "full"


def test_sites():
    assert site_mentions("fake B vai A") == ["B", "A"]
    assert site_mentions("vamo de b galera") == ["B"]
    assert site_mentions("a gente vai") == []
    assert site_mentions("tá na a main") == ["A"]


def test_clutch(jogo):
    _, _, _, g = jogo
    cl = g["clutches"]
    assert cl, "a partida de exemplo tem rounds com um só vivo"
    for c in cl:
        assert c["jogador"] in RIOT_MAP and 1 <= c["contra"] <= 5 and c["duracao_s"] >= 1


def test_clutch_conta_quem_fala_por_cima():
    m = {"nosso_time": "Blue", "kills": [
        {"round": 1, "t_s": 10 + i, "vitima": r, "vitima_time": "Blue", "killer": "x#1",
         "killer_time": "Red"} for i, (_, r, _) in enumerate(exemplo.NOSSOS[:4])]}
    roster = [r for _, r, _ in exemplo.NOSSOS]
    wins = [{"n": 1, "fim": 40.0, "ganhamos": False}]
    tl = [U("Léo", 15.0, "ele tá no site eu vou"), U("Kaio", 15.5, "cuidado com o canto"),
          U("Bia", 30.0, "boa")]
    c = clutches(tl, m, wins, 0.0, RIOT_MAP, roster)[0]
    assert c["jogador"] == "Léo" and c["contra"] == 5
    assert c["falas_outros"] == 2 and c["por_cima_dele"] == 1 and not c["silencio_ok"]


def test_call_x_execucao():
    m = {"nosso_time": "Blue", "rounds": [
        {"n": 1, "lado": "ataque", "plant": {"time": "Blue", "site": "B"}},
        {"n": 2, "lado": "ataque", "plant": {"time": "Blue", "site": "A"}},
        {"n": 3, "lado": "defesa", "plant": None}]}
    wins = [{"n": 1, "buy": 0, "barreira": 30, "fim": 100, "plant": 80, "ganhamos": True},
            {"n": 2, "buy": 110, "barreira": 140, "fim": 200, "plant": 190, "ganhamos": False},
            {"n": 3, "buy": 210, "barreira": 240, "fim": 300, "plant": None, "ganhamos": True}]
    tl = [U("Ronaldo", 5, "vamo de B"), U("Kaio", 60, "dois no A main"),  # info, não ordem
          U("Ronaldo", 115, "vamo A"), U("Ronaldo", 150, "roda pro B")]
    r = {c["round"]: c for c in call_x_execucao(tl, m, wins)}
    assert set(r) == {1, 2}  # round de defesa fica de fora
    assert r[1]["status"] == "seguiu a call" and r[1]["call_final"] == "B"
    assert r[2]["status"] == "plantou em outro site" and r[2]["call_inicial"] == "A"


def test_compras(jogo):
    _, _, _, g = jogo
    cp = {c["round"]: c for c in g["compras"]}
    assert 1 not in cp  # pistol
    assert cp[4]["dividida"] and cp[4]["contagem"] == {"full": 3, "meio": 0, "eco": 2}
    assert not cp[2]["dividida"]
    # "força ou salva" é pergunta: não vira combinado
    assert all(c["call"] is None or "força ou salva" not in c["call"]["texto"] for c in cp.values())
    assert cp[9]["call"]["tipo"] == "full" and cp[9]["seguiu"] is True


def test_compra_combinada_x_real():
    m = {"rounds": [{"n": 3, "economia": {
        f"p{i}#1": {"loadout": 4000 if i < 3 else 500} for i in range(5)}}], "modo": "competitive"}
    wins = [{"n": 3, "buy": 100, "barreira": 130, "fim": 200, "ganhamos": False}]
    c = compras([U("Bia", 105, "bora salvar esse")], m, wins)[0]
    assert c["call"]["tipo"] == "eco" and c["seguiu"] is False and c["dividida"]


def test_audio_misturado(tmp_path):
    av = pytest.importorskip("av")
    import numpy as np
    import soundfile as sf

    from espumas.audio import existing_audio, mix_tracks

    sr = 16000
    paths = []
    for i in range(2):
        x = np.zeros(sr * 10, dtype=np.float32)
        x[sr * (2 + 4 * i): sr * (3 + 4 * i)] = 0.3
        f = tmp_path / f"{i}.flac"
        sf.write(f, x, sr)
        paths.append(str(f))
    nome = mix_tracks(paths, tmp_path)
    assert nome == existing_audio(tmp_path)
    with av.open(str(tmp_path / nome)) as c:
        assert 6 <= c.duration / 1e6 <= 9
