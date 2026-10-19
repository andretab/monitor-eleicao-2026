"""Resume o 1º turno para governador do RN, município a município, em dados/rn/primeiro-turno-mun.json.

Fontes:
  dados/rn/tse-1t/<cd>.json   TSE, eleição 6259 (estadual 1º turno), cargo 3, um arquivo por município
  dados/rn/tse-1t/rn.json     TSE, total do estado
  dados/rn/municipios-tse.json   lista de municípios do TSE (código TSE → código IBGE)
  dados/rn/municipios-ibge.json  IBGE /localidades: mesorregião de cada município

Candidato A = Cadu (13, PT); candidato B = Allyson (44, União). Os demais (Álvaro Dias, 22, PL, e
os nanicos) vão em "outros" — são esses votos que decidem o 2º turno.
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
D = RAIZ / "dados" / "rn"
NUM_A, NUM_B, NUM_3 = "13", "44", "22"
REGIAO = {"Leste Potiguar": "Leste", "Agreste Potiguar": "Agreste", "Central Potiguar": "Central", "Oeste Potiguar": "Oeste"}


def votos(d):
    out = {}
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                out[c["n"]] = int(c["vap"] or 0)
    return out


def resumo(d, nome, ibge, regiao):
    v = votos(d)
    validos = int(d["v"]["vv"])
    return {"nome": nome, "ibge": ibge, "regiao": regiao, "secoes": int(d["s"]["ts"]), "eleitorado": int(d["e"]["te"]),
            "comparecimento": int(d["e"]["c"]), "validos": validos, "a": v.get(NUM_A, 0), "b": v.get(NUM_B, 0),
            "terceiro": v.get(NUM_3, 0), "outros": validos - v.get(NUM_A, 0) - v.get(NUM_B, 0)}


mus = json.loads((D / "municipios-tse.json").read_text(encoding="utf-8"))
ibge = {str(m["id"]): REGIAO[m["microrregiao"]["mesorregiao"]["nome"]]
        for m in json.loads((D / "municipios-ibge.json").read_text(encoding="utf-8"))}
saida = {"_leia": "a = Cadu (13, PT); b = Allyson (44, União); terceiro = Álvaro Dias (22, PL); outros = todos menos a e b.",
         "candidatos": {"a": {"numero": NUM_A, "nome": "Cadu", "partido": "PT"}, "b": {"numero": NUM_B, "nome": "Allyson", "partido": "União"},
                        "terceiro": {"numero": NUM_3, "nome": "Álvaro Dias", "partido": "PL"}},
         "estado": resumo(json.loads((D / "tse-1t" / "rn.json").read_text(encoding="utf-8")), "Rio Grande do Norte", "24", "RN"),
         "municipios": {}}
for m in mus:
    d = json.loads((D / "tse-1t" / f"{m['cd']}.json").read_text(encoding="utf-8"))
    nome = m["nm"].title().replace(" Do ", " do ").replace(" Da ", " da ").replace(" De ", " de ").replace(" Dos ", " dos ").replace(" Das ", " das ")
    saida["municipios"][m["cd"]] = resumo(d, nome, m["cdi"], ibge[m["cdi"]])

(D / "primeiro-turno-mun.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
# Conferência: a soma dos municípios tem de bater com o total do estado no TSE.
for campo in ("validos", "a", "b", "terceiro"):
    soma = sum(r[campo] for r in saida["municipios"].values())
    print(f"{campo:9} soma={soma:>9,} estado={saida['estado'][campo]:>9,} {'OK' if soma == saida['estado'][campo] else 'DIVERGE'}")
