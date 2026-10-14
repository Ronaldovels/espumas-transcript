"""Relatório HTML autocontido (abre direto no navegador, sem internet)."""

from __future__ import annotations

import html
from pathlib import Path

from .export import fmt_clock
from .game import FASE_LABEL
from .models import Utterance

CORES = ["#3b82f6", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6",
         "#06b6d4", "#ef4444", "#84cc16", "#f97316", "#64748b"]

PAGINA_S = 120  # sem partida: cada linha da linha do tempo cobre 2 minutos

_TIPO_LABEL = {
    "interrupcao": "Interrupção",
    "simultaneo": "Falaram juntos",
    "backchannel": "Resposta curta",
}
_METODO_LABEL = {
    "palavra": "palavra de sinc",
    "manual": "momento informado",
    "relogio": "horário do Craig x horário da partida",
    "nenhum": "sem sincronização",
}

CSS = """
:root{--bg:#f7f7f8;--card:#fff;--fg:#17181c;--muted:#6b7080;--line:#e3e4e8;--bad:#dc2626;
--bad-bg:rgba(220,38,38,.12);--warn:#d97706;--good:#059669;--good-bg:rgba(5,150,105,.12);
--chip-fg:#fff;--buy:rgba(100,116,139,.10)}
@media (prefers-color-scheme:dark){:root{--bg:#111215;--card:#1a1b20;--fg:#ececf1;
--muted:#9a9eab;--line:#2b2d35;--bad:#f87171;--bad-bg:rgba(248,113,113,.16);--warn:#fbbf24;
--good:#34d399;--good-bg:rgba(52,211,153,.14);--buy:rgba(148,163,184,.10)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}
.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--muted);font-size:13px}
ul.dest{margin:0;padding-left:20px}ul.dest li{margin:4px 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
td.n{text-align:right}th.n{text-align:right}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;color:var(--chip-fg);
font-size:12px;font-weight:600;white-space:nowrap}
.bar{height:8px;border-radius:4px;background:var(--line);min-width:80px}
.bar>span{display:block;height:100%;border-radius:4px}
.tl-row{display:flex;gap:8px;align-items:stretch;padding:6px 0;border-bottom:1px dashed var(--line)}
.tl-row:last-of-type{border-bottom:0}
.tl-t{width:56px;flex:none;color:var(--muted);font-size:12px;padding-top:2px;
font-variant-numeric:tabular-nums;line-height:1.3}
.tl-t b{color:var(--fg);font-weight:650}
.tl-box{flex:1;min-width:0}.tl-box svg{height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.tag{font-size:12px;font-weight:600;padding:1px 6px;border-radius:4px;white-space:nowrap}
.tag.interrupcao,.tag.L,.tag.morto{background:var(--bad-bg);color:var(--bad)}
.tag.simultaneo{background:rgba(217,119,6,.14);color:var(--warn)}
.tag.backchannel,.tag.fase{background:var(--line);color:var(--muted)}
.tag.W{background:var(--good-bg);color:var(--good)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;align-items:center}
.filters button{border:1px solid var(--line);background:var(--card);color:var(--fg);
border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer}
.filters button[aria-pressed=false]{opacity:.45}
.tr{display:grid;grid-template-columns:52px 120px 1fr;gap:8px;padding:6px 4px;
border-bottom:1px solid var(--line)}
.tr .t{color:var(--muted);font-variant-numeric:tabular-nums;font-size:13px;padding-top:1px}
.tr .t small{display:block;font-size:11px}
.tr.hit{background:var(--bad-bg)}
.tr .x .tag{margin-left:6px}
.rsep{padding:10px 4px 4px;font-size:12px;font-weight:650;color:var(--muted);
text-transform:uppercase;letter-spacing:.04em}
@media (max-width:600px){.tr{grid-template-columns:44px 1fr}.tr .p{grid-column:2}
.tr .x{grid-column:1/-1}}
.muted{color:var(--muted)}
.player{position:fixed;left:0;right:0;bottom:0;display:flex;gap:12px;align-items:center;
flex-wrap:wrap;padding:10px 16px;background:var(--card);border-top:1px solid var(--line);z-index:5}
.player audio{flex:1 1 320px;max-width:640px}.player .muted{font-size:13px}
body.com-audio main{padding-bottom:120px}
body.com-audio [data-t]{cursor:pointer}
body.com-audio tr[data-t]:hover,body.com-audio .tr:hover{background:var(--buy)}
.tr.agora{box-shadow:inset 3px 0 0 var(--warn);background:var(--buy)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
dl.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0}
.aviso{border-left:3px solid var(--warn);padding:6px 10px;margin:8px 0 0;font-size:14px}
"""

