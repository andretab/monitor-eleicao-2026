"""Resume os arquivos do TSE do 1º turno (dados/tse-1t/*.json) num JSON compacto por UF.

Fonte: https://resultados.tse.jus.br/oficial/ele2026/6257/dados/<uf>/<uf>-c0001-e006257-u.json
(eleição 6257 = presidente 1º turno; o 2º turno é 6258).
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REGIOES = {
    "N": ["ac", "am", "ap", "pa", "ro", "rr", "to"],
    "NE": ["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"],
    "CO": ["df", "go", "ms", "mt"],
    "SE": ["es", "mg", "rj", "sp"],
    "S": ["pr", "rs", "sc"],
    "EX": ["zz"],
}
REGIAO_DE = {uf: r for r, ufs in REGIOES.items() for uf in ufs}


def candidatos(d):
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                yield c["n"], c["nmu"], int(c["vap"])


def resumo(uf):
    d = json.loads((RAIZ / "dados" / "tse-1t" / f"{uf}.json").read_text(encoding="utf-8"))
    votos = {n: v for n, _, v in candidatos(d)}
    validos = int(d["v"]["vv"])
    return {
        "uf": uf,
        "regiao": REGIAO_DE.get(uf, "BR"),
        "secoes": int(d["s"]["ts"]),
        "eleitorado": int(d["e"]["te"]),
        "comparecimento": int(d["e"]["c"]),
        "validos": validos,
        "brancos": int(d["v"]["vb"]),
        "nulos": int(d["v"]["tvn"]),
        "lula": votos["13"],
        "flavio": votos["22"],
        "outros": validos - votos["13"] - votos["22"],
        "outros_detalhe": {nome: v for n, nome, v in candidatos(d) if n not in ("13", "22")} if uf == "br" else None,
        "totalizado_em": f'{d["dt"]} {d["ht"]}',
    }


ufs = ["br"] + sorted(u for r in REGIOES.values() for u in r)
saida = {r["uf"]: r for r in map(resumo, ufs)}
for r in saida.values():
    if r["outros_detalhe"] is None:
        del r["outros_detalhe"]

destino = RAIZ / "dados" / "primeiro-turno-uf.json"
destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")

# Conferência: a soma das UFs tem de bater com o total nacional do TSE.
for campo in ("validos", "lula", "flavio"):
    soma = sum(r[campo] for u, r in saida.items() if u != "br")
    print(f"{campo:8} soma UFs={soma:>11,} br={saida['br'][campo]:>11,} {'OK' if soma == saida['br'][campo] else 'DIVERGE'}")
