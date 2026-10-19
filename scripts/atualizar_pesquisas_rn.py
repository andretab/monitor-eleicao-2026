"""Atualiza as pesquisas para governador do RN (Cadu × Allyson) lendo a Wikipédia e regenera painel/dados-rn.js.

Página: "Pesquisas eleitorais para a eleição estadual de 2026 no Rio Grande do Norte".
  - "Primeiro turno (governador)" > "2026": última pesquisa de cada instituto antes de 4/10 (cenário 1),
    usada para medir o erro de cada instituto contra a urna;
  - "Segundo turno (governador)" > "Allyson e Cadu de Lula": todas as pesquisas depois de 4/10.
As seções são achadas pelo título. Se a leitura vier com menos pesquisas do que já havia, nada é gravado.
Roda no mesmo robô de hora em hora das pesquisas nacionais.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import lxml.html

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = "Pesquisas eleitorais para a eleição estadual de 2026 no Rio Grande do Norte"
MESES = {m: i for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                    "setembro", "outubro", "novembro", "dezembro"], 1)}
PRIMEIRO_TURNO = date(2026, 10, 4)
# Só pesquisas da reta final medem o erro do instituto: cobrar de uma pesquisa de maio o resultado de
# outubro seria medir mudança de opinião, não erro. Quem não tem pesquisa nessa janela usa o erro médio.
INICIO_RETA_FINAL = date(2026, 9, 15)


def api(**params) -> dict:
    url = "https://pt.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"format": "json", "formatversion": 2, "page": PAGINA, **params})
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-eleicao-2026 (github.com/andretab)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def secao(*caminho: str) -> str:
    """Índice da seção que segue a sequência de títulos dada (cada um contido no título da seção)."""
    fase = 0
    for s in api(action="parse", prop="sections")["parse"]["sections"]:
        linha = re.sub("<.*?>", "", s["line"]).strip()
        if caminho[fase].lower() in linha.lower():
            fase += 1
            if fase == len(caminho):
                return s["index"]
    raise RuntimeError(f"seção {' > '.join(caminho)} não encontrada")


def numero(txt: str) -> float | None:
    txt = txt.replace("±", "").replace("%", "").replace(" ", "").replace(" ", "").replace(" ", "").strip()
    if not re.search(r"\d", txt) or "—" in txt:
        return None
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def datas(txt: str) -> tuple[str, str]:
    """'29 de agosto a 1° de setembro' / '9 e 12 de outubro' / '16 a 21 de julho de 2026' → ISO."""
    txt = txt.lower().replace("º", "").replace("°", "")
    pares = re.findall(r"(\d{1,2})(?:\s+de\s+([a-zç]+))?(?:\s+de\s+(\d{4}))?", txt)
    dias, mes, ano = [], None, 2026
    for d, m, a in reversed(pares):
        if a:
            ano = int(a)
        if m in MESES:
            mes = MESES[m]
        dias.append(date(ano, mes, int(d)))
    dias.reverse()
    return dias[0].isoformat(), dias[-1].isoformat()


def linhas(html: str):
    doc = lxml.html.fromstring(html)
    tabela = doc.xpath("//table[contains(@class,'wikitable')]")[0]
    for tr in tabela.xpath(".//tr"):
        tds = [re.sub(r"\[[^\]]*\]", "", td.text_content()).strip() for td in tr.xpath("./td")]
        if len(tds) >= 6 and re.search(r"\d", tds[1]) and not re.fullmatch(r"\d", tds[0]):
            try:
                ini, fim = datas(tds[1])
            except (ValueError, TypeError):
                continue
            yield tds, ini, fim


def main() -> int:
    caminho = RAIZ / "dados" / "rn" / "pesquisas.json"
    atual = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {"segundo_turno": []}

    # 2º turno: colunas = instituto, datas, amostra, margem, Allyson, Cadu, indecisos, vantagem.
    segundo = []
    for tds, ini, fim in linhas(api(action="parse", prop="text", section=secao("Segundo turno", "Allyson e Cadu"))["parse"]["text"]):
        if date.fromisoformat(fim) <= PRIMEIRO_TURNO:
            continue
        b, a = numero(tds[4]), numero(tds[5])
        if a is None or b is None:
            continue
        segundo.append({"instituto": tds[0], "inicio": ini, "fim": fim, "amostra": int(numero(tds[2]) or 0),
                        "margem": numero(tds[3]), "a": a, "b": b, "indecisos": numero(tds[6]) if len(tds) > 6 else None})

    # 1º turno: colunas = instituto, datas, amostra, margem, cenário, Allyson, Álvaro, Cadu, outros, indecisos.
    primeiro = {}
    for tds, ini, fim in linhas(api(action="parse", prop="text", section=secao("Primeiro turno", "2026"))["parse"]["text"]):
        if len(tds) < 10 or tds[4] != "1" or not INICIO_RETA_FINAL <= date.fromisoformat(fim) <= PRIMEIRO_TURNO:
            continue
        b, t, a = numero(tds[5]), numero(tds[6]), numero(tds[7])
        if None in (a, b, t) or tds[0] in primeiro:
            continue  # a tabela vem da mais nova para a mais antiga: fica a primeira de cada instituto
        primeiro[tds[0]] = {"instituto": tds[0], "inicio": ini, "fim": fim, "amostra": int(numero(tds[2]) or 0),
                            "a": a, "b": b, "terceiro": t, "outros": numero(tds[8]), "indecisos": numero(tds[9])}

    da_wiki = [p for p in atual.get("segundo_turno", []) if p.get("fonte") != "extra"]
    if len(segundo) < len(da_wiki) - 1:
        print(f"ABORTADO: li {len(segundo)} pesquisas do 2º turno, mas já havia {len(da_wiki)}. Arquivo mantido.")
        return 1
    na_wiki = {(p["instituto"], p["fim"]) for p in segundo}
    extras = [e for e in atual.get("segundo_turno_extras", []) if (e["instituto"], e["fim"]) not in na_wiki]
    agora = datetime.now(timezone(timedelta(hours=-3)))
    saida = {
        "_leia": "a = Cadu (PT), b = Allyson (União), terceiro = Álvaro Dias (PL). Percentuais como divulgados; "
                 "'indecisos' = indecisos + brancos/nulos. segundo_turno_extras: achadas fora da Wikipédia (com 'url').",
        "fonte": "https://pt.wikipedia.org/wiki/" + PAGINA.replace(" ", "_"),
        "atualizado_em": agora.date().isoformat(), "conferido_em": agora.strftime("%Y-%m-%d %H:%M"),
        "primeiro_turno_ultima_por_instituto": sorted(primeiro.values(), key=lambda p: p["fim"], reverse=True),
        "segundo_turno": sorted(segundo + [{**e, "fonte": "extra"} for e in extras], key=lambda p: p["fim"], reverse=True),
        "segundo_turno_extras": extras,
    }
    caminho.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"RN: {len(segundo)} pesquisas de 2º turno, {len(primeiro)} institutos no 1º turno")

    base = json.loads((RAIZ / "dados" / "rn" / "primeiro-turno-mun.json").read_text(encoding="utf-8"))
    boletins_rn = RAIZ / "dados" / "rn" / "boletins.json"
    dados = {"pesquisas": saida, "primeiro_turno": base,
             "boletins": json.loads(boletins_rn.read_text(encoding="utf-8"))["boletins"] if boletins_rn.exists() else []}
    (RAIZ / "painel" / "dados-rn.js").write_text("window.DADOS_RN = " + json.dumps(dados, ensure_ascii=False) + ";\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
