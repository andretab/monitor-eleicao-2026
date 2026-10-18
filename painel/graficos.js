// Gráficos em SVG puro, sem biblioteca externa: o site precisa abrir rápido no celular e direto do disco.
// Cada gráfico mede a largura do contêiner e se redesenha quando ela muda.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const registrados = new Map();

  function preparar(el, cfg, desenho) {
    registrados.set(el, () => desenho(el, cfg));
    desenho(el, cfg);
  }
  let espera;
  addEventListener("resize", () => { clearTimeout(espera); espera = setTimeout(() => registrados.forEach((f, el) => el.isConnected ? f() : registrados.delete(el)), 120); });

  function dica(el) {
    let d = el.querySelector(".dica");
    if (!d) { d = document.createElement("div"); d.className = "dica"; el.appendChild(d); }
    return {
      mostrar(html, x, y) {
        d.innerHTML = html; d.style.opacity = 1;
        const w = d.offsetWidth, h = d.offsetHeight, W = el.clientWidth;
        d.style.left = Math.min(Math.max(x - w / 2, 0), W - w) + "px";
        d.style.top = Math.max(y - h - 12, 0) + "px";
      },
      esconder() { d.style.opacity = 0; },
    };
  }
  const pos = (el, ev) => { const r = el.getBoundingClientRect(); const t = ev.touches ? ev.touches[0] : ev; return [t.clientX - r.left, t.clientY - r.top]; };

  // ---------------------------------------------------------------- linhas no tempo
  // cfg: { altura, x:{min,max} (ISO), y:{min,max,passo,fmt}, series:[{nome,cor,pontos:[[iso,y]],tracejada}],
  //        pontos:[{x,y,cor,dica}], refY:[{y,rotulo}], refX:[{x,rotulo}], dicaX(iso) -> html }
  function linhas(el, cfg) {
    const W = Math.max(el.clientWidth, 280), estreito = W < 560;
    const H = cfg.altura || (estreito ? 260 : 340);
    const m = { e: 40, d: estreito ? 56 : 88, t: 14, b: 28 };
    // Eixo x: datas ISO (padrão) ou números (cfg.x.tipo = "num", com cfg.x.passo e cfg.x.fmt).
    const num = cfg.x.tipo === "num";
    const ms = v => num ? v : new Date(v + "T12:00:00").getTime();
    const x0 = ms(cfg.x.min), x1 = ms(cfg.x.max);
    const X = s => m.e + (W - m.e - m.d) * (ms(s) - x0) / (x1 - x0);
    const Y = v => m.t + (H - m.t - m.b) * (cfg.y.max - v) / (cfg.y.max - cfg.y.min);
    const fmt = cfg.y.fmt || (v => v);
    const fmtValor = cfg.y.fmtValor || fmt;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.rotulo || "gráfico")}">`;
    for (let v = cfg.y.min; v <= cfg.y.max + 1e-9; v += cfg.y.passo)
      s += `<line class="grade-l" x1="${m.e}" x2="${W - m.d}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.e - 8}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
    if (num) {
      const passo = cfg.x.passo * (estreito ? 2 : 1);
      for (let v = x0; v <= x1 + 1e-9; v += passo) s += `<text x="${X(v)}" y="${H - 8}" text-anchor="middle">${esc(cfg.x.fmt(v))}</text>`;
    } else {
      const passoDias = Math.ceil((x1 - x0) / 864e5 / (estreito ? 4 : 8));
      for (let t = x0; t <= x1; t += passoDias * 864e5) {
        const iso = new Date(t).toISOString().slice(0, 10);
        s += `<text x="${X(iso)}" y="${H - 8}" text-anchor="middle">${iso.slice(8, 10)}/${iso.slice(5, 7)}</text>`;
      }
    }
    for (const r of cfg.refY || [])
      s += `<line x1="${m.e}" x2="${W - m.d}" y1="${Y(r.y)}" y2="${Y(r.y)}" stroke="var(--texto-3)" stroke-dasharray="4 4"/>` +
        (r.rotulo ? `<text x="${m.e + 4}" y="${Y(r.y) - 5}">${esc(r.rotulo)}</text>` : "");
    // Rótulos das linhas verticais: junto à borda direita alinham para dentro; se dois colidem, o segundo desce.
    let caixaAnterior = null;
    for (const r of cfg.refX || []) {
      const xr = X(r.x), larg = 7 * r.rotulo.length, fim = xr > W - m.d - 30;
      const caixa = fim ? [xr - 4 - larg, xr - 4] : [xr + 4, xr + 4 + larg];
      const desce = caixaAnterior && caixa[0] < caixaAnterior[1] + 4 && caixa[1] > caixaAnterior[0] - 4;
      const yr = m.t + 10 + (desce ? 13 : 0);
      s += `<line x1="${xr}" x2="${xr}" y1="${m.t}" y2="${H - m.b}" stroke="var(--texto-3)" stroke-dasharray="2 4"/>` +
        `<text x="${fim ? xr - 4 : xr + 4}" y="${yr}" ${fim ? 'text-anchor="end"' : ""}>${esc(r.rotulo)}</text>`;
      caixaAnterior = caixa;
    }
    for (const p of cfg.pontos || [])
      s += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${p.raio || 4}" fill="${p.cor}" fill-opacity="${p.opacidade ?? .35}" stroke="${p.borda || "none"}" stroke-width="2"/>`;
    const fins = [];
    for (const se of cfg.series) {
      if (!se.pontos.length) continue;
      s += `<polyline fill="none" stroke="${se.cor}" stroke-width="${se.largura || 2.5}" stroke-opacity="${se.opacidade ?? 1}" stroke-linejoin="round" stroke-linecap="round" ${se.tracejada ? 'stroke-dasharray="6 5"' : ""} points="${se.pontos.map(p => X(p[0]) + "," + Y(p[1])).join(" ")}"/>`;
      const u = se.pontos.at(-1);
      if (!se.tracejada) s += `<circle cx="${X(u[0])}" cy="${Y(u[1])}" r="5" fill="${se.cor}" stroke="#fff" stroke-width="2"/>`;
      if (se.rotulo !== false) fins.push({ y: Y(u[1]), x: X(u[0]), texto: `${se.nome} ${fmtValor(u[1])}`, curto: fmtValor(u[1]), cor: se.cor });
    }
    // Rótulos diretos no fim das linhas, afastados para não se sobreporem.
    fins.sort((a, b) => a.y - b.y);
    for (let i = 1; i < fins.length; i++) if (fins[i].y - fins[i - 1].y < 16) fins[i].y = fins[i - 1].y + 16;
    for (const f of fins) s += `<text class="rotulo-dado" x="${f.x + 9}" y="${f.y + 4}" style="fill:${f.cor}">${esc(estreito ? f.curto : f.texto)}</text>`;
    s += `<line class="mira" x1="0" x2="0" y1="${m.t}" y2="${H - m.b}" stroke="var(--texto)" stroke-opacity=".25" visibility="hidden"/>`;
    s += `<rect x="${m.e}" y="${m.t}" width="${W - m.e - m.d}" height="${H - m.t - m.b}" fill="transparent"/></svg>`;
    el.innerHTML = s;
    if (!cfg.dicaX) return;
    const d = dica(el), mira = el.querySelector(".mira");
    const datas = [...new Set([...(cfg.pontos || []).map(p => p.x), ...(cfg.alvosDica || cfg.series.flatMap(se => se.pontos.map(p => p[0])))])].sort((a, b) => ms(a) - ms(b));
    const mover = ev => {
      const [px, py] = pos(el, ev);
      const alvo = datas.reduce((a, b) => Math.abs(X(b) - px) < Math.abs(X(a) - px) ? b : a, datas[0]);
      mira.setAttribute("x1", X(alvo)); mira.setAttribute("x2", X(alvo)); mira.setAttribute("visibility", "visible");
      d.mostrar(cfg.dicaX(alvo), X(alvo), Math.min(py, H / 2));
    };
    const sair = () => { mira.setAttribute("visibility", "hidden"); d.esconder(); };
    const svg = el.querySelector("svg");
    svg.addEventListener("mousemove", mover); svg.addEventListener("touchstart", mover, { passive: true });
    svg.addEventListener("mouseleave", sair);
  }

  // ---------------------------------------------------------------- barras horizontais
  // cfg: { itens:[{rotulo, valor, cor, dica, texto}], divergente, min, max, fmt, rotuloNeg, rotuloPos }
  function barras(el, cfg) {
    const W = Math.max(el.clientWidth, 280), estreito = W < 560;
    const lin = cfg.alturaLinha || 30, rot = cfg.larguraRotulo || (estreito ? 104 : 150);
    const topo = cfg.rotuloNeg ? 22 : 6;
    const H = topo + cfg.itens.length * lin + 6;
    const vals = cfg.itens.map(i => i.valor);
    const max = cfg.max ?? Math.max(...vals.map(Math.abs), 1e-9);
    const min = cfg.divergente ? -(cfg.max ?? max) : (cfg.min ?? 0);
    // colunaValor: valores numa coluna fixa à direita (quando há marcador, o rótulo na ponta da barra colidiria).
    const col = cfg.colunaValor ? (estreito ? cfg.colunaValor * .8 : cfg.colunaValor) : 0;
    // Divergente com rótulo na ponta: reserva espaço à esquerda também, para o número não encostar no nome.
    const folga = cfg.divergente && !col ? (estreito ? 36 : 44) : 0;
    const area = [rot + 8 + folga, W - (col ? col + 12 : (estreito ? 44 : 60))];
    const X = v => area[0] + (area[1] - area[0]) * (v - min) / (max - min);
    const fmt = cfg.fmt || (v => v);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.rotulo || "gráfico de barras")}">`;
    if (cfg.rotuloNeg) s += `<text x="${X(min)}" y="12">${esc(cfg.rotuloNeg)}</text><text x="${X(max)}" y="12" text-anchor="end">${esc(cfg.rotuloPos)}</text>`;
    if (col && cfg.tituloColuna) s += `<text x="${W - 2}" y="12" text-anchor="end">${esc(cfg.tituloColuna)}</text>`;
    cfg.itens.forEach((it, i) => {
      const y = topo + i * lin, meio = y + lin / 2;
      const a = X(Math.min(0, it.valor)), b = X(Math.max(0, it.valor)), w = Math.max(b - a, 2);
      s += `<g class="item" data-i="${i}"><rect x="0" y="${y}" width="${W}" height="${lin}" fill="transparent"/>`;
      s += `<text class="rotulo-cat" x="${rot}" y="${meio + 4}" text-anchor="end">${esc(it.rotulo)}</text>`;
      s += `<rect x="${a}" y="${meio - 8}" width="${w}" height="16" rx="4" fill="${it.cor}"/>`;
      if (it.marcador) s += `<circle cx="${X(it.marcador.valor)}" cy="${meio}" r="5" fill="#fff" stroke="${it.marcador.cor || "var(--texto)"}" stroke-width="2.5"/>`;
      if (col) s += `<text class="rotulo-dado" x="${W - 2}" y="${meio + 4}" text-anchor="end">${esc(it.texto ?? fmt(it.valor))}</text></g>`;
      else { const tx = it.valor >= 0 ? b + 6 : a - 6;
        s += `<text class="rotulo-dado" x="${tx}" y="${meio + 4}" text-anchor="${it.valor >= 0 ? "start" : "end"}">${esc(it.texto ?? fmt(it.valor))}</text></g>`; }
    });
    if (cfg.divergente || min < 0) s += `<line class="eixo-zero" x1="${X(0)}" x2="${X(0)}" y1="${topo - 2}" y2="${H - 4}"/>`;
    s += `</svg>`;
    el.innerHTML = s;
    const d = dica(el);
    el.querySelectorAll(".item").forEach(g => {
      const it = cfg.itens[+g.dataset.i];
      if (!it.dica) return;
      const ver = ev => { const [px, py] = pos(el, ev); d.mostrar(it.dica, px, py); };
      g.addEventListener("mousemove", ver); g.addEventListener("touchstart", ver, { passive: true }); g.addEventListener("mouseleave", d.esconder);
    });
  }

  // ---------------------------------------------------------------- barras empilhadas (100%)
  // cfg: { itens:[{rotulo, partes:[{valor, cor, nome}], dica, direita}] }
  function empilhadas(el, cfg) {
    const W = Math.max(el.clientWidth, 280), estreito = W < 560;
    const lin = 40, rot = estreito ? 92 : 120, dir = cfg.direita ? (estreito ? 70 : 96) : 8;
    const H = cfg.itens.length * lin + 4;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.rotulo || "barras empilhadas")}">`;
    cfg.itens.forEach((it, i) => {
      const y = i * lin, tot = it.partes.reduce((a, p) => a + p.valor, 0) || 1;
      let x = rot + 8; const larg = W - rot - 8 - dir;
      s += `<g class="item" data-i="${i}"><rect x="0" y="${y}" width="${W}" height="${lin}" fill="transparent"/>`;
      s += `<text class="rotulo-cat" x="${rot}" y="${y + lin / 2 + 4}" text-anchor="end">${esc(it.rotulo)}</text>`;
      it.partes.forEach((p, k) => {
        const w = larg * p.valor / tot, gap = k < it.partes.length - 1 ? 2 : 0;
        if (w > 0) s += `<rect x="${x}" y="${y + 9}" width="${Math.max(w - gap, 0)}" height="22" rx="4" fill="${p.cor}"/>`;
        if (w > 44 && p.texto) s += `<text x="${x + 8}" y="${y + lin / 2 + 4}" style="fill:#fff;font-weight:600">${esc(p.texto)}</text>`;
        x += w;
      });
      if (cfg.direita) s += `<text class="rotulo-dado" x="${W - 4}" y="${y + lin / 2 + 4}" text-anchor="end">${esc(it.direita || "")}</text>`;
      s += `</g>`;
    });
    s += `</svg>`;
    el.innerHTML = s;
    const d = dica(el);
    el.querySelectorAll(".item").forEach(g => {
      const it = cfg.itens[+g.dataset.i];
      if (!it.dica) return;
      const ver = ev => { const [px, py] = pos(el, ev); d.mostrar(it.dica, px, py); };
      g.addEventListener("mousemove", ver); g.addEventListener("touchstart", ver, { passive: true }); g.addEventListener("mouseleave", d.esconder);
    });
  }

  // Duelo Lula × Flávio: barra dividida com os dois percentuais grandes.
  function duelo(el, lula, flavio, rotuloL = "Lula (PT)", rotuloF = "Flávio Bolsonaro (PL)", nota = "50%") {
    const fmt = v => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const pl = 100 * lula / (lula + flavio || 1);
    el.innerHTML = `<div class="duelo"><div class="nomes"><div class="lula">${rotuloL}<b class="num">${fmt(pl)}%</b></div>` +
      `<div class="flavio" style="text-align:right">${rotuloF}<b class="num">${fmt(100 - pl)}%</b></div></div>` +
      `<div class="trilho"><span style="width:${pl}%;background:var(--lula)"></span><span style="width:${100 - pl}%;background:var(--flavio)"></span></div>` +
      `<div class="legenda-meio">${nota}</div></div>`;
  }

  window.G = {
    linhas: (el, cfg) => preparar(el, cfg, linhas),
    barras: (el, cfg) => preparar(el, cfg, barras),
    empilhadas: (el, cfg) => preparar(el, cfg, empilhadas),
    duelo, esc,
  };
})();
