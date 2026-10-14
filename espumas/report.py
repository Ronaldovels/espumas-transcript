"""Relatório HTML autocontido (abre direto no navegador, sem internet)."""

from __future__ import annotations

import html
from pathlib import Path

from .export import fmt_clock
from .models import Utterance

CORES = ["#3b82f6", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6",
         "#06b6d4", "#ef4444", "#84cc16", "#f97316", "#64748b"]

PAGINA_S = 120  # cada linha da linha do tempo cobre 2 minutos

_TIPO_LABEL = {
    "interrupcao": "Interrupção",
    "simultaneo": "Falaram juntos",
    "backchannel": "Resposta curta",
}

CSS = """
:root{--bg:#f7f7f8;--card:#fff;--fg:#17181c;--muted:#6b7080;--line:#e3e4e8;--bad:#dc2626;
--bad-bg:rgba(220,38,38,.12);--warn:#d97706;--chip-fg:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#111215;--card:#1a1b20;--fg:#ececf1;
--muted:#9a9eab;--line:#2b2d35;--bad:#f87171;--bad-bg:rgba(248,113,113,.16);--warn:#fbbf24}}
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
.tl-row{display:flex;gap:8px;align-items:stretch;padding:6px 0;border-bottom:1px dashed var(--line)}.tl-row:last-of-type{border-bottom:0}
.tl-t{width:44px;flex:none;color:var(--muted);font-size:12px;padding-top:2px;font-variant-numeric:tabular-nums}
.tl-row svg{flex:1;min-width:0;height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.tag{font-size:12px;font-weight:600;padding:1px 6px;border-radius:4px}
.tag.interrupcao{background:var(--bad-bg);color:var(--bad)}
.tag.simultaneo{background:rgba(217,119,6,.14);color:var(--warn)}
.tag.backchannel{background:var(--line);color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.filters button{border:1px solid var(--line);background:var(--card);color:var(--fg);
border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer}
.filters button[aria-pressed=false]{opacity:.45}
.tr{display:grid;grid-template-columns:52px 120px 1fr;gap:8px;padding:6px 4px;
border-bottom:1px solid var(--line)}
.tr .t{color:var(--muted);font-variant-numeric:tabular-nums;font-size:13px;padding-top:1px}
.tr.hit{background:var(--bad-bg)}
@media (max-width:600px){.tr{grid-template-columns:44px 1fr}.tr .p{grid-column:2}
.tr .x{grid-column:1/-1}}
.muted{color:var(--muted)}
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


def _e(s) -> str:
    return html.escape(str(s))


def _chip(player: str, colors: dict[str, str]) -> str:
    return f'<span class="chip" style="background:{colors[player]}">{_e(player)}</span>'


def _timeline_svg(timeline: list[Utterance], players: list[str], colors: dict[str, str],
                  overlaps: list[dict], t0: float, t1: float) -> str:
    lane_h, gap = 12, 3
    width = 1000
    height = len(players) * (lane_h + gap)
    sx = width / (t1 - t0)
    parts = [f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
             f'role="img" aria-label="Fala de {fmt_clock(t0)} a {fmt_clock(t1)}">']
    for ev in overlaps:
        if ev["tipo"] == "backchannel" or ev["end"] < t0 or ev["start"] > t1:
            continue
        x = (max(ev["start"], t0) - t0) * sx
        w = max(2, (min(ev["end"], t1) - max(ev["start"], t0)) * sx)
        fill = "var(--bad-bg)" if ev["tipo"] == "interrupcao" else "rgba(217,119,6,.14)"
        parts.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" fill="{fill}"/>')
    for i, p in enumerate(players):
        y = i * (lane_h + gap)
        parts.append(f'<rect x="0" y="{y + lane_h / 2 - .5}" width="{width}" height="1" '
                     f'fill="var(--line)"/>')
        for u in timeline:
            if u.player != p or u.end < t0 or u.start > t1:
                continue
            x = (max(u.start, t0) - t0) * sx
            w = max(1.5, (min(u.end, t1) - max(u.start, t0)) * sx)
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{lane_h}" rx="2" '
                f'fill="{colors[p]}"><title>{_e(p)} {fmt_clock(u.start)}: {_e(u.text)}</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def render_report(timeline: list[Utterance], metrics: dict, meta: dict, path: Path) -> None:
    players = list(metrics["jogadores"].keys())
    colors = {p: CORES[i % len(CORES)] for i, p in enumerate(players)}
    r = metrics["resumo"]
    overlaps = metrics["sobreposicoes"]

    # Falas envolvidas em interrupção (para destacar na transcrição).
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
    h.append(f'<p class="sub">{fmt_clock(r["duracao_s"])} de gravação · {len(players)} jogadores · '
             f'modelo {_e(meta.get("modelo", "?"))}</p>')

    kpis = [
        (r["interrupcoes"], "interrupções"),
        (f'{r["sobreposicao_pct_da_fala"]}%', "da fala sobreposta"),
        (r["callouts_longos"], "falas longas"),
        (r["conflitos_de_site"], "ordens de site conflitantes"),
        (f'{r["silencio_pct"]}%', "da partida em silêncio"),
    ]
    h.append('<div class="kpis">' + "".join(
        f'<div class="card kpi"><div class="v">{_e(v)}</div><div class="l">{_e(l)}</div></div>'
        for v, l in kpis) + "</div>")

    h.append('<h2>Destaques</h2><div class="card"><ul class="dest">'
             + "".join(f"<li>{_e(s)}</li>" for s in metrics["destaques"]) + "</ul></div>")

    # Tabela por jogador
    max_pct = max((d["participacao_pct"] for d in metrics["jogadores"].values()), default=1) or 1
    h.append('<h2>Por jogador</h2><div class="card scroll"><table><thead><tr>'
             '<th>Jogador</th><th>Participação</th><th class="n">Tempo</th><th class="n">Falas</th>'
             '<th class="n">Interrompeu</th><th class="n">Foi cortado</th>'
             '<th class="n">Falou junto</th><th class="n">Falas longas</th></tr></thead><tbody>')
    for p, d in metrics["jogadores"].items():
        w = 100 * d["participacao_pct"] / max_pct
        h.append(
            f'<tr><td>{_chip(p, colors)}</td><td><div style="display:flex;gap:8px;align-items:center">'
            f'<div class="bar" style="flex:1"><span style="width:{w:.0f}%;background:{colors[p]}">'
            f'</span></div><span>{d["participacao_pct"]}%</span></div></td>'
            f'<td class="n">{fmt_clock(d["tempo_fala_s"])}</td><td class="n">{d["falas"]}</td>'
            f'<td class="n">{d["interrompeu"]}</td><td class="n">{d["foi_interrompido"]}</td>'
            f'<td class="n">{d["falou_junto"]}</td><td class="n">{d["callouts_longos"]}</td></tr>')
    h.append("</tbody></table></div>")

    # Linha do tempo
    h.append('<h2>Linha do tempo</h2><div class="card"><div class="legend">'
             + "".join(_chip(p, colors) for p in players)
             + '<span class="tag interrupcao">Interrupção</span>'
               '<span class="tag simultaneo">Falaram juntos</span></div>')
    dur = max(r["duracao_s"], 1.0)
    t = 0.0
    while t < dur:
        h.append(f'<div class="tl-row"><div class="tl-t">{fmt_clock(t)}</div>'
                 f'{_timeline_svg(timeline, players, colors, overlaps, t, t + PAGINA_S)}</div>')
        t += PAGINA_S
    h.append('<p class="muted" style="margin:8px 0 0;font-size:13px">Cada linha = 2 minutos; '
             'uma faixa por jogador, na ordem da legenda. Passe o mouse para ver a fala.</p></div>')

    # Interrupções
    sig = [e for e in overlaps if e["tipo"] != "backchannel"]
    h.append(f'<h2>Sobreposições ({len(sig)})</h2>')
    if sig:
        h.append('<div class="card scroll"><table><thead><tr><th>Quando</th><th>Tipo</th>'
                 '<th>Quem falava</th><th>Quem entrou</th></tr></thead><tbody>')
        for e in sig:
            h.append(
                f'<tr><td>{fmt_clock(e["start"])}<div class="muted" style="font-size:12px">'
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
            h.append(f'<tr><td>{fmt_clock(o["start"])}{flag}</td><td>{linhas}</td></tr>')
        h.append("</tbody></table></div>")

    longos = metrics["callouts_longos"]
    if longos:
        h.append(f'<h2>Falas longas ({len(longos)})</h2><div class="card scroll"><table><thead>'
                 '<tr><th>Quando</th><th>Jogador</th><th class="n">Duração</th><th>Fala</th>'
                 '</tr></thead><tbody>')
        for c in longos:
            h.append(f'<tr><td>{fmt_clock(c["start"])}</td><td>{_chip(c["jogador"], colors)}</td>'
                     f'<td class="n">{c["duracao"]}s</td><td>{_e(c["texto"])}</td></tr>')
        h.append("</tbody></table></div>")

    # Transcrição
    h.append('<h2>Transcrição</h2><div class="card"><div class="filters">'
             + "".join(f'<button type="button" aria-pressed="true" data-p="{_e(p)}" '
                       f'style="border-color:{colors[p]}">{_e(p)}</button>' for p in players)
             + '<label style="margin-left:auto;font-size:13px"><input type="checkbox" id="only-hits"> '
               'só interrupções</label></div>')
    for u in timeline:
        cls = "tr hit" if id(u) in hits else "tr"
        h.append(f'<div class="{cls}" data-p="{_e(u.player)}"><div class="t">{fmt_clock(u.start)}'
                 f'</div><div class="p">{_chip(u.player, colors)}</div><div class="x">{_e(u.text)}'
                 f'</div></div>')
    h.append("</div>")
    h.append(f'<p class="muted" style="margin-top:24px;font-size:12px">Gerado por espumas-transcript. '
             f'Métricas automáticas: use como ponto de partida para a revisão, não como veredito.</p>')
    h.append(f"</main><script>{JS}</script></body></html>")
    path.write_text("".join(h), encoding="utf-8")