JS = """
const btns=document.querySelectorAll('.filters button');
btns.forEach(b=>b.addEventListener('click',()=>{
  b.setAttribute('aria-pressed',b.getAttribute('aria-pressed')==='true'?'false':'true');
  const on=new Set([...btns].filter(x=>x.getAttribute('aria-pressed')==='true').map(x=>x.dataset.p));
  document.querySelectorAll('.tr').forEach(r=>{r.style.display=on.has(r.dataset.p)?'':'none'});
}));
const only=document.getElementById('only-hits');
if(only)only.addEventListener('change',()=>document.body.classList.toggle('hits-only',only.checked));
"""


JS_AUDIO = """
const player=document.getElementById('player');
document.body.classList.add('com-audio');
function tocar(t){player.currentTime=Math.max(0,t-1.0);player.play().catch(()=>{});}
document.addEventListener('click',e=>{
  if(e.target.closest('button,input,label,a,audio'))return;
  const el=e.target.closest('[data-t]');
  if(el)tocar(parseFloat(el.dataset.t));
});
const linhas=[...document.querySelectorAll('.tr[data-t]')];
let atual=null;
player.addEventListener('timeupdate',()=>{
  const t=player.currentTime;let lo=0,hi=linhas.length-1,k=-1;
  while(lo<=hi){const m=(lo+hi)>>1;if(parseFloat(linhas[m].dataset.t)<=t){k=m;lo=m+1}else hi=m-1}
  const el=k>=0?linhas[k]:null;
  if(el!==atual){if(atual)atual.classList.remove('agora');if(el)el.classList.add('agora');atual=el;}
});
"""


def _e(s) -> str:
    return html.escape(str(s))


def _chip(player: str, colors: dict[str, str]) -> str:
    c = colors.get(player, "#64748b")
    return f'<span class="chip" style="background:{c}">{_e(player)}</span>'


def _wl(ganhamos) -> str:
    if ganhamos is True:
        return '<span class="tag W">Ganho</span>'
    if ganhamos is False:
        return '<span class="tag L">Perdido</span>'
    return '<span class="tag fase">?</span>'


