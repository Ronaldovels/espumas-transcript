"use strict";
/* Aba "Evolução": gráficos de linha simples em SVG, sem bibliotecas. */

const CORES_JOG = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => `var(--p${i})`);
const TEND = { melhorou: "melhorou", piorou: "piorou", estavel: "estável", igual: "igual" };
let evo = null;

function fmt(v, unidade) {
  if (v == null) return "—";
  const n = Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(v % 1 === 0 ? 0 : 1);
  return n.replace(".", ",") + (unidade === "%" ? "%" : unidade === "s" ? " s" : "");
}

function rotuloPartida(p) {
  const d = p.data ? new Date(p.data).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : "";
  const placar = p.placar ? ` ${p.placar[0]}–${p.placar[1]}` : "";
  return { curto: d, longo: `${p.mapa || p.nome}${placar}${d ? ", " + d : ""}` };
}

function escalaY(max) {
  if (max <= 0) return { max: 1, ticks: [0, 0.5, 1] };
  const passo = Math.pow(10, Math.floor(Math.log10(max)));
  const fatores = [1, 2, 2.5, 5, 10];
  let top = passo;
  for (const f of fatores) { top = f * passo; if (top >= max) break; }
  return { max: top, ticks: [0, top / 2, top] };
}

/** Desenha um gráfico de linhas. series: [{nome, cor, valores}] */
function graficoLinhas(alvo, opcoes) {
  alvo._grafico = opcoes;  // para redesenhar quando a janela muda de tamanho
  const { series, partidas, unidade, altura = 180, rotularFim = false } = opcoes;
  // Largura real em pixels: texto e marcas ficam do mesmo tamanho em qualquer tela.
  const W = Math.max(260, alvo.clientWidth || 600), H = altura;
  const m = { t: 12, r: rotularFim ? 80 : 16, b: 26, l: 44 };
  const n = partidas.length;
  const vals = series.flatMap((s) => s.valores).filter((v) => v != null);
  const { max, ticks } = escalaY(Math.max(...vals, 0));
  const x = (i) => m.l + (n === 1 ? (W - m.l - m.r) / 2 : (i * (W - m.l - m.r)) / (n - 1));
  const y = (v) => m.t + (H - m.t - m.b) * (1 - v / max);
  const rot = partidas.map(rotuloPartida);

  let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Gráfico por partida">`;
  svg += '<g class="eixo">';
  ticks.forEach((t) => {
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/>` +
      `<text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${fmt(t, unidade)}</text>`;
  });
  const passoX = Math.max(1, Math.ceil(n / 6));
  rot.forEach((r, i) => {
    if (i % passoX === 0 || i === n - 1) {
      svg += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(r.curto)}</text>`;
    }
  });
  svg += "</g>";
  const finais = [];
  series.forEach((s) => {
    let d = "", aberto = false;
    s.valores.forEach((v, i) => {
      if (v == null) { aberto = false; return; }
      d += `${aberto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      aberto = true;
    });
    svg += `<path class="serie" d="${d}" style="stroke:${s.cor}"/>`;
    s.valores.forEach((v, i) => {
      if (v != null) svg += `<circle class="ponto" cx="${x(i)}" cy="${y(v)}" r="4.5" style="fill:${s.cor}"/>`;
    });
    if (rotularFim) {
      const ult = s.valores.map((v, i) => [v, i]).filter(([v]) => v != null).pop();
      if (ult) finais.push({ nome: s.nome, x: x(ult[1]) + 9, y: y(ult[0]) + 4 });
    }
  });
  // Rótulos no fim das linhas sem encavalar: empurra para baixo os que ficam colados.
  finais.sort((a, b) => a.y - b.y);
  finais.forEach((f, i) => { if (i && f.y - finais[i - 1].y < 15) f.y = finais[i - 1].y + 15; });
  finais.forEach((f) => { svg += `<text class="rotulo-serie" x="${f.x}" y="${f.y}">${esc(f.nome)}</text>`; });
  svg += `<line class="mira" y1="${m.t}" y2="${H - m.b}" x1="0" x2="0" visibility="hidden"/>`;
  svg += `<rect x="${m.l - 10}" y="0" width="${W - m.l - m.r + 20}" height="${H}" fill="transparent" class="alvo"/>`;
  svg += "</svg>";

  let html = "";
  if (series.length >= 2) {
    html += '<div class="legenda">' + series.map((s) => `<span style="--c:${s.cor}">${esc(s.nome)}</span>`).join("") + "</div>";
  }
  alvo.innerHTML = html + svg;

  // Mira + dica ao passar o mouse (ou tocar)
  const el = alvo.querySelector("svg");
  const mira = el.querySelector(".mira");
  const dica = $("#dica");
  const mover = (ev) => {
    const r = el.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    let i = n === 1 ? 0 : Math.round(((px - m.l) / (W - m.l - m.r)) * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    mira.setAttribute("x1", x(i)); mira.setAttribute("x2", x(i)); mira.setAttribute("visibility", "visible");
    const linhas = series.filter((s) => s.valores[i] != null)
      .map((s) => `<div class="linha-dica" style="--c:${s.cor}">${series.length > 1 ? esc(s.nome) + ": " : ""}${fmt(s.valores[i], unidade)}</div>`)
      .join("") || "<div>sem dado</div>";
    dica.innerHTML = `<b>${esc(rot[i].longo)}</b>${linhas}`;
    dica.hidden = false;
    const dx = ev.clientX + 14 + 260 > innerWidth ? -274 : 14;
    dica.style.left = ev.clientX + dx + "px";
    dica.style.top = ev.clientY + 12 + "px";
  };
  el.addEventListener("pointermove", mover);
  el.addEventListener("pointerdown", mover);
  el.addEventListener("pointerleave", () => { dica.hidden = true; mira.setAttribute("visibility", "hidden"); });
}

function textoTendencia(t, unidade) {
  if (!t) return "Precisa de 4 partidas para comparar.";
  return `Últimas 3: <b>${fmt(t.recentes, unidade)}</b> (antes ${fmt(t.antes, unidade)})` +
    ` <span class="selo-t ${t.direcao}">${TEND[t.direcao]}</span>`;
}

function renderTime() {
  const box = $("#evo-time");
  box.innerHTML = "";
  evo.time.forEach((mt) => {
    if (mt.serie.every((v) => v == null)) return;
    const card = document.createElement("div");
    card.className = "grafico";
    card.innerHTML = `<h4>${esc(mt.rotulo)}</h4><p class="tend">${textoTendencia(mt.tendencia, mt.unidade)}</p><div></div>`;
    box.appendChild(card);
    graficoLinhas(card.lastElementChild, {
      series: [{ nome: "Time", cor: "var(--teal)", valores: mt.serie }],
      partidas: evo.partidas, unidade: mt.unidade, altura: 170,
    });
  });
}

function renderJogadores() {
  const chave = $("#evo-metrica").value;
  const def = evo.metricas_jogador.find((m) => m.chave === chave);
  const series = evo.jogadores.map((j, i) => ({
    nome: j.nome, cor: CORES_JOG[i % CORES_JOG.length], valores: j.metricas[chave].serie,
  })).filter((s) => s.valores.some((v) => v != null));
  graficoLinhas($("#evo-jog-grafico"), {
    series, partidas: evo.partidas, unidade: def.unidade, altura: 240, rotularFim: series.length <= 5,
  });

  // Tabela: mesma informação em números (também serve de alternativa ao gráfico)
  const cab = evo.metricas_jogador.map((m) => `<th class="n">${esc(m.rotulo)}</th>`).join("");
  const linhas = evo.jogadores.map((j, i) => {
    const cels = evo.metricas_jogador.map((m) => {
      const x = j.metricas[m.chave];
      const t = x.tendencia ? ` <span class="selo-t ${x.tendencia.direcao}">${TEND[x.tendencia.direcao]}</span>` : "";
      return `<td class="n">${fmt(x.media, m.unidade)}${t}</td>`;
    }).join("");
    return `<tr><td class="cor" style="--c:${CORES_JOG[i % CORES_JOG.length]}">${esc(j.nome)}</td>` +
      `<td class="n">${j.partidas}</td>${cels}</tr>`;
  }).join("");
  $("#evo-jog-tabela").innerHTML = `<thead><tr><th>Jogador</th><th class="n">Partidas</th>${cab}</tr></thead>` +
    `<tbody>${linhas}</tbody><caption class="sr">Média por jogador; selo compara as 3 últimas partidas com as anteriores.</caption>`;
}

function renderMapas() {
  const defs = evo.time;
  if (!evo.mapas.length) { $("#evo-mapas").innerHTML = '<tbody><tr><td>Sem partidas com mapa.</td></tr></tbody>'; return; }
  const cab = defs.map((d) => `<th class="n">${esc(d.rotulo)}</th>`).join("");
  const linhas = evo.mapas.map((m) =>
    `<tr><td>${esc(m.mapa)}</td><td class="n">${m.partidas}</td><td class="n">${m.vitorias}</td>` +
    defs.map((d) => `<td class="n">${fmt(m.medias[d.chave], d.unidade)}</td>`).join("") + "</tr>").join("");
  $("#evo-mapas").innerHTML = `<thead><tr><th>Mapa</th><th class="n">Partidas</th><th class="n">Vitórias</th>${cab}</tr></thead><tbody>${linhas}</tbody>`;
}

async function carregarEvolucao() {
  evo = await api("/api/evolucao");
  const n = evo.partidas.length;
  const vit = evo.partidas.filter((p) => p.venceu).length;
  const comJogo = evo.partidas.filter((p) => p.rounds).length;
  $("#evo-resumo").textContent = n
    ? `${n} partida${n > 1 ? "s" : ""} analisada${n > 1 ? "s" : ""}, ${vit} vitória${vit === 1 ? "" : "s"}.`
    : "";
  const vazio = comJogo < 2;
  $("#evo-vazio").hidden = !vazio;
  $("#evo-conteudo").hidden = vazio;
  if (vazio) return;
  const sel = $("#evo-metrica");
  if (!sel.options.length) {
    sel.innerHTML = evo.metricas_jogador.map((m) => `<option value="${m.chave}">${esc(m.rotulo)}</option>`).join("");
    sel.value = "interrompeu_round";
    sel.addEventListener("change", renderJogadores);
  }
  renderTime();
  renderJogadores();
  renderMapas();
}

function mostrarAba(qual) {
  const evoAtiva = qual === "evolucao";
  $("#vista-analisar").hidden = evoAtiva;
  $("#vista-evolucao").hidden = !evoAtiva;
  $("#aba-analisar").toggleAttribute("aria-current", false);
  $("#aba-evolucao").toggleAttribute("aria-current", false);
  $(evoAtiva ? "#aba-evolucao" : "#aba-analisar").setAttribute("aria-current", "page");
  if (evoAtiva) carregarEvolucao().catch((e) => erro(e.message));
  history.replaceState(null, "", evoAtiva ? "#evolucao" : location.pathname);
}
let redesenho = null;
addEventListener("resize", () => {
  clearTimeout(redesenho);
  redesenho = setTimeout(() => {
    document.querySelectorAll("#vista-evolucao .grafico > div, #evo-jog-grafico").forEach((el) => {
      if (el._grafico) graficoLinhas(el, el._grafico);
    });
  }, 150);
});
$("#aba-analisar").addEventListener("click", () => mostrarAba("analisar"));
$("#aba-evolucao").addEventListener("click", () => mostrarAba("evolucao"));
if (location.hash === "#evolucao") mostrarAba("evolucao");
