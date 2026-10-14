"""Interface web local: anexar a gravação, escolher a partida, sincronizar e ver resultados.

Roda só no seu PC (127.0.0.1). Inicie com:  python -m espumas web
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import load_config, player_alias, player_riot, save_config
from ..riot import HenrikClient, RiotAPIError, match_start_datetime, normalize_match
from ..tracks import AUDIO_EXTS, list_zip_players, parse_info_txt, read_recording_info

STATIC = Path(__file__).parent / "static"


# --------------------------------------------------------------------------- estado

class State:
    def __init__(self, root: Path, config_path: Path):
        self.root = root
        self.config_path = config_path
        self.saida = root / "saida"
        self.gravacoes_dir = root / "dados" / "gravacoes"
        self.saida.mkdir(parents=True, exist_ok=True)
        self.gravacoes_dir.mkdir(parents=True, exist_ok=True)
        self.gravacoes: dict[str, dict] = {}
        self.tarefas: dict[str, dict] = {}
        self.fila: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.make_client = lambda cfg: HenrikClient(
            cfg["riot"]["api_key"], cfg["riot"]["regiao"], cfg["riot"]["plataforma"])
        self.analyze = None  # injetável nos testes
        self._client = None
        self._client_key = None
        threading.Thread(target=self._worker, daemon=True).start()

    def cfg(self) -> dict:
        return load_config(self.config_path if self.config_path.exists() else None)

    def client(self, cfg: dict):
        key = (cfg["riot"]["api_key"], cfg["riot"]["regiao"], cfg["riot"]["plataforma"])
        if self._client is None or self._client_key != key:
            self._client = self.make_client(cfg)
            self._client_key = key
        return self._client

    # Uma análise por vez: a GPU é uma só.
    def _worker(self):
        while True:
            tid = self.fila.get()
            t = self.tarefas[tid]
            t.update(estado="rodando", inicio=time.time())
            try:
                self._run(t)
                t.update(estado="pronto", progresso=1.0, etapa="Pronto")
            except Exception as e:  # noqa: BLE001 — o erro vai para a interface
                t.update(estado="erro", erro=str(e) or e.__class__.__name__,
                         detalhe=traceback.format_exc())

    def _run(self, t: dict):
        from ..pipeline import analyze

        fn = self.analyze or analyze
        req = t["pedido"]
        cfg = self.cfg()
        cfg["sinc"].update({k: v for k, v in (req.get("sinc_cfg") or {}).items() if v is not None})
        match = None
        if req.get("partida_id"):
            t["etapa"] = "Buscando a partida"
            raw = self.client(cfg).get_match(req["partida_id"])
            match = normalize_match(raw, cfg["riot"]["riot_id"], cfg["sinc"]["buy_fase_s"])

        def prog(f, msg):
            t.update(progresso=round(f, 3), etapa=msg)

        fn(req["fonte"], t["pasta"], cfg, nome=req["nome"], log=lambda *_: None,
           progress=prog, match=match, riot_map=req.get("riot_map") or None,
           manual_anchor_s=req.get("ancora_manual_s"))


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:40] or "partida"


def _discord_players(fonte: Path) -> tuple[list[str], dict]:
    if fonte.is_file():
        return list_zip_players(fonte), _zip_info(fonte)
    files = sorted(f for f in fonte.iterdir() if f.suffix.lower() in AUDIO_EXTS)
    info = read_recording_info(fonte)
    from ..tracks import _discord_name, _track_number

    files.sort(key=_track_number)
    return [_discord_name(f, info) for f in files], info


def _zip_info(path: Path) -> dict:
    import zipfile

    with zipfile.ZipFile(path) as zf:
        for m in zf.infolist():
            if Path(m.filename).name.lower() == "info.txt":
                return parse_info_txt(zf.read(m).decode("utf-8", errors="replace"))
    return {"inicio": None, "usuarios": {}}


# --------------------------------------------------------------------------- app

class ConfigIn(BaseModel):
    api_key: str | None = None
    riot_id: str | None = None
    regiao: str | None = None
    plataforma: str | None = None
    palavra: str | None = None
    modelo: str | None = None


class CaminhoIn(BaseModel):
    caminho: str


class SincIn(BaseModel):
    modo: str = "padrao"  # padrao | personalizado | manual | nenhum
    round: int | None = None
    fase: str | None = None
    restantes_s: float | None = None
    ancora_manual_s: float | None = None


class JogadorIn(BaseModel):
    discord: str
    apelido: str | None = None
    riot: str | None = None


class AnaliseIn(BaseModel):
    gravacao: str
    nome: str | None = None
    partida_id: str | None = None
    sinc: SincIn = SincIn()
    jogadores: list[JogadorIn] = []


def create_app(root: str | Path = ".", config_path: str | Path = "config.yaml") -> FastAPI:
    root = Path(root).resolve()
    cp = Path(config_path)
    st = State(root, cp if cp.is_absolute() else root / cp)
    app = FastAPI(title="espumas-transcript")
    app.state.st = st

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ----- configurações
    @app.get("/api/config")
    def get_config():
        cfg = st.cfg()
        return {
            "riot_id": cfg["riot"]["riot_id"], "regiao": cfg["riot"]["regiao"],
            "plataforma": cfg["riot"]["plataforma"], "tem_chave": bool(cfg["riot"]["api_key"]),
            "palavra": cfg["sinc"]["palavra"], "modelo": cfg["transcricao"]["modelo"],
        }

    @app.put("/api/config")
    def put_config(body: ConfigIn):
        with st.lock:
            cfg = st.cfg()
            if body.api_key is not None and body.api_key.strip():
                cfg["riot"]["api_key"] = body.api_key.strip()
            if body.riot_id is not None:
                rid = body.riot_id.strip()
                if rid and "#" not in rid:
                    raise HTTPException(400, "Riot ID precisa estar no formato Nome#TAG.")
                cfg["riot"]["riot_id"] = rid
            for campo in ("regiao", "plataforma"):
                v = getattr(body, campo)
                if v:
                    cfg["riot"][campo] = v.strip().lower()
            if body.palavra:
                cfg["sinc"]["palavra"] = body.palavra.strip()
            if body.modelo:
                cfg["transcricao"]["modelo"] = body.modelo.strip()
            save_config(cfg, st.config_path)
        return get_config()

    # ----- gravações
    def _registrar(fonte: Path, nome: str) -> dict:
        try:
            discord, info = _discord_players(fonte)
        except Exception as e:  # zip corrompido etc.
            raise HTTPException(400, f"Não consegui ler a gravação: {e}") from e
        if not discord:
            raise HTTPException(400, "Nenhum arquivo de áudio encontrado. Baixe do Craig em "
                                     "Multi-track (FLAC).")
        gid = uuid.uuid4().hex[:10]
        cfg = st.cfg()
        g = {
            "id": gid, "nome": nome, "fonte": str(fonte),
            "inicio": info["inicio"].isoformat() if info.get("inicio") else None,
            "jogadores": [{"discord": d, "apelido": player_alias(cfg["jogadores"], d),
                           "riot": player_riot(cfg["jogadores"], d)} for d in discord],
        }
        st.gravacoes[gid] = g
        return g

    @app.post("/api/gravacoes")
    def upload(arquivo: UploadFile = File(...)):
        if not (arquivo.filename or "").lower().endswith(".zip"):
            raise HTTPException(400, "Envie o .zip baixado do Craig.")
        dest = st.gravacoes_dir / f"{uuid.uuid4().hex[:8]}-{Path(arquivo.filename).name}"
        with dest.open("wb") as f:
            shutil.copyfileobj(arquivo.file, f, 1 << 20)
        return _registrar(dest, Path(arquivo.filename).stem)

    @app.post("/api/gravacoes/caminho")
    def por_caminho(body: CaminhoIn):
        p = Path(body.caminho.strip().strip('"'))
        if not p.exists():
            raise HTTPException(400, f"Não encontrei: {p}")
        if p.is_file() and p.suffix.lower() != ".zip":
            raise HTTPException(400, "Use o .zip do Craig ou a pasta extraída.")
        return _registrar(p, p.stem)

    # ----- partidas
    @app.get("/api/partidas")
    def partidas(gravacao: str | None = None):
        cfg = st.cfg()
        if not cfg["riot"]["riot_id"]:
            raise HTTPException(400, "Configure seu Riot ID primeiro.")
        try:
            lista = st.client(cfg).list_matches(cfg["riot"]["riot_id"], size=10)
        except (RiotAPIError, ValueError) as e:
            raise HTTPException(400, str(e)) from e
        g = st.gravacoes.get(gravacao or "")
        rec = datetime.fromisoformat(g["inicio"]) if g and g.get("inicio") else None
        for m in lista:
            m["provavel"] = False
            if rec and m.get("inicio"):
                ini = match_start_datetime(m)
                fim = ini + timedelta(seconds=m.get("duracao_s") or 0)
                # A gravação começou antes do fim da partida e no máximo 1h antes do início.
                m["provavel"] = bool(ini and ini - timedelta(hours=1) <= rec <= fim)
        return lista

    @app.get("/api/partidas/{match_id}/time")
    def time_da_partida(match_id: str, gravacao: str | None = None):
        cfg = st.cfg()
        try:
            raw = st.client(cfg).get_match(match_id)
        except RiotAPIError as e:
            raise HTTPException(400, str(e)) from e
        m = normalize_match(raw, cfg["riot"]["riot_id"])
        time_ = [p for p in m["jogadores"] if p["time"] == m["nosso_time"]]
        sugestao = {}
        g = st.gravacoes.get(gravacao or "")
        if g:
            from ..pipeline import guess_riot_map

            apelidos = {j["apelido"]: j["discord"] for j in g["jogadores"]}
            sugestao = guess_riot_map(apelidos, m, cfg["jogadores"])
        return {"time": time_, "sugestao": sugestao, "rounds": len(m["rounds"]),
                "mapa": m["mapa"], "placar": m["placar"]}

    # ----- análises
    @app.post("/api/analises")
    def nova_analise(body: AnaliseIn):
        g = st.gravacoes.get(body.gravacao)
        if not g:
            raise HTTPException(400, "Gravação não encontrada. Anexe de novo.")
        cfg = st.cfg()
        # Lembra apelido e conta Riot de cada um para as próximas vezes.
        with st.lock:
            cfg = st.cfg()
            for j in body.jogadores:
                atual = cfg["jogadores"].get(j.discord)
                atual = atual if isinstance(atual, dict) else ({"apelido": atual} if atual else {})
                if j.apelido:
                    atual["apelido"] = j.apelido.strip()
                if j.riot is not None:
                    atual["riot"] = j.riot or None
                cfg["jogadores"][j.discord] = {k: v for k, v in atual.items() if v}
            save_config(cfg, st.config_path)
        riot_map = {}
        for j in body.jogadores:
            if j.riot:
                riot_map[(j.apelido or player_alias(cfg["jogadores"], j.discord))] = j.riot

        s = body.sinc
        sinc_cfg = {}
        if s.modo == "personalizado":
            sinc_cfg = {"round": s.round or 1, "fase": s.fase or "round",
                        "restantes_s": s.restantes_s if s.restantes_s is not None else 100}
        elif s.modo == "nenhum":
            sinc_cfg = {"palavra": ""}
        elif s.modo == "manual":
            sinc_cfg = {"round": 1, "fase": "round", "restantes_s": 100}

        nome = (body.nome or g["nome"]).strip()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        aid = f"{stamp}-{_slug(nome)}"
        tid = uuid.uuid4().hex[:10]
        st.tarefas[tid] = {
            "id": tid, "analise": aid, "nome": nome, "estado": "na_fila", "progresso": 0.0,
            "etapa": "Na fila", "erro": None, "pasta": str(st.saida / aid),
            "pedido": {"fonte": g["fonte"], "nome": nome, "partida_id": body.partida_id,
                       "sinc_cfg": sinc_cfg, "riot_map": riot_map or None,
                       "ancora_manual_s": s.ancora_manual_s if s.modo == "manual" else None},
        }
        st.fila.put(tid)
        return _tarefa_publica(st.tarefas[tid])

    @app.get("/api/tarefas/{tid}")
    def tarefa(tid: str):
        t = st.tarefas.get(tid)
        if not t:
            raise HTTPException(404, "Tarefa não encontrada.")
        return _tarefa_publica(t)

    @app.get("/api/analises")
    def analises():
        out = []
        for f in sorted(st.saida.glob("*/analise.json"), reverse=True):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            meta, r = d.get("meta", {}), d.get("metricas", {}).get("resumo", {})
            p = d.get("partida") or {}
            jogo = d.get("jogo") or {}
            morto = sum(x.get("segundos", 0) for x in
                        (jogo.get("fala_de_morto") or {}).get("por_jogador", {}).values())
            out.append({
                "id": f.parent.name, "nome": meta.get("nome"), "criado_em": meta.get("criado_em"),
                "mapa": p.get("mapa"), "placar": p.get("placar"),
                "interrupcoes": r.get("interrupcoes"),
                "sobreposicao_pct": r.get("sobreposicao_pct_da_fala"),
                "fala_morto_s": round(morto, 1) if jogo else None,
                "sinc": (d.get("sinc") or {}).get("metodo"),
                "duracao_s": r.get("duracao_s"),
            })
        rodando = [_tarefa_publica(t) for t in st.tarefas.values()
                   if t["estado"] in ("na_fila", "rodando")]
        falhas = [_tarefa_publica(t) for t in st.tarefas.values() if t["estado"] == "erro"]
        return {"analises": out, "em_andamento": rodando, "falhas": falhas}

    @app.get("/relatorios/{aid}")
    def relatorio_sem_barra(aid: str):
        # Com a barra no fim, o "audio.webm" relativo do relatório aponta para a pasta certa.
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", aid):
            raise HTTPException(404)
        return RedirectResponse(f"/relatorios/{aid}/")

    @app.get("/relatorios/{aid}/")
    def relatorio(aid: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", aid):
            raise HTTPException(404)
        f = st.saida / aid / "relatorio.html"
        if not f.exists():
            raise HTTPException(404, "Relatório não encontrado.")
        return FileResponse(f, media_type="text/html")

    @app.get("/relatorios/{aid}/{arquivo}")
    def arquivo_relatorio(aid: str, arquivo: str):
        permitido = {"transcricao.txt", "transcricao.srt", "analise.json", "relatorio.html",
                     "audio.webm", "audio.m4a"}
        if arquivo not in permitido or not re.fullmatch(r"[A-Za-z0-9_.-]+", aid):
            raise HTTPException(404)
        f = st.saida / aid / arquivo
        if not f.exists():
            raise HTTPException(404)
        if arquivo.startswith("audio."):
            return FileResponse(f)  # sem "download": o navegador toca e pula no tempo
        return FileResponse(f, filename=arquivo if arquivo != "relatorio.html" else None)

    return app


def _tarefa_publica(t: dict) -> dict:
    return {k: t.get(k) for k in ("id", "analise", "nome", "estado", "progresso", "etapa", "erro")}


def run(host: str = "127.0.0.1", port: int = 8765, abrir: bool = True) -> None:
    import uvicorn

    if abrir:
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    print(f"Interface em http://{host}:{port}  (Ctrl+C para fechar)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
