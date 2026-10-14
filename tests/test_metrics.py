from espumas.config import DEFAULTS
from espumas.metrics import compute_metrics, find_overlaps, has_order, sites_in
from espumas.models import Utterance, Word

CFG = DEFAULTS["metricas"]


def U(p, s, e, text):
    n = len(text.split())
    step = (e - s) / n
    words = [Word(s + i * step, s + (i + 1) * step, " " + w) for i, w in enumerate(text.split())]
    return Utterance(p, s, e, text, words)


def test_interrupcao_e_quem_cortou():
    tl = [U("A", 0.0, 4.0, "dois no B main um tapado cem"),
          U("B", 2.0, 5.0, "ô galera vamo comprar o que")]
    ev = find_overlaps(tl, CFG)
    assert len(ev) == 1
    assert ev[0].tipo == "interrupcao"
    assert ev[0].primeiro == "A" and ev[0].segundo == "B"
    assert ev[0].duration == 2.0


def test_backchannel_nao_conta_como_interrupcao():
    tl = [U("A", 0.0, 4.0, "vou pegar o heaven aqui"), U("B", 1.0, 1.5, "boa")]
    assert find_overlaps(tl, CFG)[0].tipo == "backchannel"


def test_comecaram_juntos():
    tl = [U("A", 1.0, 3.0, "um no mid"), U("B", 1.1, 3.0, "dois no A main")]
    assert find_overlaps(tl, CFG)[0].tipo == "simultaneo"


def test_sobreposicao_curta_ignorada():
    tl = [U("A", 0.0, 2.0, "um no mid"), U("B", 1.9, 3.0, "vai rotate")]
    assert find_overlaps(tl, CFG) == []


def test_metricas_completas():
    tl = [
        U("A", 0.0, 4.0, "dois no B main um tapado cem"),
        U("B", 2.0, 5.0, "ô galera vamo comprar o que"),
        U("C", 3.0, 4.5, "vai pro A agora"),
        U("D", 3.5, 6.0, "roda pro B roda"),
        U("E", 20.0, 30.0, " ".join(["blablabla"] * 20)),
    ]
    m = compute_metrics(tl, ["A", "B", "C", "D", "E"], CFG, duracao_total=60.0)
    r = m["resumo"]
    assert r["duracao_s"] == 60.0
    assert r["interrupcoes"] >= 3
    assert r["tempo_3mais_falando_s"] > 0
    assert r["callouts_longos"] == 1
    assert r["conflitos_de_site"] >= 1
    assert m["jogadores"]["A"]["foi_interrompido"] >= 2
    assert abs(sum(d["participacao_pct"] for d in m["jogadores"].values()) - 100) < 0.5
    assert 0 < r["silencio_pct"] < 100
    assert m["destaques"]


def test_jogador_sem_fala_aparece_zerado():
    m = compute_metrics([U("A", 0, 1, "oi")], ["A", "Mudo"], CFG)
    assert m["jogadores"]["Mudo"]["falas"] == 0


def test_timeline_vazia():
    m = compute_metrics([], ["A"], CFG)
    assert m["resumo"]["interrupcoes"] == 0


def test_ordens_e_sites():
    assert has_order("roda pro B")
    assert not has_order("um tapado cem")
    assert sites_in("roda pro B agora") == {"B"}
    assert sites_in("a gente vai") == set()  # "a" minúsculo é artigo, não site
