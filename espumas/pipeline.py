"""Orquestra as etapas:
faixas -> transcrição -> linha do tempo -> métricas -> (partida + sinc) -> relatórios."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rapidfuzz import fuzz

from . import audio as audio_mod, export, report, timeline as tl, vocab
from .config import player_riot
from .game import compute_game_metrics
from .metrics import compute_metrics
from .riot import match_start_datetime
from .sync import synchronize
from .tracks import find_tracks
from .transcribe import Transcriber

Progress = Callable[[float, str], None]


def _audio_duration(path: str) -> float | None:
    try:
        import av  # vem junto com o faster-whisper

        with av.open(path) as c:
            if c.duration:
                return c.duration / 1_000_000
            s = c.streams.audio[0]
            return float(s.duration * s.time_base) if s.duration else None
    except Exception:
        try:
            import soundfile as sf

            info = sf.info(path)
            return info.frames / info.samplerate
        except Exception:
            return None


def _simple(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def guess_riot_map(players: dict[str, str], match: dict, cfg_players: dict) -> dict[str, str]:
    """Liga cada faixa (apelido -> usuário Discord) a um jogador do nosso time na partida.

    Usa primeiro o que está no config; o resto tenta pelo nome parecido.
    """
    team = match.get("nosso_time")
    roster = [p["riot"] for p in match.get("jogadores") or [] if p.get("time") == team]
    out: dict[str, str] = {}
    usados = set()
    for apelido, discord in players.items():
        r = player_riot(cfg_players, discord)
        if r:
            hit = next((x for x in roster if x.lower() == r.lower()), None)
            if hit:
                out[apelido] = hit
                usados.add(hit)
    pares = []
    for apelido, discord in players.items():
        if apelido in out:
            continue
        for r in roster:
            if r in usados:
                continue
            nome = _simple(r.split("#")[0])
            sc = max(fuzz.ratio(_simple(apelido), nome), fuzz.ratio(_simple(discord), nome),
                     fuzz.partial_ratio(_simple(discord), nome) - 10)
            pares.append((sc, apelido, r))
    for sc, apelido, r in sorted(pares, reverse=True):
        if sc < 70 or apelido in out or r in usados:
            continue
        out[apelido] = r
        usados.add(r)
    return out


def analyze(source: str | Path, out_dir: str | Path, cfg: dict, nome: str | None = None,
            log=print, progress: Progress | None = None, match: dict | None = None,
            riot_map: dict[str, str] | None = None,
            manual_anchor_s: float | None = None) -> Path:
    """Analisa uma gravação. `match` é a partida já normalizada (riot.normalize_match)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    nome = nome or Path(source).stem
    prog = progress or (lambda f, m: None)

    prog(0.01, "Lendo as faixas")
    tracks, rec_info = find_tracks(source, cfg["jogadores"], work_dir=out)
    log(f"{len(tracks)} faixa(s): " + ", ".join(t.player for t in tracks))

    extra_vocab = list(cfg["vocabulario"])
    palavra = (cfg.get("sinc") or {}).get("palavra")
    if palavra and palavra not in extra_vocab:
        extra_vocab.append(palavra)
    transcriber = Transcriber(
        cfg["transcricao"],
        prompt=vocab.build_prompt(extra_vocab),
        hotwords=vocab.build_hotwords(extra_vocab),
        cache_dir=out / "cache",
    )
    corrector = vocab.Corrector(cfg["correcoes"])

    per_player = {}
    duracao = 0.0
    n = len(tracks)
    for i, track in enumerate(tracks):
        t0 = time.time()
        msg = f"Transcrevendo {track.player} ({i + 1}/{n})"
        log(msg + "...")
        prog(0.03 + 0.9 * i / n, msg)

        last = [-1]

        def on_seg(t, total, _last=last, _i=i, _msg=msg):
            frac = (t / total) if total else 0
            prog(0.03 + 0.9 * (_i + frac) / n, _msg)
            pct = int(100 * frac)
            if pct >= _last[0] + 10:
                _last[0] = pct
                log(f"    {pct}%")

        segs = transcriber.transcribe(track, progress=on_seg)
        per_player[track.player] = tl.segments_to_utterances(
            track.player, segs, cfg["metricas"]["juntar_gap_s"], corrector)
        duracao = max(duracao, _audio_duration(track.path) or 0.0)
        log(f"    {len(per_player[track.player])} falas em {time.time() - t0:.0f}s")

    if cfg.get("audio_relatorio", True):
        prog(0.93, "Preparando o áudio para ouvir no relatório")
        try:
            audio_mod.mix_tracks([t.path for t in tracks], out)
        except Exception as e:  # noqa: BLE001 — o áudio é um extra; não derruba a análise
            log(f"Não consegui gerar o áudio do relatório: {e}")

    discord = {t.player: t.discord for t in tracks}
    if match is not None and riot_map is None:
        riot_map = guess_riot_map(discord, match, cfg["jogadores"])

    meta = {
        "nome": nome,
        "modelo": cfg["transcricao"]["modelo"],
        "jogadores": [t.player for t in tracks],
        "discord": discord,
        "gravacao_inicio": rec_info["inicio"].isoformat() if rec_info.get("inicio") else None,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ancora_manual_s": manual_anchor_s,
        "riot_map": riot_map or {},
    }
    prog(0.95, "Calculando métricas")
    path = build_outputs(per_player, cfg, out, meta, duracao, match)
    prog(1.0, "Pronto")
    return path


def build_outputs(per_player: dict, cfg: dict, out: Path, meta: dict,
                  duracao: float | None = None, match: dict | None = None) -> Path:
    timeline = tl.merge_timeline(per_player)
    players = meta.get("jogadores") or list(per_player)
    metrics = compute_metrics(timeline, players, cfg["metricas"], duracao or None)

    extra: dict = {"partida": match, "sinc": None, "jogo": None}
    if match:
        rec_start = None
        if meta.get("gravacao_inicio"):
            rec_start = datetime.fromisoformat(meta["gravacao_inicio"])
        sync = synchronize(timeline, match, cfg["sinc"], rec_start, match_start_datetime(match),
                           meta.get("riot_map") or {}, meta.get("ancora_manual_s"))
        extra["sinc"] = sync
        if sync["offset_s"] is not None:
            extra["jogo"] = compute_game_metrics(timeline, match, sync, meta.get("riot_map") or {},
                                                 metrics["sobreposicoes"], cfg["sinc"])

    export.write_txt(timeline, out / "transcricao.txt")
    export.write_srt(timeline, out / "transcricao.srt")
    export.write_json(timeline, metrics, meta, out / "analise.json", extra)
    report.render_report(timeline, metrics, meta, out / "relatorio.html",
                         audio=audio_mod.existing_audio(out), **extra)
    return out / "relatorio.html"


def rebuild(analysis_json: str | Path, cfg: dict) -> Path:
    """Refaz métricas, sinc e relatório a partir de um analise.json (sem transcrever)."""
    path = Path(analysis_json)
    data = export.read_analysis(path)
    meta = data.get("meta", {})
    per_player: dict = {p: [] for p in meta.get("jogadores") or []}
    for u in data["falas"]:
        per_player.setdefault(u.player, []).append(u)
    duracao = data.get("metricas", {}).get("resumo", {}).get("duracao_s")
    cfg = {**cfg, "transcricao": {**cfg["transcricao"], "modelo": meta.get("modelo", "?")}}
    return build_outputs(per_player, cfg, path.parent, meta, duracao, data.get("partida"))
