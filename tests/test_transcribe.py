"""Testa o Transcriber com um WhisperModel falso (filtros e cache), sem baixar modelo."""

import sys
import types
from types import SimpleNamespace as NS

from espumas.config import DEFAULTS
from espumas.models import Track
from espumas.transcribe import Transcriber

CHAMADAS = []


class FakeModel:
    def __init__(self, *a, **kw):
        pass

    def transcribe(self, path, **kw):
        CHAMADAS.append(kw)
        w = lambda s, e, t: NS(start=s, end=e, word=t, probability=0.9)  # noqa: E731
        segs = [
            NS(start=1.0, end=2.0, text=" dois no B", no_speech_prob=0.1, avg_logprob=-0.2,
               words=[w(1.0, 1.4, " dois"), w(1.4, 1.6, " no"), w(1.6, 2.0, " B")]),
            # silêncio que o modelo "achou" que era fala: descartado
            NS(start=5.0, end=6.0, text=" hmm", no_speech_prob=0.9, avg_logprob=-1.5, words=[]),
            # alucinação clássica: descartada
            NS(start=8.0, end=9.0, text=" Legendas pela comunidade Amara.org",
               no_speech_prob=0.3, avg_logprob=-0.5, words=[]),
        ]
        return iter(segs), NS(duration=10.0)


def test_filtros_e_cache(tmp_path, monkeypatch):
    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    CHAMADAS.clear()

    audio = tmp_path / "1-ronaldo.flac"
    audio.write_bytes(b"x")
    t = Transcriber(DEFAULTS["transcricao"], prompt="Valorant", hotwords="Sova",
                    cache_dir=tmp_path / "cache")
    segs = t.transcribe(Track("ronaldo", str(audio)))
    assert [s["text"] for s in segs] == ["dois no B"]
    assert len(segs[0]["words"]) == 3
    kw = CHAMADAS[0]
    assert kw["language"] == "pt" and kw["word_timestamps"] and kw["vad_filter"]
    assert kw["hotwords"] == "Sova" and kw["initial_prompt"] == "Valorant"

    # Segunda vez vem do cache, sem chamar o modelo
    assert t.transcribe(Track("ronaldo", str(audio))) == segs
    assert len(CHAMADAS) == 1
