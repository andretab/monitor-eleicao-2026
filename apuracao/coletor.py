"""Lê a apuração em ciclos, projeta o resultado e escreve o que o painel mostra.

Noite real (25/10, a partir das 17h de Brasília):
    python apuracao/coletor.py

Ensaio com noite simulada (1 segundo real = 1 minuto de apuração):
    python apuracao/coletor.py --simular
    python apuracao/coletor.py --simular --sim-swing -0.02 --velocidade 5

Saídas: apuracao/estado.json e painel/apuracao-dados.js (o painel recarrega sozinho).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fontes import FonteSimulada, FonteTSE  # noqa: E402
from modelo import prever_virada, projetar, ritmos  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BRASILIA = timezone(timedelta(hours=-3))
FECHAMENTO = (17, 0)  # urnas fecham às 17h de Brasília em todo o país
NOMES_REGIAO = {"N": "Norte", "NE": "Nordeste", "CO": "Centro-Oeste", "SE": "Sudeste", "S": "Sul", "EX": "Exterior"}


def hora_de(minuto: float) -> str:
    base = datetime(2026, 10, 25, *FECHAMENTO)
    return (base + timedelta(minutes=minuto)).strftime("%H:%M")


def minuto_agora() -> float:
    agora = datetime.now(BRASILIA)
    return (agora - agora.replace(hour=FECHAMENTO[0], minute=FECHAMENTO[1], second=0, microsecond=0)).total_seconds() / 60


def montar_estado(proj, virada, saida_hist, modo, transferencia, minuto, sim_real=None) -> dict:
    regioes = {}
    for p in proj.ufs:
        r = regioes.setdefault(p.regiao, {"regiao": NOMES_REGIAO[p.regiao], "lula": 0, "flavio": 0, "proj_lula": 0.0,
                                          "proj_flavio": 0.0, "votos_rest": 0.0})
        for k in ("lula", "flavio", "proj_lula", "proj_flavio", "votos_rest"):
            r[k] += getattr(p, k)
    estado = {
        "modo": modo,
        "gerado_em": datetime.now(BRASILIA).strftime("%d/%m %H:%M:%S"),
        "hora_apuracao": hora_de(minuto),
        "transferencia_prior": transferencia,
        "fracao_secoes": proj.fracao_secoes,
        "lula": proj.lula, "flavio": proj.flavio,
        "proj_lula": proj.proj_lula, "proj_flavio": proj.proj_flavio,
        "desvio_margem": proj.desvio_margem, "chance_lula": proj.chance_lula, "swing": proj.swing,
        "virada": {k: v for k, v in virada.items() if k != "curva"},
        "curva_futura": virada["curva"],
        "historico": saida_hist,
        "ufs": [asdict(p) for p in sorted(proj.ufs, key=lambda p: -(p.proj_lula + p.proj_flavio))],
        "regioes": list(regioes.values()),
        # Referência de imprensa (conferir): em 2022, no 2º turno, Lula passou Bolsonaro com ~67,8% das seções.
        "referencia_2022": {"fracao_virada": 0.678, "hora": "18:44"},
    }
    if sim_real:
        estado["sim_resultado_real"] = {"lula": sim_real[0], "flavio": sim_real[1]}
    return estado


def gravar(estado: dict) -> None:
    texto = json.dumps(estado, ensure_ascii=False)
    (RAIZ / "apuracao" / "estado.json").write_text(texto, encoding="utf-8")
    tmp = RAIZ / "painel" / "apuracao-dados.js.tmp"
    tmp.write_text("window.APURACAO = " + texto + ";\n", encoding="utf-8")
    tmp.replace(RAIZ / "painel" / "apuracao-dados.js")  # troca atômica: o painel nunca lê arquivo pela metade


def publicar(texto: str) -> None:
    """Põe o estado.json num commit avulso e força o ramo 'ao-vivo' para ele.

    Avulso (sem histórico) de propósito: são centenas de atualizações na noite e só a última importa.
    Feito por comandos de baixo nível do git para não tocar no diretório de trabalho.
    """
    git = lambda *a, entrada=None: subprocess.run(["git", *a], cwd=RAIZ, input=entrada, capture_output=True,
                                                  text=True, check=True).stdout.strip()
    try:
        blob = git("hash-object", "-w", "--stdin", entrada=texto)
        # -z (registro terminado em \0): no Windows o modo texto troca \n por \r\n e o nome viraria "estado.json\r".
        arvore = git("mktree", "-z", entrada=f"100644 blob {blob}\testado.json\0")
        commit = git("-c", "user.name=monitor-eleicao", "-c", "user.email=monitor@users.noreply.github.com",
                     "commit-tree", arvore, "-m", "apuração ao vivo")
        git("push", "--force", "--quiet", "origin", f"{commit}:refs/heads/ao-vivo")
    except subprocess.CalledProcessError as e:  # sem rede ou sem permissão: a noite continua, tenta no próximo ciclo
        print("  publicação falhou:", (e.stderr or "").strip()[:200])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true", help="noite simulada em vez do TSE")
    ap.add_argument("--velocidade", type=float, default=1.0, help="simulação: minutos de apuração por segundo real")
    ap.add_argument("--intervalo", type=float, default=60, help="TSE: segundos entre leituras")
    ap.add_argument("--transferencia", type=float, default=0.5,
                    help="prior: fração dos votos dos demais candidatos do 1º turno que vai para Lula")
    ap.add_argument("--sim-transferencia", type=float, default=0.45)
    ap.add_argument("--sim-swing", type=float, default=0.0)
    ap.add_argument("--sim-vies-capital", type=float, default=-0.04)
    ap.add_argument("--ate", type=float, help="simulação: para neste minuto após as 17h (para ver o meio da noite)")
    ap.add_argument("--publicar", action="store_true", help="envia cada atualização ao ramo ao-vivo do GitHub")
    ap.add_argument("--uma-vez", action="store_true", help="faz uma leitura e sai")
    a = ap.parse_args()

    base = json.loads((RAIZ / "dados" / "primeiro-turno-uf.json").read_text(encoding="utf-8"))
    if a.simular:
        fonte = FonteSimulada(base, a.sim_transferencia, a.sim_swing, a.sim_vies_capital)
        modo, minuto = "simulacao", 0.0
    else:
        fonte = FonteTSE([u for u in base if u != "br"], RAIZ / "apuracao" / "bruto-2t")
        modo, minuto = "tse", minuto_agora()

    historico, minutos, saida_hist = [], [], []
    while True:
        leituras = fonte.ler(minuto)
        if leituras:
            historico.append(leituras)
            minutos.append(minuto)
            proj = projetar(leituras, base, a.transferencia)
            virada = prever_virada(proj, leituras, ritmos(historico, minutos))
            saida_hist.append({"min": round(minuto, 1), "hora": hora_de(minuto), "fracao_secoes": proj.fracao_secoes,
                               "margem_placar": proj.lula - proj.flavio, "margem_proj": proj.proj_lula - proj.proj_flavio,
                               "chance_lula": proj.chance_lula,
                               "virada_prevista_fracao": virada.get("fracao_secoes"),
                               "virada_prevista_hora": hora_de(minuto + virada["minutos_ate"]) if "minutos_ate" in virada else None})
            estado = montar_estado(proj, virada, saida_hist, modo, a.transferencia, minuto,
                                   fonte.resultado_real() if a.simular else None)
            gravar(estado)
            if a.publicar:
                publicar(json.dumps(estado, ensure_ascii=False))
            tot = proj.proj_lula + proj.proj_flavio
            print(f"{hora_de(minuto)}  seções {100 * proj.fracao_secoes:5.1f}%  placar L {100 * proj.lula / max(proj.lula + proj.flavio, 1):5.2f}%"
                  f"  projeção L {100 * proj.proj_lula / tot:5.2f}%  chance L {100 * proj.chance_lula:3.0f}%")
            if proj.fracao_secoes >= 1:
                print("Apuração concluída.")
                break
        elif not a.simular:
            print(f"{datetime.now(BRASILIA):%H:%M}  TSE ainda sem arquivos do 2º turno; aguardando")
        if a.uma_vez:
            break
        if a.simular:
            if a.ate is not None and minuto >= a.ate:
                break
            minuto += 1
            time.sleep(1 / a.velocidade)
        else:
            time.sleep(a.intervalo)
            minuto = minuto_agora()


if __name__ == "__main__":
    main()
