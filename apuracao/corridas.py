"""As disputas que o coletor acompanha. Cada uma diz de onde vêm os arquivos do TSE, quem são os dois
candidatos, qual é a base do 1º turno e para onde vão as saídas.

O modelo trabalha com "unidades" (UFs no presidente, municípios no RN) e com dois candidatos nos campos
lula/flavio, nomes herdados da primeira versão: no RN, lula = Cadu (13) e flavio = Allyson (44).
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE_TSE = "https://resultados.tse.jus.br/oficial/ele2026"


def _base_presidente() -> tuple[dict, dict]:
    base = json.loads((RAIZ / "dados" / "primeiro-turno-uf.json").read_text(encoding="utf-8"))
    base = {u: b for u, b in base.items() if u != "br"}
    return base, {}


def _base_rn() -> tuple[dict, dict]:
    d = json.loads((RAIZ / "dados" / "rn" / "primeiro-turno-mun.json").read_text(encoding="utf-8"))
    base = {cd: {**m, "lula": m["a"], "flavio": m["b"]} for cd, m in d["municipios"].items()}
    unidades = {cd: {"nome": m["nome"], "mapa": m["ibge"]} for cd, m in d["municipios"].items()}
    return base, unidades


CORRIDAS = {
    "presidente": {
        "titulo": "Presidente",
        "url": lambda u: f"{BASE_TSE}/6258/dados/{u}/{u}-c0001-e006258-u.json",
        "num_a": "13", "num_b": "22",
        "candidatos": {"a": "Lula", "b": "Flávio"},
        "carregar_base": _base_presidente,
        "nomes_regiao": {"N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste", "SE": "Sudeste", "S": "Sul", "EX": "Exterior"},
        "regioes_lentas": ("N", "NE"),  # padrão conhecido: totalizam por último
        "unidade": "estado",
        "estado_json": "apuracao/estado.json", "painel_js": "painel/apuracao-dados.js", "variavel_js": "APURACAO",
        "ramo": "ao-vivo", "bruto": "apuracao/bruto-2t",
        "referencia_2022": {"fracao_virada": 0.678, "hora": "18:44"},
    },
    "rn": {
        "titulo": "Governador do RN",
        "url": lambda cd: f"{BASE_TSE}/6260/dados/rn/rn{cd}-c0003-e006260-u.json",
        "num_a": "13", "num_b": "44",
        "candidatos": {"a": "Cadu", "b": "Allyson"},
        "carregar_base": _base_rn,
        "nomes_regiao": {},  # já vêm por extenso (Leste, Agreste, Central, Oeste)
        "regioes_lentas": (),  # sem padrão de atraso conhecido entre as regiões do RN
        "unidade": "município",
        "estado_json": "apuracao/estado-rn.json", "painel_js": "painel/apuracao-rn-dados.js", "variavel_js": "APURACAO_RN",
        "ramo": "ao-vivo-rn", "bruto": "apuracao/bruto-2t-rn",
        "referencia_2022": None,
    },
}
