"""Converte a malha dos estados do IBGE (GeoJSON) em painel/mapa-br.js: um caminho SVG por UF, já projetado.

Fonte: API de malhas do IBGE (qualidade mínima, divisão por UF)
  https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=UF
  https://servicodados.ibge.gov.br/api/v1/localidades/estados (código IBGE → sigla)

    python scripts/gerar_mapa.py <malha.json> <estados.json>       # Brasil por UF → painel/mapa-br.js
    python scripts/gerar_mapa.py --rn <malha-municipios-rn.json>   # RN por município → painel/mapa-rn.js
      (malha: .../api/v3/malhas/estados/24?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio)

Projeção equiretangular com a longitude encolhida por cos(latitude central): no recorte do Brasil
(15°S) ou do RN (5,8°S) a distorção é pequena e o desenho fica reconhecível sem biblioteca de mapas.
"""
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LARGURA = 1000


def aneis(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]  # MultiPolygon


def main(malha, estados=None, destino="mapa-br.js", variavel="MAPA_BR", lat_central=15, fonte="IBGE, malha de UFs (qualidade mínima)"):
    FATOR_LON = math.cos(math.radians(lat_central))
    g = json.loads(Path(malha).read_text(encoding="utf-8"))
    # Chave de cada área: sigla da UF (Brasil) ou o próprio código IBGE do município (RN).
    sigla = {str(e["id"]): e["sigla"].lower() for e in json.loads(Path(estados).read_text(encoding="utf-8"))} if estados else None
    pontos = [(lon * FATOR_LON, -lat) for f in g["features"] for poli in aneis(f["geometry"]) for anel in poli for lon, lat in anel]
    x0, x1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    y0, y1 = min(p[1] for p in pontos), max(p[1] for p in pontos)
    esc = LARGURA / (x1 - x0)
    altura = round((y1 - y0) * esc)
    xy = lambda lon, lat: (round((lon * FATOR_LON - x0) * esc, 1), round((-lat - y0) * esc, 1))

    ufs = {}
    for f in g["features"]:
        uf = sigla[f["properties"]["codarea"]] if sigla else f["properties"]["codarea"]
        partes, maior, area_maior = [], None, -1
        for poli in aneis(f["geometry"]):
            for k, anel in enumerate(poli):
                pts = [xy(lon, lat) for lon, lat in anel]
                partes.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts) + "Z")
                if k == 0:  # contorno externo: o maior polígono dá o centro do rótulo
                    a = sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1)) / 2
                    if abs(a) > area_maior:
                        area_maior, maior = abs(a), (pts, a)
        pts, a = maior
        cx = sum((pts[i][0] + pts[i + 1][0]) * (pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]) for i in range(len(pts) - 1)) / (6 * a)
        cy = sum((pts[i][1] + pts[i + 1][1]) * (pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]) for i in range(len(pts) - 1)) / (6 * a)
        ufs[uf] = {"d": "".join(partes), "cx": round(cx, 1), "cy": round(cy, 1), "area": round(area_maior)}

    saida = {"largura": LARGURA, "altura": altura, "fonte": fonte, "ufs": ufs}
    caminho = RAIZ / "painel" / destino
    caminho.write_text(f"window.{variavel} = " + json.dumps(saida, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{len(ufs)} áreas, {LARGURA}x{altura}, {caminho.stat().st_size // 1024} KB -> {destino}")


if __name__ == "__main__":
    if sys.argv[1] == "--rn":
        main(sys.argv[2], None, "mapa-rn.js", "MAPA_RN", 5.8, "IBGE, malha de municípios do RN (qualidade mínima)")
    else:
        main(*sys.argv[1:3])
