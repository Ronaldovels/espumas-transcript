"""Transcrição de cada faixa com faster-whisper, com cache em disco."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from .models import Track

# Frases que o Whisper costuma "inventar" em silêncio/ruído.
ALUCINACOES = [
    r"legendas? pela comunidade amara\.org",
    r"obrigad[oa] por assistir",
    r"inscreva-se no canal",
    r"legendado por",
    r"^\W*(música|musica|aplausos|risos)\W*$",
    r"^\W*$",
]
_ALUC_RE = [re.compile(p, re.IGNORECASE) for p in ALUCINACOES]


def _windows_cuda_dlls() -> None:
    """No Windows, registra as DLLs de cuBLAS/cuDNN instaladas via pip (pacotes nvidia-*)."""
    if sys.platform != "win32":
        return
    try:
        import nvidia  # type: ignore
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            bin_dir = Path(base) / sub / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def is_hallucination(text: str) -> bool:
    t = text.strip()
    if any(r.search(t) for r in _ALUC_RE):
        return True
    # Repetição em loop: "vai vai vai vai vai vai vai vai"
    words = t.lower().split()
    if len(words) >= 8 and len(set(words)) <= 2:
        return True
    return False


def _cache_key(track: Track, cfg: dict, prompt: str) -> str:
    st = os.stat(track.path)
    payload = json.dumps(
        {
            "path": os.path.abspath(track.path),
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "cfg": cfg,
            "prompt": prompt,
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


# Modelos já carregados, reaproveitados entre análises (a interface roda várias seguidas).
_MODELOS: dict[tuple, object] = {}


class Transcriber:
    """Carrega o modelo uma vez e transcreve várias faixas."""

    def __init__(self, cfg: dict, prompt: str, hotwords: str | None = None,
                 cache_dir: str | Path | None = None):
        self.cfg = cfg
        self.prompt = prompt
        self.hotwords = hotwords
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        key = (self.cfg["modelo"], self.cfg["dispositivo"], self.cfg["compute_type"])
        if key not in _MODELOS:
            _windows_cuda_dlls()
            from faster_whisper import WhisperModel  # import tardio: testes não precisam

            _MODELOS[key] = WhisperModel(key[0], device=key[1], compute_type=key[2])
        self._model = _MODELOS[key]
        return self._model

    def transcribe(self, track: Track, progress=None) -> list[dict]:
        """Retorna segmentos [{start, end, text, words:[{start,end,text,prob}]}]."""
        cache_file = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            key = _cache_key(track, self.cfg, self.prompt)
            cache_file = self.cache_dir / f"{Path(track.path).stem}.{key}.json"
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))

        model = self._load()
        segments, info = model.transcribe(
            track.path,
            language=self.cfg["idioma"],
            beam_size=self.cfg["beam_size"],
            initial_prompt=self.prompt,
            hotwords=self.hotwords,
            word_timestamps=True,
            # Cada fala é curta e independente: condicionar no texto anterior
            # aumenta alucinação em loop.
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 150},
        )

        out: list[dict] = []
        for seg in segments:
            if progress:
                progress(seg.end, info.duration)
            if (seg.no_speech_prob > self.cfg["max_no_speech_prob"]
                    and seg.avg_logprob < self.cfg["min_avg_logprob"]):
                continue
            if is_hallucination(seg.text):
                continue
            words = [
                {"start": round(w.start, 3), "end": round(w.end, 3),
                 "text": w.word, "prob": round(w.probability, 3)}
                for w in (seg.words or [])
            ]
            out.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "words": words,
            })

        if cache_file:
            cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out