def _timeline_svg(timeline, players, colors, overlaps, t0, t1, scale_s, jogo=None,
                  contexto=None) -> str:
    """Uma linha da linha do tempo, de t0 a t1. `scale_s` = duração que ocupa 100%."""
    lane_h, gap, ev_h = 12, 3, 12 if jogo else 0
    width = 1000 * (t1 - t0) / scale_s
    height = ev_h + len(players) * (lane_h + gap)
    sx = 1000 / scale_s
    pct = 100 * (t1 - t0) / scale_s
    parts = [f'<svg viewBox="0 0 {width:.1f} {height}" style="width:{pct:.2f}%" '
             f'role="img" aria-label="Fala de {fmt_clock(t0)} a {fmt_clock(t1)}">']

    def X(t):
        return (max(t, t0) - t0) * sx

    if jogo:
        for w in jogo["janelas"]:
            if w["barreira"] < t0 or w["buy"] > t1:
                continue
            x, x2 = X(w["buy"]), X(min(w["barreira"], t1))
            parts.append(f'<rect x="{x:.1f}" y="{ev_h}" width="{max(0, x2 - x):.1f}" '
                         f'height="{height - ev_h}" fill="var(--buy)"><title>Fase de compra'
                         f'</title></rect>')
            if t0 <= w["barreira"] <= t1:
                parts.append(f'<rect x="{X(w["barreira"]):.1f}" y="0" width="1.2" '
                             f'height="{height}" fill="var(--muted)"/>')
    for ev in overlaps:
        if ev["tipo"] == "backchannel" or ev["end"] < t0 or ev["start"] > t1:
            continue
        x = X(ev["start"])
        w = max(2, (min(ev["end"], t1) - max(ev["start"], t0)) * sx)
        fill = "var(--bad-bg)" if ev["tipo"] == "interrupcao" else "rgba(217,119,6,.14)"
        parts.append(f'<rect x="{x:.1f}" y="{ev_h}" width="{w:.1f}" height="{height - ev_h}" '
                     f'fill="{fill}"/>')
    if jogo:
        for k in jogo["kills"]:
            if not t0 <= k["t"] <= t1:
                continue
            x = X(k["t"])
            if k["nossa"]:  # nossa kill: triângulo para cima
                pts = f"{x - 4:.1f},{ev_h - 2} {x + 4:.1f},{ev_h - 2} {x:.1f},2"
                fill, label = "var(--good)", f'{k["killer"]} matou {k["vitima"]}'
            else:  # morte nossa: triângulo para baixo
                pts = f"{x - 4:.1f},2 {x + 4:.1f},2 {x:.1f},{ev_h - 2}"
                fill, label = "var(--bad)", f'{k["vitima"]} morreu ({k["killer"]})'
            parts.append(f'<polygon points="{pts}" fill="{fill}"><title>{_e(label)}</title>'
                         f'</polygon>')
        for w in jogo["janelas"]:
            for key, letra in (("plant", "P"), ("defuse", "D")):
                t = w.get(key)
                if t is not None and t0 <= t <= t1:
                    parts.append(f'<text x="{X(t):.1f}" y="{ev_h - 2}" font-size="10" '
                                 f'font-weight="700" text-anchor="middle" fill="var(--warn)">'
                                 f'{letra}<title>{"Plant" if letra == "P" else "Defuse"}</title>'
                                 f'</text>')
    for i, p in enumerate(players):
        y = ev_h + i * (lane_h + gap)
        parts.append(f'<rect x="0" y="{y + lane_h / 2 - .5}" width="{width:.1f}" height="1" '
                     f'fill="var(--line)"/>')
        for j, u in enumerate(timeline):
            if u.player != p or u.end < t0 or u.start > t1:
                continue
            x = X(u.start)
            w = max(1.5, (min(u.end, t1) - max(u.start, t0)) * sx)
            morto = contexto[j]["morto"] if contexto else False
            extra = ' opacity=".45" stroke="var(--bad)" stroke-width="1.2"' if morto else ""
            dica = " (morto)" if morto else ""
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lane_h}" rx="2" data-t="{u.start:.2f}" '
                f'fill="{colors[p]}"{extra}><title>{_e(p)}{dica} {fmt_clock(u.start)}: '
                f'{_e(u.text)}</title></rect>')
    parts.append("</svg>")
    return "".join(parts)


def _timeline_rows(dur: float, jogo: dict | None) -> list[tuple[float, float, str]]:
    """Linhas da linha do tempo: por round quando há partida; senão, blocos de 2 min."""
    if not jogo or not jogo.get("janelas"):
        rows, t = [], 0.0
        while t < dur:
            rows.append((t, min(t + PAGINA_S, dur), fmt_clock(t)))
            t += PAGINA_S
        return rows
    wins = jogo["janelas"]
    rows = []
    if wins[0]["buy"] > 1:
        rows.append((max(0.0, wins[0]["buy"] - PAGINA_S), wins[0]["buy"], "Antes"))
    for i, w in enumerate(wins):
        fim = wins[i + 1]["buy"] if i + 1 < len(wins) else min(dur, w["fim"] + 15)
        rows.append((w["buy"], max(fim, w["buy"] + 1), f'<b>R{w["n"]}</b><br>{fmt_clock(w["buy"])}'))
    return rows


_STATUS_CALL = {
    "seguiu a call": ("W", "Seguiu a call"),
    "mudou a call e seguiu": ("W", "Mudou a call e seguiu"),
    "plantou em outro site": ("L", "Plantou em outro site"),
    "sem plant": ("fase", "Sem plant"),
    "sem call": ("fase", "Sem call de site"),
}
_COMPRA_LABEL = {"forca": "forçar", "eco": "salvar", "full": "comprar tudo"}


