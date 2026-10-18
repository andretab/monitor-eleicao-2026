"""Junta dados/*.json em painel/dados.js para o painel abrir direto do disco (file://), sem servidor.

Rodar depois de cada pesquisa nova lançada em dados/pesquisas.json.
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
dados = {
    "pesquisas": json.loads((RAIZ / "dados" / "pesquisas.json").read_text(encoding="utf-8")),
    "primeiro_turno": json.loads((RAIZ / "dados" / "primeiro-turno-uf.json").read_text(encoding="utf-8")),
    "boletins": json.loads((RAIZ / "dados" / "boletins.json").read_text(encoding="utf-8"))["boletins"],
}
(RAIZ / "painel" / "dados.js").write_text(
    "window.DADOS = " + json.dumps(dados, ensure_ascii=False) + ";\n", encoding="utf-8"
)
print("painel/dados.js gerado:", len(dados["pesquisas"]["segundo_turno"]), "pesquisas de 2º turno")
