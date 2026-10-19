"""Compara os dados entre duas versões do repositório e, se houver novidade real, escreve o texto do alerta.

    python scripts/alerta.py <ref_antes> [<ref_depois>] > alerta.md

Novidade real = pesquisa nova no 2º turno, pesquisa que saiu da lista "a divulgar" ou boletim novo do
analista. A simples conferência de hora em hora (que só muda o horário) não gera alerta. Sem novidade,
não imprime nada; o robô então não comenta no aviso e nenhum e-mail sai.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
SITE = "https://eleicao.andrefreitas.eng.br"


def ler(ref: str, caminho: str) -> dict:
    try:
        txt = subprocess.run(["git", "show", f"{ref}:{caminho}"], cwd=RAIZ, capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout
        return json.loads(txt)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def br(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def chave(p: dict) -> tuple:
    return (p["instituto"], p["fim"])


def main() -> int:
    antes = sys.argv[1]
    depois = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    pa, pd = ler(antes, "dados/pesquisas.json"), ler(depois, "dados/pesquisas.json")
    ba, bd = ler(antes, "dados/boletins.json"), ler(depois, "dados/boletins.json")

    vistas = {chave(p) for p in pa.get("segundo_turno", [])}
    novas = [p for p in pd.get("segundo_turno", []) if chave(p) not in vistas]
    pend_antes = {chave(p) for p in pa.get("segundo_turno_a_divulgar", [])}
    pend_depois = {chave(p) for p in pd.get("segundo_turno_a_divulgar", [])}
    registradas = [p for p in pd.get("segundo_turno_a_divulgar", []) if chave(p) not in pend_antes]
    titulos_antes = {(b.get("quando"), b.get("titulo")) for b in ba.get("boletins", [])}
    boletins = [b for b in bd.get("boletins", []) if (b.get("quando"), b.get("titulo")) not in titulos_antes]

    ra, rd = ler(antes, "dados/rn/pesquisas.json"), ler(depois, "dados/rn/pesquisas.json")
    vistas_rn = {chave(p) for p in ra.get("segundo_turno", [])}
    novas_rn = [p for p in rd.get("segundo_turno", []) if chave(p) not in vistas_rn]

    bra, brd = ler(antes, "dados/rn/boletins.json"), ler(depois, "dados/rn/boletins.json")
    tit_rn = {(b.get("quando"), b.get("titulo")) for b in bra.get("boletins", [])}
    boletins_rn = [b for b in brd.get("boletins", []) if (b.get("quando"), b.get("titulo")) not in tit_rn]

    if not (novas or registradas or boletins or novas_rn or boletins_rn):
        return 0

    linhas = ["@andretab novidade no Monitor Eleição 2026:", ""]
    if novas:
        linhas.append(f"**{len(novas)} pesquisa(s) nova(s) do 2º turno**")
        for p in sorted(novas, key=lambda p: p["fim"], reverse=True):
            tot = p["lula"] + p["flavio"]
            linhas.append(f"- {p['instituto']} ({p['inicio'][8:10]}/{p['inicio'][5:7]}–{p['fim'][8:10]}/{p['fim'][5:7]}): "
                          f"Lula {br(p['lula'])}% × Flávio {br(p['flavio'])}% · válidos {br(100 * p['lula'] / tot)}% × {br(100 * p['flavio'] / tot)}%"
                          + (" · achada pelo analista" if p.get("fonte") == "extra" else ""))
        try:  # média atualizada, com as mesmas contas do site
            from estatisticas import pesquisas
            m = pesquisas()["medias_2t"]
            linhas += ["", f"Média como divulgada: Lula {br(m['bruta']['lula'])}% × Flávio {br(m['bruta']['flavio'])}% · "
                           f"corrigida: Lula {br(m['instituto']['lula'])}% × Flávio {br(m['instituto']['flavio'])}% "
                           f"(chance estimada de Flávio {100 * m['instituto']['chance_flavio']:.0f}%)"]
        except Exception:
            pass
        linhas.append("")
    if registradas:
        linhas.append(f"**{len(registradas)} pesquisa(s) nova(s) registrada(s) no TSE, a divulgar:** "
                      + ", ".join(f"{p['instituto']} (campo até {p['fim'][8:10]}/{p['fim'][5:7]})" for p in registradas))
        linhas.append("")
    if novas_rn:
        linhas.append(f"**RN · {len(novas_rn)} pesquisa(s) nova(s) para governador (Cadu × Allyson)**")
        for p in sorted(novas_rn, key=lambda p: p["fim"], reverse=True):
            tot = p["a"] + p["b"]
            linhas.append(f"- {p['instituto']} ({p['inicio'][8:10]}/{p['inicio'][5:7]}–{p['fim'][8:10]}/{p['fim'][5:7]}): "
                          f"Cadu {br(p['a'])}% × Allyson {br(p['b'])}% · válidos {br(100 * p['a'] / tot)}% × {br(100 * p['b'] / tot)}%")
        linhas.append(f"Ver o RN: {SITE}/painel/rn.html")
        linhas.append("")
    for b in boletins:
        linhas.append(f"**Boletim do analista ({b.get('quando', '').replace('T', ' ')}):** {b.get('titulo', '')}")
        if b.get("paragrafos"):
            linhas.append(f"> {b['paragrafos'][0]}")
        linhas.append("")
    for b in boletins_rn:
        linhas.append(f"**Boletim do RN ({b.get('quando', '').replace('T', ' ')}):** {b.get('titulo', '')}")
        if b.get("paragrafos"):
            linhas.append(f"> {b['paragrafos'][0]}")
        linhas.append("")
    linhas.append(f"Ver no site: {SITE}")
    print("\n".join(linhas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
