"use strict";

const $ = (s) => document.querySelector(s);
const estado = { gravacao: null, partida: undefined, time: [], sugestao: {}, config: null };

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  let data = null;
  try { data = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok) throw new Error((data && data.detail) || `Erro ${r.status}`);
  return data;
}
const json = (method, body) => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function erro(msg) {
  const el = $("#erro");
  el.textContent = msg || "";
  el.hidden = !msg;
}

function dataCurta(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) + " às " +
    d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function relogio(s) {
  if (s == null) return "";
  s = Math.round(s);
  const m = Math.floor(s / 60), r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}
function segundos(txt) {
  const p = String(txt || "").trim().split(":").map(Number);
  if (p.some(isNaN) || !p.length) return null;
  return p.reduce((a, v) => a * 60 + v, 0);
}

// ---------------------------------------------------------------- configurações
async function carregarConfig() {
  estado.config = await api("/api/config");
  document.querySelectorAll(".palavra").forEach((el) => { el.textContent = estado.config.palavra; });
  const semRiot = !estado.config.tem_chave || !estado.config.riot_id;
  $("#partida-ajuda").textContent = semRiot
    ? "Para cruzar com a partida, adicione a chave da HenrikDev e seu Riot ID em Configurações."
    : `Busca as últimas partidas de ${estado.config.riot_id} para cruzar a call com rounds, kills e mortes.`;
  $("#buscar-partidas").disabled = semRiot;
}

function abrirConfig() {
  const c = estado.config;
  $("#c-chave").value = "";
  $("#c-chave").placeholder = c.tem_chave ? "chave salva (deixe vazio para manter)" : "cole a chave aqui";
  $("#c-riot").value = c.riot_id || "";
  $("#c-regiao").value = c.regiao || "br";
  $("#c-palavra").value = c.palavra || "";
  $("#c-modelo").value = c.modelo || "large-v3-turbo";
  $("#c-erro").hidden = true;
  $("#config").showModal();
}

$("#abrir-config").addEventListener("click", abrirConfig);
$("#form-config").addEventListener("submit", async (ev) => {
  if (ev.submitter && ev.submitter.value === "cancel") return;
  ev.preventDefault();
  try {
    await api("/api/config", json("PUT", {
      api_key: $("#c-chave").value, riot_id: $("#c-riot").value, regiao: $("#c-regiao").value,
      palavra: $("#c-palavra").value, modelo: $("#c-modelo").value,
    }));
    $("#config").close();
    await carregarConfig();
  } catch (e) {
    $("#c-erro").textContent = e.message;
    $("#c-erro").hidden = false;
  }
});

// ---------------------------------------------------------------- 1. gravação
const drop = $("#drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => {
  e.preventDefault(); drop.classList.add("arrastando");
}));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("arrastando")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (f) enviarArquivo(f);
});
$("#arquivo").addEventListener("change", (e) => { if (e.target.files[0]) enviarArquivo(e.target.files[0]); });

async function enviarArquivo(f) {
  erro("");
  mostrarGravacao(`Enviando ${esc(f.name)}…`);
  const fd = new FormData();
  fd.append("arquivo", f);
  try {
    gravacaoPronta(await api("/api/gravacoes", { method: "POST", body: fd }));
  } catch (e) { mostrarGravacao(""); erro(e.message); }
}

$("#form-caminho").addEventListener("submit", async (e) => {
  e.preventDefault();
  erro("");
  const caminho = $("#caminho").value.trim();
  if (!caminho) return;
  try {
    gravacaoPronta(await api("/api/gravacoes/caminho", json("POST", { caminho })));
  } catch (err) { erro(err.message); }
});

function mostrarGravacao(html) {
  const el = $("#gravacao-info");
  el.innerHTML = html;
  el.hidden = !html;
}

function gravacaoPronta(g) {
  estado.gravacao = g;
  const inicio = g.inicio ? ` Gravação começou ${dataCurta(g.inicio)}.` : "";
  mostrarGravacao(`<b>${esc(g.nome)}</b><br>${g.jogadores.length} pessoas na call: ` +
    g.jogadores.map((j) => esc(j.apelido)).join(", ") + "." + inicio);
  $("#passo-gravacao").classList.add("ok");
  if (!$("#nome").value) $("#nome").value = "";
  renderJogadores();
  atualizarBotao();
  if (estado.partidasCarregadas) buscarPartidas();
}

// ---------------------------------------------------------------- 2. partida
$("#buscar-partidas").addEventListener("click", buscarPartidas);
$("#sem-partida").addEventListener("click", () => {
  estado.partida = null;
  estado.time = [];
  document.querySelectorAll(".partida").forEach((b) => b.setAttribute("aria-checked", "false"));
  $("#passo-partida").classList.add("ok");
  $("#passo-sinc").hidden = true;
  renderJogadores();
  atualizarBotao();
});

