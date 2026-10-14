"""Mistura as faixas do Craig num único áudio leve para ouvir no relatório.

Usa PyAV (vem com o faster-whisper), então não precisa de ffmpeg instalado.
Saída: audio.webm (Opus, ~32 kbps; ~8 MB por partida de 40 min). Se o Opus não estiver
disponível, cai para audio.m4a (AAC).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

SR = 24_000
NOMES = ("audio.webm", "audio.m4a")


def existing_audio(folder: Path) -> str | None:
    for n in NOMES:
        if (Path(folder) / n).exists():
            return n
    return None


def _decode_into(path: str, mix: np.ndarray | None, sr: int) -> np.ndarray:
    import av

    with av.open(path) as c:
        stream = c.streams.audio[0]
        res = av.AudioResampler(format="flt", layout="mono", rate=sr)
        pos = 0
        for frame in c.decode(stream):
            for out in res.resample(frame):
                data = out.to_ndarray().reshape(-1)
                # Usa o carimbo de tempo quando existe (faixas com buracos ficam alinhadas).
                if out.time is not None:
                    pos = int(round(out.time * sr))
                end = pos + data.size
                if mix is None or end > mix.size:
                    novo = np.zeros(max(end, int((mix.size if mix is not None else 0) * 1.5)),
                                    dtype=np.float32)
                    if mix is not None:
                        novo[:mix.size] = mix
                    mix = novo
                mix[pos:end] += data
                pos = end
        for out in res.resample(None):
            data = out.to_ndarray().reshape(-1)
            end = pos + data.size
            if end <= mix.size:
                mix[pos:end] += data
            pos = end
    return mix


def mix_tracks(paths: list[str], out_dir: str | Path,
               progress: Callable[[float], None] | None = None) -> str | None:
    """Mistura as faixas e devolve o nome do arquivo gerado (ou None se falhar)."""
    out_dir = Path(out_dir)
    mix: np.ndarray | None = None
    ultimo = 0
    for i, p in enumerate(paths):
        mix = _decode_into(p, mix, SR)
        if progress:
            progress((i + 1) / (len(paths) + 1))
    if mix is None:
        return None
    # Corta o excesso de pré-alocação (silêncio no fim)
    nz = np.flatnonzero(np.abs(mix) > 1e-5)
    ultimo = int(nz[-1]) + SR if nz.size else 0
    mix = mix[:max(ultimo, SR)]
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0.95:
        mix *= 0.95 / peak
    for nome, codec in (("audio.webm", "libopus"), ("audio.m4a", "aac")):
        try:
            _encode(mix, out_dir / nome, codec)
            for outro in NOMES:  # remove versão antiga em outro formato
                if outro != nome and (out_dir / outro).exists():
                    (out_dir / outro).unlink()
            return nome
        except Exception:  # noqa: BLE001 — tenta o próximo codec
            (out_dir / nome).unlink(missing_ok=True)
    return None


def _encode(mix: np.ndarray, path: Path, codec: str) -> None:
    import av

    with av.open(str(path), "w") as c:
        st = c.add_stream(codec, rate=SR)
        st.layout = "mono"
        st.bit_rate = 32_000 if codec == "libopus" else 48_000
        bloco = SR  # 1 s por vez
        for i in range(0, mix.size, bloco):
            chunk = np.ascontiguousarray(mix[i:i + bloco].reshape(1, -1))
            frame = av.AudioFrame.from_ndarray(chunk, format="flt", layout="mono")
            frame.sample_rate = SR
            frame.pts = i
            for pkt in st.encode(frame):
                c.mux(pkt)
        for pkt in st.encode(None):
            c.mux(pkt)