def _analises_jogo(jogo: dict, colors: dict, riot_map: dict) -> str:
    h: list[str] = []
    riot_to_player = {v.lower(): k for k, v in riot_map.items() if v}

    cl = jogo.get("clutches") or []
    h.append(f'<h2>Clutches ({len(cl)})</h2>')
    if cl:
        h.append('<div class="card scroll"><p class="muted" style="margin:0 0 8px;font-size:13px">'
                 'Quando sobra um só vivo, o ideal é a call ficar quieta para ele ouvir o jogo.</p>'
                 '<table><thead><tr><th>Round</th><th>Quem</th><th>Situação</th>'
                 '<th class="n">Duração</th><th class="n">Outros falaram</th>'
                 '<th class="n">Por cima dele</th><th>Resultado</th></tr></thead><tbody>')
        for c in cl:
            quem = _chip(c["jogador"], colors) if c["jogador"] else _e(c["riot"] or "?")
            fala = ('<span class="tag W">silêncio</span>' if c["silencio_ok"] else
                    f'{c["fala_outros_s"]}s · {c["falas_outros"]} fala{"s" if c["falas_outros"] != 1 else ""}')
            h.append(f'<tr data-t="{c["t"]}"><td>R{c["round"]} · {fmt_clock(c["t"])}</td>'
                     f'<td>{quem}</td><td>1v{c["contra"]}</td><td class="n">{c["duracao_s"]}s</td>'
                     f'<td class="n">{fala}</td><td class="n">{c["por_cima_dele"]}</td>'
                     f'<td>{_wl(c["ganhamos"])}</td></tr>')
        h.append("</tbody></table></div>")
    else:
        h.append('<p class="muted">Nenhum round terminou com um só vivo do time.</p>')

    ce = jogo.get("call_execucao") or []
    if ce:
        h.append(f'<h2>Call x execução ({len(ce)} rounds de ataque)</h2>'
                 '<div class="card scroll"><p class="muted" style="margin:0 0 8px;font-size:13px">'
                 'Sites citados em ordens ("vamo B", "roda pro A") desde o fim do round anterior '
                 'até o plant, comparados com onde a spike foi plantada.</p><table><thead><tr>'
                 '<th>Round</th><th>Calls</th><th>Plant</th><th>Execução</th><th>Resultado</th>'
                 '</tr></thead><tbody>')
        for c in ce:
            seq = " → ".join(f'<b>{_e(x["site"])}</b>' for x in c["calls"][-6:]) or '<span class="muted">—</span>'
            if len(c["calls"]) > 6:
                seq = "… → " + seq
            t0 = c["calls"][-1]["t"] if c["calls"] else None
            cls, label = _STATUS_CALL[c["status"]]
            dt = f' data-t="{t0}"' if t0 is not None else ""
            h.append(f'<tr{dt}><td>R{c["round"]}</td><td>{seq}</td>'
                     f'<td>{_e(c["site_plant"] or "—")}</td><td><span class="tag {cls}">{label}'
                     f'</span></td><td>{_wl(c["ganhamos"])}</td></tr>')
        h.append("</tbody></table></div>")

    cp = jogo.get("compras") or []
    if cp:
        h.append(f'<h2>Compras ({len(cp)} rounds)</h2><div class="card scroll">'
                 '<p class="muted" style="margin:0 0 8px;font-size:13px">O que foi falado na compra '
                 'x quanto cada um levou para o round (full ≥ 3500, eco &lt; 1600). Rounds de pistol '
                 'ficam de fora.</p><table><thead><tr><th>Round</th><th>Combinado</th>'
                 '<th>Comprado</th><th></th><th>Resultado</th></tr></thead><tbody>')
        for c in cp:
            call = c["call"]
            comb = (f'{_COMPRA_LABEL[call["tipo"]]}<div class="muted" style="font-size:12px">'
                    f'{_e(call["jogador"])}: “{_e(call["texto"])}”</div>' if call
                    else '<span class="muted">nada falado</span>')
            n = c["contagem"]
            partes = [f'{n[k]} {k}' for k in ("full", "meio", "eco") if n[k]]
            jog = " ".join(
                f'<span title="{_e(r)}: {v.get("loadout")} ({_e(v.get("arma") or "")})">'
                f'{_chip(riot_to_player.get(r.lower(), r.split("#")[0]), colors)}</span>'
                for r, v in c["jogadores"].items() if v.get("classe") == "eco") if c["dividida"] else ""
            if c["dividida"]:
                flag = '<span class="tag L">Dividida</span>'
            elif c["seguiu"] is False:
                flag = '<span class="tag simultaneo">Diferente do combinado</span>'
            else:
                flag = ""
            dt = f' data-t="{call["t"]}"' if call else ""
            h.append(f'<tr{dt}><td>R{c["round"]}</td><td>{comb}</td><td>{", ".join(partes)}'
                     f'{"<div style=margin-top:4px>salvaram: " + jog + "</div>" if jog else ""}</td>'
                     f'<td>{flag}</td><td>{_wl(c["ganhamos"])}</td></tr>')
        h.append("</tbody></table></div>")
    return "".join(h)


