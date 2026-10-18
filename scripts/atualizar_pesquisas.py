"""Atualiza as pesquisas do 2º turno lendo a compilação da Wikipédia e regenera painel/dados.js.

Roda sozinho no GitHub Actions a cada 3 horas (.github/workflows/pesquisas.yml).
A seção é achada pelo título (Segundo turno > Lula e Flávio Bolsonaro > 2026), não pelo número,
porque os editores da página mudam a numeração. Se a leitura vier estranha (menos pesquisas do que
já temos), o arquivo não é tocado: melhor um dado de 3 horas atrás do que um dado quebrado.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import lxml.html

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = "Pesquisas_de_opinião_para_a_eleição_presidencial_no_Brasil_em_2026"
API = "https://pt.wikipedia.org/w/api.php"
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
PRIMEIRO_TURNO = date(2026, 10, 4)
ANO = 2026
# Mesma empresa, grafias diferentes na Wikipédia. A correção por instituto casa pelo nome do 1º turno.
APELIDOS = {"datafolha": "Datafolha", "btg/nexus": "Nexus/BTG", "nexus/btg pactual": "Nexus/BTG",
            "genial/quaest": "Quaest", "vox brasil": "Vox", "apex/futura": "Futura", "futura/apex": "Futura",
            "indexa/broadcast": "Indexa"}


def api(**params) -> dict:
    url = API + "?" + urllib.parse.urlencode({"format": "json", "formatversion": 2, "page": PAGINA, **params})
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-eleicao-2026 (github.com/andretab)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def secao_segundo_turno() -> str:
    secoes = api(action="parse", prop="sections")["parse"]["sections"]
    fase = 0
    for s in secoes:
        linha = re.sub("<.*?>", "", s["line"]).strip()
        if fase == 0 and linha == "Segundo turno":
            fase = 1
        elif fase == 1 and "Flávio" in linha:
            fase = 2
        elif fase == 2 and linha == str(ANO):
            return s["index"]
    raise RuntimeError("seção do 2º turno não encontrada — a página mudou de estrutura")


def numero(txt: str) -> float | None:
    txt = txt.replace("±", "").replace("%", "").replace(" ", "").replace(" ", "").strip()
    if not re.search(r"\d", txt):
        return None
    return float(txt.replace(".", "").replace(",", "."))


def datas(txt: str) -> tuple[str, str]:
    """'28 Set – 1 Out' / '1 – 3 Out' / '3 Out' → (início, fim) ISO. Dia sem mês herda o mês seguinte."""
    pares = re.findall(r"(\d{1,2})\s*([A-Za-zçÇ]{3})?", txt)
    dias, mes_seguinte = [], None
    for d, m in reversed(pares):
        mes = MESES.get(m.lower()[:3]) if m else mes_seguinte
        mes_seguinte = mes
        dias.append(date(ANO, mes, int(d)))
    dias.reverse()
    return dias[0].isoformat(), dias[-1].isoformat()


def ler_tabela(html: str) -> tuple[list[dict], list[dict]]:
    doc = lxml.html.fromstring(html)
    divulgadas, pendentes, vistos = [], [], set()
    for tr in doc.xpath("//table[contains(@class,'wikitable')][1]//tr"):
        tds = [re.sub(r"\[[^\]]*\]", "", td.text_content()).strip() for td in tr.xpath("./td")]
        if len(tds) < 5 or not re.search(r"\d", tds[1] if len(tds) > 1 else ""):
            continue  # cabeçalho ou linha de evento ("4 Out | Confirmado o segundo turno")
        try:
            inicio, fim = datas(tds[1])
        except (ValueError, TypeError):
            continue
        if date.fromisoformat(fim) <= PRIMEIRO_TURNO:
            continue  # cenários de 2º turno medidos antes do 1º turno ficam de fora
        tds[0] = APELIDOS.get(tds[0].lower(), tds[0])
        chave = (tds[0], inicio, fim)
        if chave in vistos:
            continue
        vistos.add(chave)
        p = {"instituto": tds[0], "inicio": inicio, "fim": fim,
             "amostra": int(numero(tds[2]) or 0), "margem": numero(tds[3])}
        if "não divulgad" in " ".join(tds[4:]).lower():
            pendentes.append(p)
            continue
        lula, flavio = numero(tds[4]), numero(tds[5])
        if lula is None or flavio is None:
            continue
        indecisos = numero(tds[6]) if len(tds) > 6 else None
        divulgadas.append({**p, "lula": lula, "flavio": flavio, "indecisos": indecisos or None})
    return divulgadas, pendentes


def main() -> int:
    caminho = RAIZ / "dados" / "pesquisas.json"
    atual = json.loads(caminho.read_text(encoding="utf-8"))
    html = api(action="parse", prop="text", section=secao_segundo_turno())["parse"]["text"]
    divulgadas, pendentes = ler_tabela(html)

    if len(divulgadas) < len(atual["segundo_turno"]) - 2:
        print(f"ABORTADO: li {len(divulgadas)} pesquisas, mas já havia {len(atual['segundo_turno'])}. Arquivo mantido.")
        return 1

    novas = {(p["instituto"], p["fim"]) for p in divulgadas} - {(p["instituto"], p["fim"]) for p in atual["segundo_turno"]}
    hoje = datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
    atual.update(segundo_turno=divulgadas, segundo_turno_a_divulgar=pendentes, atualizado_em=hoje)
    caminho.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(divulgadas)} divulgadas ({len(novas)} novas: {sorted(novas) or '-'}), {len(pendentes)} a divulgar")
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "gerar_dados_js.py")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
