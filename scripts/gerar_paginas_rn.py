"""Gera painel/rn.html a partir de painel/index.html (mesmo motor de gráficos e contas), trocando:
nomes (Lula → Cadu, Flávio → Allyson), dados (dados-rn.js, adaptado ao formato da página nacional),
mapa (municípios do RN no lugar das UFs) e regiões (mesorregiões do RN).

    python scripts/gerar_paginas_rn.py

Rodar de novo sempre que painel/index.html mudar, para o RN acompanhar.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
P = RAIZ / "painel"


def troca(s: str, velho: str, novo: str, vezes: int = 1) -> str:
    assert velho in s, f"trecho não encontrado: {velho[:70]}"
    return s.replace(velho, novo, vezes)


# Navegação própria do RN, igual nas três páginas (a aba ativa fica em negrito).
def subnav(ativa: str) -> str:
    itens = [("rn.html", "Pesquisas do RN"), ("rn-apuracao.html", "Apuração do RN"), ("rn-balanco.html", "Balanço do RN")]
    return ('<p class="sub" style="margin:0 0 4px">'
            + " · ".join(f"<b>{t}</b>" if h == ativa else f'<a href="{h}">{t}</a>' for h, t in itens) + "</p>")


# Adaptador: o motor das páginas nacionais usa os campos lula/flavio; no RN, lula = Cadu (a) e flavio = Allyson (b).
ADAPTADOR = """<script>
// Adaptador: o motor desta página usa os campos lula/flavio; no RN, lula = Cadu (a) e flavio = Allyson (b).
(() => {
  const R = window.DADOS_RN, conv = p => ({ ...p, lula: p.a, flavio: p.b });
  const est = R.primeiro_turno.estado;
  window.DADOS = {
    pesquisas: { ...R.pesquisas, segundo_turno_a_divulgar: [],
      primeiro_turno_ultima_por_instituto: R.pesquisas.primeiro_turno_ultima_por_instituto.map(conv),
      segundo_turno: R.pesquisas.segundo_turno.map(conv) },
    primeiro_turno: { br: { ...est, lula: est.a, flavio: est.b, totalizado_em: "" },
      ...Object.fromEntries(Object.entries(R.primeiro_turno.municipios).map(([cd, m]) => [cd, { ...m, lula: m.a, flavio: m.b }])) },
    boletins: R.boletins || [],
  };
})();
</script>
<script>
(() => {
  const D = window.DADOS"""

s = (P / "index.html").read_text(encoding="utf-8")

# Cabeçalho, título e navegação
s = troca(s, "<title>Monitor Eleição 2026</title>", "<title>RN · Cadu × Allyson</title>")
s = troca(s, '<a href="index.html" aria-current="page">Pesquisas</a>', '<a href="index.html">Pesquisas</a>')
s = troca(s, '<a href="rn-apuracao.html">RN</a>', '<a href="rn-apuracao.html" aria-current="page">RN</a>')
s = troca(s, "<h1>Lula × Flávio nas pesquisas</h1>",
          '<h1>RN · Governador: Cadu × Allyson</h1>\n      ' + subnav("rn.html"))

# Mapa e textos de seção
s = troca(s, "<h2>1º turno por estado</h2>", "<h2>1º turno por município</h2>")
s = troca(s, "Vantagem entre Lula e Flávio nos votos válidos de cada estado (TSE). Passe o mouse ou toque num estado.",
          "Vantagem entre Cadu e Allyson nos votos válidos de cada município (TSE). Passe o mouse ou toque num município.")
s = troca(s, "<h2>1º turno por região</h2>", "<h2>1º turno por região do RN</h2>")
s = troca(s, "Votos válidos. É aqui que nasce a virada na apuração: o Nordeste costuma totalizar por último.",
          "Votos válidos por mesorregião. Os votos de Álvaro Dias (cinza) decidem o 2º turno.")
s = troca(s, "Demais candidatos</span>", "Álvaro Dias e demais</span>")

# Aviso sobre o tamanho dos erros do 1º turno no RN
s = troca(s, '    <p class="aviso" id="explicaModo"></p>',
          '    <p class="aviso" id="explicaModo"></p>\n'
          '    <p class="aviso" style="border-left:3px solid var(--alerta)">Atenção: no 1º turno do RN quase todas as pesquisas erraram muito '
          '(15 a 24 pontos a favor de Allyson; Cadu cresceu na reta final). Por isso esta página abre "como divulgado": a versão '
          '"corrigida" aplica esses erros inteiros e tende a exagerar a vantagem de Cadu.</p>')

# Scripts: mapa e dados do RN, com adaptador para o formato que o motor da página espera
s = troca(s, '<script src="mapa-br.js?v=1"></script>', '<script src="mapa-rn.js?v=1"></script>')
s = troca(s, "document.write('<script src=\"dados.js?t=' + Date.now() + '\"><\\/script>');",
          "document.write('<script src=\"dados-rn.js?t=' + Date.now() + '\"><\\/script>');")
s = troca(s, "<script>\n(() => {\n  const D = window.DADOS", ADAPTADOR)

# Abre "como divulgado"
s = troca(s, 'let modo = "instituto";', 'let modo = "bruta";')

# Regiões: mesorregiões do RN
s = troca(s, 'const nomes = { N: "Norte", NE: "Nordeste", CO: "Centro-Oeste", SE: "Sudeste", S: "Sul", EX: "Exterior" };',
          'const nomes = { Leste: "Leste", Agreste: "Agreste", Central: "Central", Oeste: "Oeste" };')

# Mapa: municípios do RN (malha indexada pelo código IBGE)
ini = s.index("  // ------------------------------------------------ mapa do 1º turno")
fim = s.index('  el("legMapa1t").innerHTML = G.legendaMapa();')
s = s[:ini] + """  // ------------------------------------------------ mapa do 1º turno (municípios)
  const valores1t = {}, rotulos = {};
  // Só três rótulos, espaçados: a região metropolitana de Natal é pequena demais para mais nomes.
  const maiores = Object.values(DADOS_RN.primeiro_turno.municipios).filter(m => ["Natal", "Mossoró", "Caicó"].includes(m.nome));
  for (const m of Object.values(DADOS_RN.primeiro_turno.municipios)) {
    const l = 100 * m.a / m.validos, f = 100 * m.b / m.validos, t = 100 * m.terceiro / m.validos, mg = l - f;
    valores1t[m.ibge] = { cor: G.corMargem(mg),
      dica: `<b>${esc(m.nome)}</b> · ${esc(m.regiao)}<br>Cadu ${fmt(l)}% · Allyson ${fmt(f)}% · Álvaro ${fmt(t)}%<br>Vantagem: ${mg >= 0 ? "Cadu" : "Allyson"} +${fmt(Math.abs(mg))} · ${m.validos.toLocaleString("pt-BR")} válidos` };
  }
  for (const m of maiores) rotulos[m.ibge] = m.nome;
  G.mapa(el("mapa1t"), { base: window.MAPA_RN, valores: valores1t, rotulos, alturaMax: 460, rotulo: "Resultado do 1º turno por município do RN" });
""" + s[fim:]
s = troca(s, 'el("legMapa1t").innerHTML = G.legendaMapa();', 'el("legMapa1t").innerHTML = G.legendaMapa("Cadu", "Allyson");')


# Nomes dos candidatos em todos os textos visíveis
s = s.replace("Lula (PT)", "Cadu (PT)").replace("Flávio Bolsonaro (PL)", "Allyson (União)")
s = s.replace("Lula", "Cadu").replace("Flávio", "Allyson")

(P / "rn.html").write_text(s, encoding="utf-8")
print("painel/rn.html gerado")


# ---------------------------------------------------------------- painel/rn-apuracao.html
s = (P / "apuracao.html").read_text(encoding="utf-8")
s = troca(s, "<title>Apuração ao Vivo</title>", "<title>RN · Apuração ao vivo</title>")
s = troca(s, '<a href="apuracao.html" aria-current="page">', '<a href="apuracao.html">')
s = troca(s, '<a href="rn-apuracao.html">RN</a>', '<a href="rn-apuracao.html" aria-current="page">RN</a>')
s = troca(s, "<h1>Apuração ao vivo</h1>", '<h1>RN · Governador ao vivo</h1>\n      ' + subnav("rn-apuracao.html"))
# O atalho "Governador do RN ao vivo" da página nacional não faz sentido na própria página do RN.
s = troca(s, '\n      <p class="sub" style="margin:0 0 4px"><a href="rn-apuracao.html"><b>Governador do RN ao vivo →</b></a></p>', "")
s = troca(s, "Em cada um variam o voto que ainda falta em cada estado (dentro da incerteza da projeção) e o atraso de cada estado,",
          "Em cada um variam o voto que ainda falta em cada município (dentro da incerteza da projeção) e o atraso de cada município,")
s = troca(s, "No começo da noite, sem ritmo medido, vale o padrão conhecido: Norte e Nordeste totalizam por último.",
          "No começo da noite, sem ritmo medido, supomos que todos os municípios andam no mesmo passo.")
s = troca(s, "<h2>Mapa por estado</h2>", "<h2>Mapa por município</h2>")
s = troca(s, '"Quem lidera em cada estado com os votos já apurados.', '"Quem lidera em cada município com os votos já apurados.')
s = troca(s, '"Resultado projetado de cada estado ao fim da apuração."', '"Resultado projetado de cada município ao fim da apuração."')
s = troca(s, "<h2>Saldo projetado por UF</h2>", "<h2>Saldo projetado nos municípios que mais pesam</h2>")
s = troca(s, "Diferença final esperada em votos (milhões).", "Os 20 municípios com maior diferença final esperada (milhares de votos).")
s = troca(s, "Ver tabela por UF", "Ver tabela por município")
s = troca(s, "Ainda sem ritmo medido por UF", "Ainda sem ritmo medido por município")
s = troca(s, "p.p., média das UFs", "p.p., média dos municípios")
s = s.replace("cada UF parte do resultado", "cada município parte do resultado").replace("dentro de cada UF", "dentro de cada município")
s = troca(s, '\n        <span><i class="tracejada" style="border-color:var(--neutro)"></i>2022: virada com ~67,8% das seções</span>', "")
s = troca(s, '<script src="mapa-br.js?v=1"></script>', '<script src="mapa-rn.js?v=1"></script>')
s = troca(s, 'const FONTE = { arquivo: "estado.json", ramo: "ao-vivo", js: "apuracao-dados.js", variavel: "APURACAO" };',
          'const FONTE = { arquivo: "estado.json", ramo: "ao-vivo-rn", js: "apuracao-rn-dados.js", variavel: "APURACAO_RN" };')
s = s.replace("Lula (PT)", "Cadu (PT)").replace("Flávio Bolsonaro (PL)", "Allyson (União)")
s = s.replace("Lula", "Cadu").replace("Flávio", "Allyson")
(P / "rn-apuracao.html").write_text(s, encoding="utf-8")
print("painel/rn-apuracao.html gerado")


# ---------------------------------------------------------------- painel/rn-balanco.html
s = (P / "balanco.html").read_text(encoding="utf-8")
s = troca(s, "<title>Balanço da Eleição</title>", "<title>RN · Balanço</title>")
s = troca(s, '<a href="balanco.html" aria-current="page">', '<a href="balanco.html">')
s = troca(s, '<a href="rn-apuracao.html">RN</a>', '<a href="rn-apuracao.html" aria-current="page">RN</a>')
s = troca(s, "<h1>Balanço da eleição</h1>", '<h1>RN · Balanço do governador</h1>\n      ' + subnav("rn-balanco.html"))
s = troca(s, "<h2>2º turno por estado</h2>", "<h2>2º turno por município</h2>")
s = troca(s, "Passe o mouse ou toque num estado para comparar com o 1º turno.", "Passe o mouse ou toque num município para comparar com o 1º turno.")
s = troca(s, "<h2>Onde cada um cresceu, por UF</h2>", "<h2>Onde cada um cresceu, por município</h2>")
s = troca(s, "Variação de Lula nos votos válidos, do 1º para o 2º turno (p.p.).",
          "Variação de Lula nos votos válidos, do 1º para o 2º turno (p.p.): os 10 municípios em que mais cresceu e os 10 em que menos cresceu.")
s = troca(s, "Ver tabela por UF", "Ver tabela por município")
s = troca(s, "<h2>2º turno por região</h2>", "<h2>2º turno por região do RN</h2>")
s = troca(s, '<script src="mapa-br.js?v=1"></script>', '<script src="mapa-rn.js?v=1"></script>')
s = troca(s, "document.write('<script src=\"dados.js?t=' + Date.now() + '\"><\/script>');",
          "document.write('<script src=\"dados-rn.js?t=' + Date.now() + '\"><\/script>');")
s = troca(s, "<script>\n(() => {\n  const D = window.DADOS", ADAPTADOR)
s = troca(s, 'const FONTE = { arquivo: "estado.json", ramo: "ao-vivo", js: "apuracao-dados.js", variavel: "APURACAO" };',
          'const FONTE = { arquivo: "estado.json", ramo: "ao-vivo-rn", js: "apuracao-rn-dados.js", variavel: "APURACAO_RN" };')
s = s.replace("Lula (PT)", "Cadu (PT)").replace("Flávio Bolsonaro (PL)", "Allyson (União)")
s = s.replace("Lula", "Cadu").replace("Flávio", "Allyson")
(P / "rn-balanco.html").write_text(s, encoding="utf-8")
print("painel/rn-balanco.html gerado")