def _sync_card(sinc: dict, partida: dict) -> str:
    h = ['<h2>Sincronização com a partida</h2><div class="card"><dl class="kv">']
    h.append(f'<dt>Método</dt><dd>{_e(_METODO_LABEL.get(sinc["metodo"], sinc["metodo"]))}</dd>')
    a = sinc.get("ancora")
    if a:
        quem = f' · {_e(a["jogador"])}' if a.get("jogador") else ""
        h.append(f'<dt>Âncora</dt><dd>{fmt_clock(a["t"])} da gravação{quem}</dd>')
    if sinc.get("regra"):
        h.append(f'<dt>Regra</dt><dd>só a ocorrência {_e(sinc["regra"])}</dd>')
    if sinc.get("offset_s") is not None:
        h.append(f'<dt>Deslocamento</dt><dd>{sinc["offset_s"]:+.2f}s</dd>')
    aj = sinc.get("ajuste")
    if aj:
        txt = (f'aplicado ({aj["delta_s"]:+.2f}s)' if aj["aplicado"] else "não aplicado")
        h.append(f'<dt>Ajuste pelas mortes</dt><dd>{txt} · fala logo após morrer em '
                 f'{int(100 * aj["acerto_depois"])}% de {aj["mortes_avaliadas"]} mortes</dd>')
    h.append(f'<dt>Zero do round (API)</dt><dd>'
             f'{"início da compra" if partida.get("t0_round") == "buy" else "barreira"}</dd>')
    h.append("</dl>")
    ign = sinc.get("ignoradas") or []
    if ign:
        h.append(f'<p class="muted" style="margin:10px 0 0;font-size:13px">{len(ign)} '
                 f'ocorrência(s) da palavra ignoradas: '
                 + ", ".join(f'{fmt_clock(c["t"])} ({_e(c["motivo"])})' for c in ign[:8])
                 + ("…" if len(ign) > 8 else "") + "</p>")
    for av in sinc.get("avisos") or []:
        h.append(f'<div class="aviso">{_e(av)}</div>')
    h.append("</div>")
    return "".join(h)


