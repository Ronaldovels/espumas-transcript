"""Encontra as faixas de cada jogador numa gravação do Craig (pasta ou .zip)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .models import Track

AUDIO_EXTS = {".flac", ".ogg", ".opus", ".wav", ".m4a", ".aac", ".mp3", ".mka", ".webm"}

_PREFIX = re.compile(r"^\d+-")  # "1-ronaldovels"
_SUFFIX = re.compile(r"(_\d+|#\d{4})$")  # "_0" ou "#1234"


def player_from_filename(path: Path) -> str:
    """'3-ronaldovels_0.flac' -> 'ronaldovels'."""
    name = path.stem
    name = _PREFIX.sub("", name)
    name = _SUFFIX.sub("", name)
    return name.strip() or path.stem


def _extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # Ignora caminhos perigosos (../) e qualquer coisa que não seja áudio.
            name = Path(member.filename).name
            if not name or Path(name).suffix.lower() not in AUDIO_EXTS:
                continue
            target = dest / name
            if not target.exists():
                with zf.open(member) as src, target.open("wb") as dst:
                    dst.write(src.read())
    return dest


def find_tracks(source: str | Path, aliases: dict[str, str] | None = None,
                work_dir: str | Path | None = None) -> list[Track]:
    """Lista as faixas de áudio, uma por jogador.

    `source` pode ser a pasta extraída do Craig ou o .zip baixado.
    `aliases` mapeia nome do arquivo -> apelido (comparação sem maiúsculas).
    """
    src = Path(source)
    if src.is_file() and src.suffix.lower() == ".zip":
        base = Path(work_dir) if work_dir else src.parent
        src = _extract_zip(src, base / f"{src.stem}_faixas")
    if not src.is_dir():
        raise FileNotFoundError(f"Não achei a pasta/zip da gravação: {source}")

    alias_map = {k.lower(): v for k, v in (aliases or {}).items()}
    tracks: list[Track] = []
    for f in sorted(src.iterdir()):
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        raw = player_from_filename(f)
        player = alias_map.get(raw.lower(), raw)
        tracks.append(Track(player=player, path=str(f)))

    if not tracks:
        raise FileNotFoundError(
            f"Nenhum arquivo de áudio em {src}. Baixe a gravação do Craig em "
            "'Multi-track' (FLAC ou Ogg)."
        )
    names = [t.player for t in tracks]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        # Dois arquivos com o mesmo jogador: numeramos para não misturar.
        seen: dict[str, int] = {}
        for t in tracks:
            if t.player in dupes:
                seen[t.player] = seen.get(t.player, 0) + 1
                if seen[t.player] > 1:
                    t.player = f"{t.player} ({seen[t.player]})"
    return tracks
