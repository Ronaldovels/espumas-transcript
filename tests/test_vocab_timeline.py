from espumas.timeline import merge_timeline, segments_to_utterances
from espumas.transcribe import is_hallucination
from espumas.vocab import Corrector, build_prompt


def test_correcoes_padrao():
    c = Corrector()
    assert c("o jet tá no heven") == "o Jett tá no heaven"
    assert c("cuidado com a kill joy") == "cuidado com a Killjoy"
    assert c("planta o espaique") == "planta o spike"


def test_fuzzy_em_nomes_proprios():
    c = Corrector()
    assert c("o brimstoni morreu") == "o Brimstone morreu"
    assert c("tô de phanton") == "tô de Phantom"


def test_fuzzy_nao_estraga_portugues():
    c = Corrector()
    frase = "vamos fazer a classe de sempre, nossa defesa tá verde"
    assert c(frase) == frase


def test_correcao_do_usuario():
    c = Corrector({"ronaldin": "Ronaldo"})
    assert c("ronaldin vai") == "Ronaldo vai"


def test_prompt_tem_jargao():
    p = build_prompt(["Espumas"])
    assert "Sova" in p and "heaven" in p and "Espumas" in p


def test_alucinacoes():
    assert is_hallucination("Legendas pela comunidade Amara.org")
    assert is_hallucination("vai vai vai vai vai vai vai vai vai")
    assert not is_hallucination("vai vai vai")
    assert not is_hallucination("dois no B")


def test_quebra_por_pausa():
    segs = [{"start": 0, "end": 5, "text": "um no mid ... dois no B",
             "words": [
                 {"start": 0.0, "end": 0.3, "text": " um", "prob": 1},
                 {"start": 0.3, "end": 0.5, "text": " no", "prob": 1},
                 {"start": 0.5, "end": 0.9, "text": " mid", "prob": 1},
                 {"start": 3.0, "end": 3.3, "text": " dois", "prob": 1},
                 {"start": 3.3, "end": 3.5, "text": " no", "prob": 1},
                 {"start": 3.5, "end": 3.8, "text": " B", "prob": 1},
             ]}]
    utts = segments_to_utterances("A", segs, gap_s=0.6)
    assert [u.text for u in utts] == ["um no mid", "dois no B"]
    assert utts[1].start == 3.0


def test_merge_ordena():
    a = segments_to_utterances("A", [{"start": 2, "end": 3, "text": "x"}], 0.6)
    b = segments_to_utterances("B", [{"start": 1, "end": 2, "text": "y"}], 0.6)
    assert [u.player for u in merge_timeline({"A": a, "B": b})] == ["B", "A"]
