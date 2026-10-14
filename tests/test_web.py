"""Fluxo completo da interface com API da partida e transcrição falsas."""

import time
import zipfile

import numpy as np
import pytest
import soundfile as sf
import yaml
from fastapi.testclient import TestClient

from espumas import exemplo
from espumas.riot import summarize
from espumas.transcribe import Transcriber
from espumas.web.app import create_app

OFFSET = 312.4
DISCORD = ["ronaldo.vels", "kaio", "bia", "duda", "leo"]
APELIDOS = [a for a, _, _ in exemplo.NOSSOS]


class FakeHenrik:
    def __init__(self, raw):
        self.raw = raw

    def list_matches(self, riot_id, size=10):
        outra = {**self.raw, "metadata": {**self.raw["metadata"], "match_id": "velha",
                                          "started_at": "2026-10-01T10:00:00Z"}}
        return [summarize(self.raw, riot_id), summarize(outra, riot_id)]

    def get_match(self, mid):
        return self.raw


@pytest.fixture
def craig_zip(tmp_path):
    z = tmp_path / "craig_abc.flac.zip"
    silence = np.zeros(8000, dtype=np.float32)
    inicio = exemplo.craig_inicio(OFFSET, erro_s=15).isoformat().replace("+00:00", "Z")
    info = (f"Recording abc\r\n\r\nStart time:\t{inicio}\r\n\r\nTracks:\r\n"
            + "".join(f"\t{d}#0 ({i})\r\n" for i, d in enumerate(DISCORD)))
    with zipfile.ZipFile(z, "w") as zf:
        for i, d in enumerate(DISCORD, 1):
            f = tmp_path / f"{i}-{d.replace('.', '_')}.flac"
            sf.write(f, silence, 16000)
            zf.write(f, f"craig_abc/{f.name}")
        zf.writestr("craig_abc/info.txt", info)
    return z


@pytest.fixture
def client(tmp_path, monkeypatch):
    raw = exemplo.raw_match()
    per = exemplo.call_sintetica(raw, OFFSET)
    por_arquivo = {d.replace(".", "_"): APELIDOS[i] for i, d in enumerate(DISCORD)}

    def fake_transcribe(self, track, progress=None):
        from pathlib import Path

        nome = Path(track.path).stem.split("-", 1)[1]
        if progress:
            progress(1, 1)
        return [{"start": u.start, "end": u.end, "text": u.text,
                 "words": [{"start": w.start, "end": w.end, "text": w.text, "prob": 1.0}
                           for w in u.words]} for u in per[por_arquivo[nome]]]

    monkeypatch.setattr(Transcriber, "transcribe", fake_transcribe)
    app = create_app(tmp_path, tmp_path / "config.yaml")
    app.state.st.make_client = lambda cfg: FakeHenrik(raw)
    return TestClient(app), tmp_path


def test_fluxo_completo(client, craig_zip):
    c, root = client

    r = c.get("/")
    assert r.status_code == 200 and "Espumas" in r.text

    r = c.put("/api/config", json={"riot_id": "sem-tag"})
    assert r.status_code == 400
    r = c.put("/api/config", json={"api_key": "abc", "riot_id": "Ronaldovels#BR1"})
    assert r.json()["tem_chave"] is True

    with craig_zip.open("rb") as f:
        g = c.post("/api/gravacoes", files={"arquivo": ("craig_abc.flac.zip", f, "application/zip")}).json()
    assert [j["discord"] for j in g["jogadores"]] == DISCORD  # nomes reais do info.txt
    assert g["inicio"]

    lista = c.get("/api/partidas", params={"gravacao": g["id"]}).json()
    assert lista[0]["provavel"] is True and lista[1]["provavel"] is False
    assert lista[0]["mapa"] == "Ascent"

    t = c.get(f"/api/partidas/{lista[0]['id']}/time", params={"gravacao": g["id"]}).json()
    assert len(t["time"]) == 5
    assert t["sugestao"].get("ronaldo.vels") == "Ronaldovels#BR1"  # sugerido pelo nome

    jogadores = [{"discord": d, "apelido": APELIDOS[i], "riot": exemplo.NOSSOS[i][1]}
                 for i, d in enumerate(DISCORD)]
    tarefa = c.post("/api/analises", json={
        "gravacao": g["id"], "nome": "Ascent teste", "partida_id": lista[0]["id"],
        "sinc": {"modo": "padrao"}, "jogadores": jogadores}).json()

    for _ in range(100):
        t = c.get(f"/api/tarefas/{tarefa['id']}").json()
        if t["estado"] in ("pronto", "erro"):
            break
        time.sleep(0.05)
    assert t["estado"] == "pronto", t

    hist = c.get("/api/analises").json()
    a = hist["analises"][0]
    assert a["nome"] == "Ascent teste" and a["mapa"] == "Ascent" and a["sinc"] == "palavra"
    assert a["fala_morto_s"] > 0

    page = c.get(f"/relatorios/{a['id']}")
    assert page.status_code == 200 and "Rounds" in page.text and "Kaio" in page.text
    assert c.get(f"/relatorios/{a['id']}/transcricao.srt").status_code == 200
    # Áudio para ouvir no relatório: link relativo resolve dentro da pasta da análise
    assert 'id="player"' in page.text and 'src="audio.webm"' in page.text
    assert str(page.url).endswith(f"/relatorios/{a['id']}/")
    au = c.get(f"/relatorios/{a['id']}/audio.webm", headers={"Range": "bytes=0-99"})
    assert au.status_code == 206 and len(au.content) == 100
    assert c.get(f"/relatorios/{a['id']}/../config.yaml").status_code == 404

    # Apelidos e contas ficaram salvos para a próxima vez
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["jogadores"]["kaio"] == {"apelido": "Kaio", "riot": "kaiozin#0001"}
    g2 = c.post("/api/gravacoes/caminho", json={"caminho": str(craig_zip)}).json()
    assert g2["jogadores"][1]["apelido"] == "Kaio"


def test_erros_claros(client, tmp_path):
    c, _ = client
    assert c.post("/api/gravacoes/caminho", json={"caminho": str(tmp_path / "nada.zip")}).status_code == 400
    assert "Riot ID" in c.get("/api/partidas").json()["detail"]
    assert c.post("/api/analises", json={"gravacao": "x"}).status_code == 400