async function buscarPartidas() {
  erro("");
  const box = $("#partidas");
  box.innerHTML = '<p class="ajuda">Buscando…</p>';
  try {
    const q = estado.gravacao ? `?gravacao=${encodeURIComponent(estado.gravacao.id)}` : "";
    const lista = await api(`/api/partidas${q}`);
    estado.partidasCarregadas = true;
    if (!lista.length) { box.innerHTML = '<p class="ajuda">Nenhuma partida recente encontrada.</p>'; return; }
    box.innerHTML = "";
    lista.forEach((m) => box.appendChild(cartaoPartida(m)));
    const provavel = lista.find((m) => m.provavel);
    if (provavel && estado.partida === undefined) escolherPartida(provavel);
  } catch (e) { box.innerHTML = ""; erro(e.message); }
}

function cartaoPartida(m) {
  const b = document.createElement("button");
  b.type = "button";
  const empate = m.placar && m.placar[0] === m.placar[1];
  b.className = "partida " + (empate ? "" : m.venceu === true ? "vitoria" : m.venceu === false ? "derrota" : "");
  b.setAttribute("role", "radio");
  b.setAttribute("aria-checked", estado.partida && estado.partida.id === m.id ? "true" : "false");
  b.dataset.id = m.id;
  const placar = m.placar ? `${m.placar[0]}–${m.placar[1]}` : "—";
  const kda = m.kda ? `${m.kda[0]}/${m.kda[1]}/${m.kda[2]}` : "";
  b.innerHTML = `<span class="mapa">${esc(m.mapa || "?")}</span>
    <span class="placar">${placar}</span>
    <span class="det">${esc(m.agente || "")}${kda ? " " + kda : ""}</span>
    <span class="det">${esc(m.modo || "")}, ${dataCurta(m.inicio)}</span>
    ${m.provavel ? '<span class="selo">Bate com o horário da gravação</span>' : ""}`;
  b.addEventListener("click", () => escolherPartida(m));
  return b;
}

async function escolherPartida(m) {
  estado.partida = m;
  document.querySelectorAll(".partida").forEach((b) =>
    b.setAttribute("aria-checked", b.dataset.id === m.id ? "true" : "false"));
  $("#passo-partida").classList.add("ok");
  $("#passo-sinc").hidden = false;
  $("#passo-sinc").classList.add("ok");
  if (!$("#nome").value) $("#nome").value = `${m.mapa || "Partida"} ${m.placar ? m.placar.join("-") : ""}`.trim();
  try {
    const q = estado.gravacao ? `?gravacao=${encodeURIComponent(estado.gravacao.id)}` : "";
    const t = await api(`/api/partidas/${encodeURIComponent(m.id)}/time${q}`);
    estado.time = t.time;
    estado.sugestao = t.sugestao || {};
  } catch (e) { erro(e.message); }
  renderJogadores();
  atualizarBotao();
}

// ---------------------------------------------------------------- 4. jogadores
function renderJogadores() {
  const g = estado.gravacao;
  const tabela = $("#jogadores");
  if (!g) return;
  $("#jogadores-ajuda").textContent = estado.time.length
    ? "Ligue cada pessoa da call à conta dela na partida. Fica salvo para as próximas."
    : "Escolha como cada um aparece no relatório.";
  const tbody = tabela.querySelector("tbody");
  tbody.innerHTML = "";
  g.jogadores.forEach((j) => {
    const tr = document.createElement("tr");
    const escolhido = j.riot || estado.sugestao[j.apelido] || "";
    const opcoes = ['<option value="">não ligar</option>'].concat(estado.time.map((p) =>
      `<option value="${esc(p.riot)}" ${p.riot.toLowerCase() === escolhido.toLowerCase() ? "selected" : ""}>` +
      `${esc(p.riot)}${p.agente ? " (" + esc(p.agente) + ")" : ""}</option>`)).join("");
    tr.innerHTML = `<td>${esc(j.discord)}</td>
      <td><input type="text" value="${esc(j.apelido)}" data-k="apelido" aria-label="Nome de ${esc(j.discord)}"></td>
      <td>${estado.time.length ? `<select data-k="riot" aria-label="Conta de ${esc(j.discord)}">${opcoes}</select>` : '<span class="ajuda">escolha a partida</span>'}</td>`;
    tr.dataset.discord = j.discord;
    tbody.appendChild(tr);
  });
  tabela.hidden = false;
  $("#passo-jogadores").classList.add("ok");
}

