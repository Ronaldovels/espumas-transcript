"""Saídas em texto: TXT, SRT e JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Utterance


def fmt_clock(t: float) -> str:
    """123.4 -> '02:03'  |  3723 -> '1:02:03'"""
    t = max(0, int(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_srt(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_txt(timeline: list[Utterance], path: Path) -> None:
    lines = [f"[{fmt_clock(u.start)}] {u.player}: {u.text}" for u in timeline]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_srt(timeline: list[Utterance], path: Path) -> None:
    blocks = []
    for i, u in enumerate(timeline, 1):
        end = max(u.end, u.start + 0.5)  # legenda muito curta some antes de ler
        blocks.append(f"{i}\n{fmt_srt(u.start)} --> {fmt_srt(end)}\n[{u.player}] {u.text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_json(timeline: list[Utterance], metrics: dict, meta: dict, path: Path,
               extra: dict | None = None) -> None:
    data = {"meta": meta, "metricas": metrics, **(extra or {}),
            "falas": [u.to_dict() for u in timeline]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> tuple[list[Utterance], dict, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ([Utterance.from_dict(d) for d in data["falas"]], data.get("metricas", {}),
            data.get("meta", {}))


def read_analysis(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["falas"] = [Utterance.from_dict(d) for d in data["falas"]]
    return data
