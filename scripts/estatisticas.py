"""Números para os boletins, com as mesmas contas do site (painel/index.html e painel/balanco.html).

    python scripts/estatisticas.py                       # pesquisas
    python scripts/estatisticas.py --estado estado.json  # + apuração / balanço

Imprime JSON. O analista na nuvem escreve o texto a partir daqui, para que boletim e site nunca
discordem nos números.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ELEICAO = date(2026, 10, 25)


def d(s: str) -> date:
    return date.fromisoformat(s)


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def pesquisas() -> dict:
    P = json.loads((RAIZ / "dados" / "pesquisas.json").read_text(encoding="utf-8"))
    br = json.loads((RAIZ / "dados" / "primeiro-turno-uf.json").read_text(encoding="utf-8"))["br"]
    rl, rf = 100 * br["lula"] / br["validos"], 100 * br["flavio"] / br["validos"]
    mreal = rf - rl

    erro = {}
    for p in P["primeiro_turno_ultima_por_instituto"]:
        base = 100 if p["indecisos"] is None else 100 - p["indecisos"]
        erro[p["instituto"]] = (100 * p["flavio"] / base - 100 * p["lula"] / base) - mreal
    erro_medio = sum(erro.values()) / len(erro)
    desvio = math.sqrt(sum((v - erro_medio) ** 2 for v in erro.values()) / (len(erro) - 1))

    p2 = sorted(P["segundo_turno"], key=lambda p: p["fim"], reverse=True)
    for p in p2:
        p["lula_validos"] = 100 * p["lula"] / (p["lula"] + p["flavio"])
        p["margem_flavio"] = 100 - 2 * p["lula_validos"]
    ref = d(P["atualizado_em"])

    def correcao(inst, modo):
        return 0 if modo == "bruta" else -erro_medio if modo == "media" else -erro.get(inst, erro_medio)

    ultimas = {}
    for p in p2:
        ultimas.setdefault(p["instituto"], p)

    medias = {}
    for modo in ("bruta", "instituto", "media"):
        s = w = 0.0
        for p in ultimas.values():
            peso = math.sqrt(min(p["amostra"], 5000)) * math.exp(-(ref - d(p["fim"])).days / 7)
            s += peso * (p["margem_flavio"] + correcao(p["instituto"], modo))
            w += peso
        m = s / w
        medias[modo] = {"vantagem_flavio_pp": round(m, 2), "lula": round(50 - m / 2, 2), "flavio": round(50 + m / 2, 2),
                        "chance_flavio": round(phi(m / desvio), 3)}

    # Tendência: mínimos quadrados da vantagem corrigida contra o dia, últimos 10 dias.
    pts = [(-(ref - d(p["fim"])).days, p["margem_flavio"] + correcao(p["instituto"], "instituto"))
           for p in p2 if (ref - d(p["fim"])).days <= 10]
    tendencia = None
    if len(pts) >= 4:
        mx = sum(x for x, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        b = sum((x - mx) * (y - my) for x, y in pts) / sxx
        res = math.sqrt(sum((y - (my + b * (x - mx))) ** 2 for x, y in pts) / (len(pts) - 2))
        ate = (ELEICAO - ref).days
        tendencia = {"pp_por_dia_a_favor_de_flavio": round(b, 3), "ic95": round(1.96 * res / math.sqrt(sxx), 3),
                     "vantagem_flavio_hoje": round(my + b * (0 - mx), 2),
                     "vantagem_flavio_25_10_se_ritmo_seguir": round(my + b * (ate - mx), 2), "n": len(pts)}

    return {
        "atualizado_em": P["atualizado_em"],
        "primeiro_turno_real": {"lula": round(rl, 2), "flavio": round(rf, 2)},
        "erro_1t_por_instituto_vantagem_flavio": {k: round(v, 2) for k, v in sorted(erro.items(), key=lambda kv: abs(kv[1]))},
        "erro_1t_medio": round(erro_medio, 2), "desvio_erros_1t": round(desvio, 2),
        "medias_2t": medias, "tendencia": tendencia,
        "ultima_por_instituto": [{k: p[k] for k in ("instituto", "inicio", "fim", "amostra", "lula", "flavio", "indecisos")}
                                 | {"lula_validos": round(p["lula_validos"], 2), "fonte": p.get("fonte", "wikipedia")}
                                 for p in ultimas.values()],
        "a_divulgar": P.get("segundo_turno_a_divulgar", []),
        "empate_parcela_outros_para_lula": round(100 * (br["flavio"] - br["lula"] + br["outros"]) / (2 * br["outros"]), 2),
    }


def apuracao(estado: dict, pesq: dict) -> dict:
    t1 = json.loads((RAIZ / "dados" / "primeiro-turno-uf.json").read_text(encoding="utf-8"))
    L = 100 * estado["lula"] / max(estado["lula"] + estado["flavio"], 1)
    tot = estado["proj_lula"] + estado["proj_flavio"]
    h = [x for x in estado["historico"] if x["fracao_secoes"] >= 0.02]
    trocas = [b for a, b in zip(h, h[1:]) if (a["margem_placar"] > 0) != (b["margem_placar"] > 0)]
    out = {
        "modo": estado["modo"], "hora_tse": estado["hora_apuracao"], "fracao_secoes": round(estado["fracao_secoes"], 4),
        "placar_lula": round(L, 2), "projecao_lula": round(100 * estado["proj_lula"] / tot, 2),
        "chance_lula": round(estado["chance_lula"], 3), "swing_pp": round(100 * estado["swing"], 2),
        "virada": estado["virada"], "probabilidade_virada": estado.get("probabilidade_virada"), "trocas_de_lideranca": [{"hora": t["hora"], "fracao": round(t["fracao_secoes"], 3)} for t in trocas],
        "regioes": estado["regioes"],
    }
    if estado["fracao_secoes"] >= 1:
        mreal = 100 - 2 * L
        acertos = []
        for p in pesq["ultima_por_instituto"]:
            m = 100 - 2 * p["lula_validos"]
            acertos.append({"instituto": p["instituto"], "fim": p["fim"], "lula_validos": p["lula_validos"],
                            "erro_vantagem_flavio": round(m - mreal, 2), "acertou_vencedor": (m > 0) == (mreal > 0),
                            "erro_1t": pesq["erro_1t_por_instituto_vantagem_flavio"].get(p["instituto"])})
        acertos.sort(key=lambda a: abs(a["erro_vantagem_flavio"]))
        out["balanco"] = {
            "acertos_2t": acertos,
            "media_bruta_erro": round(pesq["medias_2t"]["bruta"]["vantagem_flavio_pp"] - mreal, 2),
            "media_corrigida_erro": round(pesq["medias_2t"]["instituto"]["vantagem_flavio_pp"] - mreal, 2),
            "crescimento_lula_por_uf_pp": sorted(
                [{"uf": u["uf"], "pp": round(100 * u["lula"] / max(u["lula"] + u["flavio"], 1) - 100 * t1[u["uf"]]["lula"] / t1[u["uf"]]["validos"], 2)}
                 for u in estado["ufs"]], key=lambda x: -x["pp"]),
        }
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", help="caminho do estado.json (ramo ao-vivo)")
    a = ap.parse_args()
    saida = {"pesquisas": pesquisas()}
    if a.estado:
        saida["apuracao"] = apuracao(json.loads(Path(a.estado).read_text(encoding="utf-8")), saida["pesquisas"])
    print(json.dumps(saida, ensure_ascii=False, indent=1))
