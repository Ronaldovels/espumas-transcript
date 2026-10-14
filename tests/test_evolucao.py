"""Aba Evolução: agregação das análises salvas."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from espumas.evolucao import coletar
from espumas.web.app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "exemplos"))
import demo  # noqa: E402


def test_coleta_historico(tmp_path):
    demo.historico(tmp_path / "saida", n=6)
    d = coletar(tmp_path / "saida")
    assert len(d["partidas"]) == 6
    datas = [p["data"] for p in d["partidas"]]
    assert datas == sorted(datas)  # da mais antiga para a mais recente
    morto = next(t for t in d["time"] if t["chave"] == "fala_morto_round")
    assert len(morto["serie"]) == 6 and all(v is not None for v in morto["serie"])
    # O histórico de exemplo diminui a fala de morto na segunda metade
    assert morto["tendencia"]["direcao"] == "melhorou"
    assert [j["nome"] for j in d["jogadores"]] == ["Ronaldo", "Kaio", "Bia", "Duda", "Léo"]
    assert sum(m["partidas"] for m in d["mapas"]) == 6


def test_vazio_e_endpoint(tmp_path):
    assert coletar(tmp_path)["partidas"] == []
    demo.historico(tmp_path / "saida", n=2)
    c = TestClient(create_app(tmp_path, tmp_path / "config.yaml"))
    d = c.get("/api/evolucao").json()
    assert len(d["partidas"]) == 2 and d["time"][0]["tendencia"] is None  # poucas partidas
