"""Encontra as faixas de cada jogador numa gravação do Craig (pasta ou .zip).

Formato do Craig (conferido no código-fonte dele, CraigChat/craig):
- cada arquivo se chama "<n>-<usuário>", com tudo que não é letra/número trocado por "_"
  (ex.: "ronaldo.vels" -> "1-ronaldo_vels.flac");
- todas as faixas começam no instante em que a gravação começou (estão alinhadas);
- o info.txt traz "Start time:" em ISO/UTC e a lista de usuários na ordem das faixas.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

from .config import player_alias
from .models import Track

AUDIO_EXTS = {".flac", ".ogg", ".opus", ".wav", ".m4a", ".aac", ".mp3", ".mka", ".webm"}

_PREFIX = re.compile(r"^(\d+)-")


def craig_safe(name: str) -> str:
    """Mesma limpeza que o Craig aplica no nome do arquivo."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name)


def player_from_filename(path: Path) -> str:
    """'3-ronaldo_vels.flac' -> 'ronaldo_vels'."""
    name = _PREFIX.sub("", path.stem)
    return name.strip() or path.stem


def _track_number(path: Path) -> int:
    m = _PREFIX.match(path.stem)
    return int(m.group(1)) if m else 10_000


def parse_info_txt(text: str) -> dict:
    """Lê o info.txt do Craig: horário de início e usuários por número de faixa."""
    info: dict = {"inicio": None, "usuarios": {}}
    m = re.search(r"Start time:\s*(\S+)", text)
    if m:
        try:
            info["inicio"] = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except ValueError:
            pass
    bloco = text.split("Tracks:", 1)[1] if "Tracks:" in text else ""
    bloco = bloco.split("Notes:", 1)[0]
    n = 0
    for line in bloco.splitlines():
        line = line.strip()
        if not line:
            continue
        n += 1
        user = re.sub(r"\s*\(\d+\)\s*$", "", line)  # tira "(id)"
        user = re.sub(r"#0$", "", user)  # discriminador zero = usuário novo
        info["usuarios"][n] = user
    return info


def _extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # Só o nome do arquivo: ignora pastas e caminhos perigosos (../).
            name = Path(member.filename).name
            if not name:
                continue
            if Path(name).suffix.lower() not in AUDIO_EXTS and name.lower() != "info.txt":
                continue
            target = dest / name
            if not target.exists():
                with zf.open(member) as src, target.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
    return dest


def resolve_source(source: str | Path, work_dir: str | Path | None = None) -> Path:
    src = Path(source)
    if src.is_file() and src.suffix.lower() == ".zip":
        base = Path(work_dir) if work_dir else src.parent
        src = _extract_zip(src, base / "faixas")
    if not src.is_dir():
        raise FileNotFoundError(f"Não achei a pasta/zip da gravação: {source}")
    return src


def read_recording_info(folder: Path) -> dict:
    f = folder / "info.txt"
    if f.exists():
        return parse_info_txt(f.read_text(encoding="utf-8", errors="replace"))
    return {"inicio": None, "usuarios": {}}


def list_zip_players(zip_path: str | Path) -> list[str]:
    """Nomes do Discord dentro do .zip, sem extrair (para a interface)."""
    with zipfile.ZipFile(zip_path) as zf:
        info = {}
        files = []
        for m in zf.infolist():
            name = Path(m.filename).name
            if name.lower() == "info.txt":
                info = parse_info_txt(zf.read(m).decode("utf-8", errors="replace"))
            elif Path(name).suffix.lower() in AUDIO_EXTS:
                files.append(Path(name))
    files.sort(key=_track_number)
    return [_discord_name(f, info) for f in files]


def _discord_name(f: Path, info: dict) -> str:
    raw = player_from_filename(f)
    real = info.get("usuarios", {}).get(_track_number(f))
    # Usa o nome "de verdade" do info.txt se ele bate com o do arquivo.
    if real and craig_safe(real) == raw:
        return real
    return raw


def find_tracks(source: str | Path, cfg_players: dict | None = None,
                work_dir: str | Path | None = None) -> tuple[list[Track], dict]:
    """Lista as faixas (uma por jogador) e as informações da gravação.

    `source` pode ser a pasta extraída do Craig ou o .zip baixado.
    """
    src = resolve_source(source, work_dir)
    info = read_recording_info(src)

    files = sorted((f for f in src.iterdir() if f.suffix.lower() in AUDIO_EXTS),
                   key=lambda f: (_track_number(f), f.name))
    tracks: list[Track] = []
    for f in files:
        discord = _discord_name(f, info)
        tracks.append(Track(player=player_alias(cfg_players, discord), path=str(f),
                            discord=discord))

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
    return tracks, info
