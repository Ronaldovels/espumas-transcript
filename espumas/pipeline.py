"""Orquestra as etapas: faixas -> transcrição -> linha do tempo -> métricas -> relatórios."""

from __future__ import annotations

import time
from pathlib import Path

from . import export, report, timeline as tl, vocab
from .metrics import compute_metrics
from .tracks import find_tracks
from .transcribe import Transcriber


def _audio_duration(path: str) -> float | None:
    try:
        import av  # vem junto com o faster-whisper

        with av.open(path) as c:
            if c.duration:
                return c.duration / 1_000_000
            s = c.streams.audio[0]
            return float(s.duration * s.time_base) if s.duration else None
    except Exception:
        return None


def analyze(source: str | Path, out_dir: str | Path, cfg: dict, nome: str | None = None,
            log=print) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    nome = nome or Path(source).stem

    tracks = find_tracks(source, cfg["jogadores"], work_dir=out)
    log(f"{len(tracks)} faixa(s): " + ", ".join(t.player for t in tracks))

    tcfg = cfg["transcricao"]
    transcriber = Transcriber(
        tcfg,
        prompt=vocab.build_prompt(cfg["vocabulario"]),
        hotwords=vocab.build_hotwords(cfg["vocabulario"]),
        cache_dir=out / "cache",
    )
    corrector = vocab.Corrector(cfg["correcoes"])

    per_player = {}
    duracao = 0.0
    for i, track in enumerate(tracks, 1):
        t0 = time.time()
        log(f"[{i}/{len(tracks)}] Transcrevendo {track.player}...")

        last = [-1]

        def progress(t, total, _last=last):
            pct = int(100 * t / total) if total else 0
            if pct >= _last[0] + 10:
                _last[0] = pct
                log(f"    {pct}%")

        segs = transcriber.transcribe(track, progress=progress)
        per_player[track.player] = tl.segments_to_utterances(
            track.player, segs, cfg["metricas"]["juntar_gap_s"], corrector)
        duracao = max(duracao, _audio_duration(track.path) or 0.0)
        log(f"    {len(per_player[track.player])} falas em {time.time() - t0:.0f}s")

    return build_outputs(per_player, [t.player for t in tracks], cfg, out, nome, duracao)


def build_outputs(per_player: dict, players: list[str], cfg: dict, out: Path, nome: str,
                  duracao: float | None = None) -> Path:
    timeline = tl.merge_timeline(per_player)
    metrics = compute_metrics(timeline, players, cfg["metricas"], duracao or None)
    meta = {"nome": nome, "modelo": cfg["transcricao"]["modelo"], "jogadores": players}

    export.write_txt(timeline, out / "transcricao.txt")
    export.write_srt(timeline, out / "transcricao.srt")
    export.write_json(timeline, metrics, meta, out / "analise.json")
    report.render_report(timeline, metrics, meta, out / "relatorio.html")
    return out / "relatorio.html"


def rebuild(analysis_json: str | Path, cfg: dict) -> Path:
    """Refaz métricas e relatório a partir de um analise.json (sem transcrever de novo)."""
    path = Path(analysis_json)
    timeline, old_metrics, meta = export.read_json(path)
    per_player: dict = {}
    for u in timeline:
        per_player.setdefault(u.player, []).append(u)
    players = meta.get("jogadores") or list(per_player)
    duracao = old_metrics.get("resumo", {}).get("duracao_s")
    cfg = {**cfg, "transcricao": {**cfg["transcricao"], "modelo": meta.get("modelo", "?")}}
    return build_outputs(per_player, players, cfg, path.parent, meta.get("nome", path.stem),
                         duracao)