def render_report(timeline: list[Utterance], metrics: dict, meta: dict, path: Path,
                  partida: dict | None = None, sinc: dict | None = None,
                  jogo: dict | None = None, audio: str | None = None, **_extra) -> None:
    players = list(metrics["jogadores"].keys())
    colors = {p: CORES[i % len(CORES)] for i, p in enumerate(players)}
    r = metrics["resumo"]
    overlaps = metrics["sobreposicoes"]
    contexto = jogo["contexto_falas"] if jogo else None

    hits = set()
    for ev in overlaps:
        if ev["tipo"] != "interrupcao":
            continue
        for u in timeline:
            if u.player == ev["segundo"] and u.start <= ev["start"] + 0.05 and u.end >= ev["start"]:
                hits.add(id(u))

    h: list[str] = []
    h.append(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Call {_e(meta.get("nome", ""))}</title><style>{CSS}'
             f'body.hits-only .tr:not(.hit){{display:none!important}}</style></head><body><main>')
    h.append(f'<h1>Análise da call — {_e(meta.get("nome", "partida"))}</h1>')
    sub = [f'{fmt_clock(r["duracao_s"])} de gravação', f'{len(players)} jogadores']
    if partida:
        if partida.get("mapa"):
            sub.insert(0, _e(partida["mapa"]))
        if partida.get("placar") and None not in partida["placar"]:
            sub.insert(1, f'{partida["placar"][0]}–{partida["placar"][1]}')
        if partida.get("modo"):
            sub.append(_e(partida["modo"]))
    sub.append(f'modelo {_e(meta.get("modelo", "?"))}')
    h.append(f'<p class="sub">{" · ".join(sub)}</p>')

    kpis = [
        (r["interrupcoes"], "interrupções"),
        (f'{r["sobreposicao_pct_da_fala"]}%', "da fala sobreposta"),
        (r["callouts_longos"], "falas longas"),
        (r["conflitos_de_site"], "ordens de site conflitantes"),
    ]
    if jogo:
        fm = jogo["fala_de_morto"]["por_jogador"]
        kpis.append((f'{sum(d["segundos"] for d in fm.values()):.0f}s', "de fala de morto"))
        kpis.append((sum(d["por_cima_de_vivo"] for d in fm.values()), "mortos por cima de vivos"))
    else:
        kpis.append((f'{r["silencio_pct"]}%', "da partida em silêncio"))
    h.append('<div class="kpis">' + "".join(
        f'<div class="card kpi"><div class="v">{_e(v)}</div><div class="l">{_e(l)}</div></div>'
        for v, l in kpis) + "</div>")

    destaques = list(metrics["destaques"]) + (jogo["destaques"] if jogo else [])
    h.append('<h2>Destaques</h2><div class="card"><ul class="dest">'
             + "".join(f"<li>{_e(s)}</li>" for s in destaques) + "</ul></div>")

    # Por jogador
    max_pct = max((d["participacao_pct"] for d in metrics["jogadores"].values()), default=1) or 1
    morto_pj = jogo["fala_de_morto"]["por_jogador"] if jogo else {}
    riot_map = meta.get("riot_map") or {}
    col_morto = '<th class="n">Fala de morto</th>' if jogo else ""
    h.append('<h2>Por jogador</h2><div class="card scroll"><table><thead><tr>'
             '<th>Jogador</th><th>Participação</th><th class="n">Tempo</th><th class="n">Falas</th>'
             '<th class="n">Interrompeu</th><th class="n">Foi cortado</th>'
             f'<th class="n">Falou junto</th><th class="n">Falas longas</th>{col_morto}'
             '</tr></thead><tbody>')
    for p, d in metrics["jogadores"].items():
        w = 100 * d["participacao_pct"] / max_pct
        riot = (f'<div class="muted" style="font-size:12px">{_e(riot_map[p])}</div>'
                if p in riot_map else "")
        cel_morto = ""
        if jogo:
            m = morto_pj.get(p)
            cel_morto = (f'<td class="n">{m["segundos"]}s · {m["por_cima_de_vivo"]}×</td>' if m
                         else '<td class="n">—</td>')
        h.append(
            f'<tr><td>{_chip(p, colors)}{riot}</td><td><div style="display:flex;gap:8px;'
            f'align-items:center"><div class="bar" style="flex:1"><span style="width:{w:.0f}%;'
            f'background:{colors[p]}"></span></div><span>{d["participacao_pct"]}%</span></div></td>'
            f'<td class="n">{fmt_clock(d["tempo_fala_s"])}</td><td class="n">{d["falas"]}</td>'
            f'<td class="n">{d["interrompeu"]}</td><td class="n">{d["foi_interrompido"]}</td>'
            f'<td class="n">{d["falou_junto"]}</td><td class="n">{d["callouts_longos"]}</td>'
            f'{cel_morto}</tr>')
    h.append("</tbody></table>")
    if jogo:
        h.append('<p class="muted" style="margin:8px 0 0;font-size:13px">Fala de morto = segundos '
                 'falando depois de morrer com alguém do time ainda vivo · quantas vezes foi por '
                 'cima da fala de um vivo.</p>')
    h.append("</div>")

    # Rounds
    if jogo:
        cmp_ = jogo["ganhos_x_perdidos"]
        fases = jogo["fala_por_fase_pct"]
        h.append('<h2>Rounds</h2><div class="grid2">')
        h.append('<div class="card"><table><thead><tr><th></th><th class="n">Ganhos</th>'
                 '<th class="n">Perdidos</th></tr></thead><tbody>')
        for k, label in (("interrupcoes", "Interrupções no round"), ("fala_ativo_s", "Fala no round (s)"),
                         ("fala_morto_s", "Fala de morto (s)"), ("fala_buy_s", "Fala na compra (s)")):
            g, pz = cmp_[k]["ganhos"], cmp_[k]["perdidos"]
            h.append(f'<tr><td>{label}</td><td class="n">{"—" if g is None else g}</td>'
                     f'<td class="n">{"—" if pz is None else pz}</td></tr>')
        h.append('</tbody></table><p class="muted" style="margin:8px 0 0;font-size:13px">'
                 'Média por round.</p></div>')
        h.append('<div class="card"><table><thead><tr><th>Quando a call falou</th>'
                 '<th class="n">% da fala</th></tr></thead><tbody>')
        for f in ("buy", "ativo", "pos_round", "pre_jogo", "pos_jogo"):
            h.append(f'<tr><td>{FASE_LABEL[f].capitalize()}</td><td class="n">{fases.get(f, 0)}%</td></tr>')
        h.append("</tbody></table></div></div>")

        h.append('<div class="card scroll" style="margin-top:12px"><table><thead><tr>'
                 '<th>Round</th><th>Resultado</th><th>Site</th><th class="n">Kills</th>'
                 '<th class="n">Mortes</th><th class="n">Fala no round</th>'
                 '<th class="n">Interrupções</th><th class="n">Fala de morto</th></tr></thead><tbody>')
        for rr in jogo["rounds"]:
            est = ' <span class="muted" title="Início estimado (round sem kills)">~</span>' if rr["estimado"] else ""
            h.append(f'<tr><td>R{rr["n"]}{est}</td><td>{_wl(rr["ganhamos"])}</td>'
                     f'<td>{_e(rr["site"] or "—")}</td><td class="n">{rr["kills"]}</td>'
                     f'<td class="n">{rr["mortes"]}</td><td class="n">{rr["fala_ativo_s"]}s</td>'
                     f'<td class="n">{rr["interrupcoes"]}</td><td class="n">{rr["fala_morto_s"]}s</td></tr>')
        h.append("</tbody></table></div>")

    if jogo:
        h.append(_analises_jogo(jogo, colors, meta.get("riot_map") or {}))

    if sinc:
        h.append(_sync_card(sinc, partida or {}))

    # Linha do tempo
    h.append('<h2>Linha do tempo</h2><div class="card"><div class="legend">'
             + "".join(_chip(p, colors) for p in players)
             + '<span class="tag interrupcao">Interrupção</span>'
               '<span class="tag simultaneo">Falaram juntos</span>')
    if jogo:
        h.append('<span class="tag W">▲ kill nossa</span><span class="tag L">▼ morte nossa</span>'
                 '<span class="tag fase">cinza = compra</span>')
    h.append("</div>")
    rows = _timeline_rows(max(r["duracao_s"], 1.0), jogo)
    scale = max(max((b - a) for a, b, _ in rows), 1.0)
    for a, b, label in rows:
        h.append(f'<div class="tl-row"><div class="tl-t">{label}</div><div class="tl-box">'
                 f'{_timeline_svg(timeline, players, colors, overlaps, a, b, scale, jogo, contexto)}'
                 f'</div></div>')
    nota = ("Uma linha por round (da compra até o próximo round); mesma escala em todas. "
            "Falas apagadas com contorno vermelho = jogador já morto." if jogo else
            "Cada linha = 2 minutos; uma faixa por jogador, na ordem da legenda.")
    h.append(f'<p class="muted" style="margin:8px 0 0;font-size:13px">{nota} '
             'Passe o mouse para ver a fala.</p></div>')

    # Fala de morto
    if jogo and jogo["fala_de_morto"]["eventos"]:
        evs = jogo["fala_de_morto"]["eventos"]
        h.append(f'<h2>Fala de morto ({len(evs)})</h2><div class="card scroll"><table><thead><tr>'
                 '<th>Quando</th><th>Jogador</th><th>Fala</th><th>Por cima de</th></tr></thead><tbody>')
        for ev in evs:
            sobre = " ".join(_chip(p, colors) for p in ev["por_cima_de"]) or '<span class="muted">—</span>'
            h.append(f'<tr data-t="{ev["t"]}"><td>R{ev["round"]} · {fmt_clock(ev["t"])}</td><td>{_chip(ev["jogador"], colors)}'
                     f'</td><td>{_e(ev["texto"])}</td><td>{sobre}</td></tr>')
        h.append("</tbody></table></div>")

    # Sobreposições
    sig = [e for e in overlaps if e["tipo"] != "backchannel"]
    h.append(f'<h2>Sobreposições ({len(sig)})</h2>')
    if sig:
        h.append('<div class="card scroll"><table><thead><tr><th>Quando</th><th>Tipo</th>'
                 '<th>Quem falava</th><th>Quem entrou</th></tr></thead><tbody>')
        for e in sig:
            h.append(
                f'<tr data-t="{e["start"]}"><td>{fmt_clock(e["start"])}<div class="muted" style="font-size:12px">'
                f'{e["duration"]}s</div></td><td><span class="tag {e["tipo"]}">'
                f'{_TIPO_LABEL[e["tipo"]]}</span></td>'
                f'<td>{_chip(e["primeiro"], colors)}<div>{_e(e["texto_primeiro"])}</div></td>'
                f'<td>{_chip(e["segundo"], colors)}<div>{_e(e["texto_segundo"])}</div></td></tr>')
        h.append("</tbody></table></div>")
    else:
        h.append('<p class="muted">Nenhuma.</p>')

    ordens = metrics["ordens_proximas"]
    if ordens:
        h.append(f'<h2>Ordens próximas ({len(ordens)})</h2><div class="card scroll"><table><thead>'
                 '<tr><th>Quando</th><th>Ordens</th></tr></thead><tbody>')
        for o in ordens:
            flag = ' <span class="tag interrupcao">sites diferentes</span>' if o["conflito_site"] else ""
            linhas = "".join(f'<div>{_chip(j, colors)} {_e(tx)}</div>'
                             for j, tx in zip(o["jogadores"], o["textos"]))
            h.append(f'<tr data-t="{o["start"]}"><td>{fmt_clock(o["start"])}{flag}</td><td>{linhas}</td></tr>')
        h.append("</tbody></table></div>")

    longos = metrics["callouts_longos"]
    if longos:
        h.append(f'<h2>Falas longas ({len(longos)})</h2><div class="card scroll"><table><thead>'
                 '<tr><th>Quando</th><th>Jogador</th><th class="n">Duração</th><th>Fala</th>'
                 '</tr></thead><tbody>')
        for c in longos:
            h.append(f'<tr data-t="{c["start"]}"><td>{fmt_clock(c["start"])}</td><td>{_chip(c["jogador"], colors)}</td>'
                     f'<td class="n">{c["duracao"]}s</td><td>{_e(c["texto"])}</td></tr>')
        h.append("</tbody></table></div>")

    # Transcrição
    h.append('<h2>Transcrição</h2><div class="card"><div class="filters">'
             + "".join(f'<button type="button" aria-pressed="true" data-p="{_e(p)}" '
                       f'style="border-color:{colors[p]}">{_e(p)}</button>' for p in players)
             + '<label style="margin-left:auto;font-size:13px"><input type="checkbox" id="only-hits"> '
               'só interrupções</label></div>')
    ancora_t = (sinc or {}).get("ancora", {}) or {}
    ancora_t = ancora_t.get("t") if ancora_t.get("jogador") else None
    last_round = object()
    for j, u in enumerate(timeline):
        ctx = contexto[j] if contexto else None
        if ctx and ctx["round"] != last_round and ctx["round"] is not None:
            last_round = ctx["round"]
            h.append(f'<div class="rsep">Round {ctx["round"]}</div>')
        cls = "tr hit" if id(u) in hits else "tr"
        tags = ""
        if ancora_t is not None and u.start - 0.01 <= ancora_t <= u.end + 0.01 \
                and u.player == sinc["ancora"]["jogador"]:
            tags += '<span class="tag W">sinc</span>'
        if ctx:
            if ctx["morto"]:
                tags += '<span class="tag morto">morto</span>'
            elif ctx["fase"] in ("buy", "pos_round"):
                tags += f'<span class="tag fase">{FASE_LABEL[ctx["fase"]]}</span>'
        h.append(f'<div class="{cls}" data-p="{_e(u.player)}" data-t="{u.start:.2f}"><div class="t">{fmt_clock(u.start)}'
                 f'</div><div class="p">{_chip(u.player, colors)}</div><div class="x">{_e(u.text)}'
                 f'{tags}</div></div>')
    h.append("</div>")
    h.append('<p class="muted" style="margin-top:24px;font-size:12px">Gerado por espumas-transcript. '
             'Métricas automáticas: use como ponto de partida para a revisão, não como veredito.</p>')
    if audio:
        tipo = "audio/webm" if audio.endswith(".webm") else "audio/mp4"
        h.append('<div class="player" role="region" aria-label="Áudio da call">'
                 f'<audio id="player" controls preload="metadata"><source src="{_e(audio)}" '
                 f'type="{tipo}"></audio><span class="muted" id="player-dica">Clique em qualquer '
                 'horário, fala ou barra da linha do tempo para ouvir aquele momento.</span></div>')
        h.append(f"</main><script>{JS}{JS_AUDIO}</script></body></html>")
    else:
        h.append(f"</main><script>{JS}</script></body></html>")
    path.write_text("".join(h), encoding="utf-8")