function lerJogadores() {
  return [...document.querySelectorAll("#jogadores tbody tr")].map((tr) => {
    const sel = tr.querySelector("select");
    return {
      discord: tr.dataset.discord,
      apelido: tr.querySelector("input").value.trim() || null,
      riot: sel ? sel.value : null,
    };
  });
}

// ---------------------------------------------------------------- 3. sinc + enviar
function lerSinc() {
  const modo = document.querySelector('input[name="sinc"]:checked').value;
  const s = { modo };
  if (modo === "personalizado") {
    s.round = Number($("#s-round").value) || 1;
    s.fase = $("#s-fase").value;
    s.restantes_s = segundos($("#s-relogio").value);
    if (s.restantes_s == null) throw new Error("Tempo do relógio inválido. Use m:ss, ex.: 0:25.");
  }
  if (modo === "manual") {
    s.ancora_manual_s = segundos($("#s-manual").value);
    if (s.ancora_manual_s == null) throw new Error("Informe o momento da gravação como mm:ss, ex.: 12:34.");
  }
  return s;
}

function atualizarBotao() {
  $("#analisar").disabled = !estado.gravacao || estado.partida === undefined;
}

$("#analisar").addEventListener("click", async () => {
  erro("");
  try {
    const corpo = {
      gravacao: estado.gravacao.id,
      nome: $("#nome").value.trim() || null,
      partida_id: estado.partida ? estado.partida.id : null,
      sinc: estado.partida ? lerSinc() : { modo: "nenhum" },
      jogadores: lerJogadores(),
    };
    $("#analisar").disabled = true;
    await api("/api/analises", json("POST", corpo));
    await atualizarHistorico();
    $("#andamento").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) { erro(e.message); } finally { atualizarBotao(); }
});

// ---------------------------------------------------------------- histórico
async function atualizarHistorico() {
  const d = await api("/api/analises");
  const and = $("#andamento");
  and.innerHTML = d.em_andamento.map((t) => `
    <div class="tarefa">
      <div class="t">${esc(t.nome)}</div>
      <div class="e">${esc(t.etapa)}${t.estado === "rodando" ? ` (${Math.round(100 * t.progresso)}%)` : ""}</div>
      <div class="barra"><span style="width:${Math.round(100 * t.progresso)}%"></span></div>
    </div>`).join("") + d.falhas.map((t) => `
    <div class="tarefa falhou"><div class="t">${esc(t.nome)}</div>
      <div class="e">A análise parou: ${esc(t.erro)}</div></div>`).join("");
  estado.rodando = d.em_andamento.map((t) => t.id);

  const lista = $("#lista");
  lista.innerHTML = "";
  d.analises.forEach((a) => {
    const li = document.createElement("li");
    const placar = a.placar ? ` ${a.placar[0]}–${a.placar[1]}` : "";
    const morto = a.fala_morto_s != null ? `<span><b>${Math.round(a.fala_morto_s)}s</b> fala de morto</span>` : "";
    li.innerHTML = `<button type="button" class="item">
      <span class="t">${esc(a.nome)}</span>
      <span class="d">${a.mapa ? esc(a.mapa) + placar + ", " : ""}${dataCurta(a.criado_em)}</span>
      <span class="n"><span><b>${a.interrupcoes ?? "—"}</b> interrupções</span>${morto}</span>
    </button>`;
    li.querySelector("button").addEventListener("click", () => abrirRelatorio(a));
    lista.appendChild(li);
  });
  $("#vazio").hidden = d.analises.length > 0 || d.em_andamento.length > 0;
  return d;
}

async function acompanhar() {
  try { await atualizarHistorico(); } catch { /* servidor reiniciando */ }
  setTimeout(acompanhar, (estado.rodando || []).length ? 1000 : 4000);
}

// ---------------------------------------------------------------- visor
function abrirRelatorio(a) {
  $("#visor-titulo").textContent = a.nome;
  const base = `/relatorios/${encodeURIComponent(a.id)}`;
  $("#visor-frame").src = base + "/";
  $("#visor-downloads").innerHTML =
    `<a href="${base}/transcricao.txt">Transcrição</a><a href="${base}/transcricao.srt">Legenda</a>` +
    `<a href="${base}/analise.json">Dados</a><a href="${base}/" target="_blank" rel="noopener">Abrir em nova aba</a>`;
  $("#visor").hidden = false;
  $("#fechar-visor").focus();
}
$("#fechar-visor").addEventListener("click", () => { $("#visor").hidden = true; $("#visor-frame").src = "about:blank"; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#visor").hidden) $("#fechar-visor").click(); });

carregarConfig().catch((e) => erro(e.message));
acompanhar();
