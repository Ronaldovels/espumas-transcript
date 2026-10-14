"""Teste ponta a ponta com faixas sintéticas e transcrição falsa (não precisa de GPU)."""

import json
import zipfile

import numpy as np
import pytest
import soundfile as sf

from espumas import pipeline
from espumas.config import load_config
from espumas.tracks import find_tracks, player_from_filename
from espumas.transcribe import Transcriber

FALAS = {
    "ronaldovels": [(1.0, 3.0, "dois no B main um tapado"), (10.0, 11.0, "roda pro B")],
    "amigo1": [(2.0, 4.0, "vamo comprar o que galera"), (10.5, 12.0, "vai pro A agora")],
    "amigo2": [(5.0, 5.4, "boa")],
}


def _seg(s, e, text):
    ws = text.split()
    step = (e - s) / len(ws)
    return {"start": s, "end": e, "text": text,
            "words": [{"start": s + i * step, "end": s + (i + 1) * step, "text": " " + w,
                       "prob": 0.9} for i, w in enumerate(ws)]}


@pytest.fixture
def craig_dir(tmp_path):
    d = tmp_path / "craig_abc"
    d.mkdir()
    silence = np.zeros(16000 * 15, dtype=np.float32)
    for i, name in enumerate(FALAS, 1):
        sf.write(d / f"{i}-{name}_0.flac", silence, 16000)
    (d / "info.txt").write_text("Craig")
    return d


@pytest.fixture
def fake_transcriber(monkeypatch):
    def fake(self, track, progress=None):
        from pathlib import Path

        key = Path(track.path).stem.split("-", 1)[1].rsplit("_", 1)[0]
        if progress:
            progress(15.0, 15.0)
        return [_seg(*f) for f in FALAS[key]]

    monkeypatch.setattr(Transcriber, "transcribe", fake)


def test_nomes_do_craig():
    from pathlib import Path

    assert player_from_filename(Path("1-ronaldovels_0.flac")) == "ronaldovels"
    assert player_from_filename(Path("12-Fulano#1234.ogg")) == "Fulano"
    assert player_from_filename(Path("3-nome-com-hifen.flac")) == "nome-com-hifen"


def test_encontra_faixas_e_apelidos(craig_dir):
    tracks = find_tracks(craig_dir, {"RonaldoVels": "Ronaldo"})
    assert [t.player for t in tracks] == ["Ronaldo", "amigo1", "amigo2"]


def test_zip(craig_dir, tmp_path):
    z = tmp_path / "partida.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in craig_dir.iterdir():
            zf.write(f, f"craig_abc/{f.name}")
    tracks = find_tracks(z, work_dir=tmp_path / "out")
    assert len(tracks) == 3


def test_ponta_a_ponta(craig_dir, tmp_path, fake_transcriber):
    cfg = load_config()
    cfg["jogadores"] = {"ronaldovels": "Ronaldo"}
    out = tmp_path / "saida"
    html = pipeline.analyze(craig_dir, out, cfg, nome="Ascent 13-11", log=lambda *_: None)

    for f in ["relatorio.html", "transcricao.txt", "transcricao.srt", "analise.json"]:
        assert (out / f).exists(), f

    data = json.loads((out / "analise.json").read_text(encoding="utf-8"))
    r = data["metricas"]["resumo"]
    assert r["interrupcoes"] == 2  # amigo1 entrou por cima do Ronaldo duas vezes
    assert r["backchannels"] == 0  # "boa" não sobrepôs ninguém
    assert r["conflitos_de_site"] == 1  # "roda pro B" x "vai pro A"
    assert data["metricas"]["jogadores"]["Ronaldo"]["foi_interrompido"] == 2

    txt = (out / "transcricao.txt").read_text(encoding="utf-8")
    assert txt.splitlines()[0] == "[00:01] Ronaldo: dois no B main um tapado"
    srt = (out / "transcricao.srt").read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:03,000" in srt

    page = html.read_text(encoding="utf-8")
    assert "Ascent 13-11" in page and "Ronaldo" in page and "<svg" in page

    # Mudar limites e refazer o relatório sem transcrever de novo
    cfg["metricas"]["min_sobreposicao_s"] = 5.0
    pipeline.rebuild(out / "analise.json", cfg)
    data2 = json.loads((out / "analise.json").read_text(encoding="utf-8"))
    assert data2["metricas"]["resumo"]["interrupcoes"] == 0
    assert data2["meta"]["nome"] == "Ascent 13-11"


def test_pasta_vazia(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_tracks(tmp_path)
