"""Lê a apuração em ciclos, projeta o resultado e escreve o que o painel mostra.

Noite real (25/10, a partir das 17h de Brasília):
    python apuracao/coletor.py                    # presidente
    python apuracao/coletor.py --corrida rn       # governador do RN (Cadu × Allyson)

Ensaio com noite simulada (1 segundo real = 1 minuto de apuração):
    python apuracao/coletor.py --simular
    python apuracao/coletor.py --simular --sim-swing -0.02 --velocidade 5

Saídas (ver apuracao/corridas.py): presidente → apuracao/estado.json e painel/apuracao-dados.js;
RN → apuracao/estado-rn.json e painel/apuracao-rn-dados.js. O painel recarrega sozinho.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corridas import CORRIDAS  # noqa: E402
from fontes import FonteSimulada, FonteTSE  # noqa: E402
from modelo import prever_virada, projetar, ritmos, simular_viradas  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BRASILIA = timezone(timedelta(hours=-3))
FECHAMENTO = (17, 0)  # urnas fecham às 17h de Brasília em todo o país


def hora_de(minuto: float) -> str:
    base = datetime(2026, 10, 25, *FECHAMENTO)
    return (base + timedelta(minutes=minuto)).strftime("%H:%M")


def minuto_agora() -> float:
    agora = datetime.now(BRASILIA)
    return (agora - agora.replace(hour=FECHAMENTO[0], minute=FECHAMENTO[1], second=0, microsecond=0)).total_seconds() / 60


def resumir_viradas(mc: dict, minuto: float) -> dict:
    """Probabilidade de o placar virar e, se virar, de cada faixa de 15 minutos (hora de Brasília)."""
    out = {k: mc[k] for k in ("n", "prob_lula_vence", "prob_troca", "lider_placar")}
    out["ritmo_medido"] = mc.get("ritmo_medido", False)
    ms, fr = mc["minutos"], mc["fracoes"]
    if not ms:
        return out
    faixas = {}
    for m in ms:
        ini = int((minuto + m) // 15 * 15)
        faixas[ini] = faixas.get(ini, 0) + 1
    out["faixas"] = [{"de": hora_de(k), "ate": hora_de(k + 15), "prob": v / mc["n"]} for k, v in sorted(faixas.items())]
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
    out["hora_p10"], out["hora_p50"], out["hora_p90"] = (hora_de(minuto + q(ms, f)) for f in (.1, .5, .9))
    out["fracao_p10"], out["fracao_p50"], out["fracao_p90"] = (q(fr, f) for f in (.1, .5, .9))
    mais = max(out["faixas"], key=lambda f: f["prob"])
    out["faixa_mais_provavel"] = mais
    return out


def montar_estado(cfg, unidades, proj, virada, saida_hist, modo, transferencia, minuto, sim_real=None, prob_virada=None) -> dict:
    regioes = {}
    for p in proj.ufs:
        r = regioes.setdefault(p.regiao, {"regiao": cfg["nomes_regiao"].get(p.regiao, p.regiao), "lula": 0, "flavio": 0, "proj_lula": 0.0,
                                          "proj_flavio": 0.0, "votos_rest": 0.0})
        for k in ("lula", "flavio", "proj_lula", "proj_flavio", "votos_rest"):
            r[k] += getattr(p, k)
    estado = {
        "corrida": cfg["titulo"], "candidatos": cfg["candidatos"], "rotulo_unidade": cfg["unidade"],
        "modo": modo,
        "gerado_em": datetime.now(BRASILIA).strftime("%d/%m %H:%M:%S"),
        "gerado_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origem": ORIGEM,
        "hora_apuracao": hora_de(minuto),
        "transferencia_prior": transferencia,
        "fracao_secoes": proj.fracao_secoes,
        "lula": proj.lula, "flavio": proj.flavio,
        "proj_lula": proj.proj_lula, "proj_flavio": proj.proj_flavio,
        "desvio_margem": proj.desvio_margem, "chance_lula": proj.chance_lula, "swing": proj.swing,
        "virada": {k: v for k, v in virada.items() if k != "curva"},
        "probabilidade_virada": prob_virada,
        "curva_futura": virada["curva"],
        "historico": saida_hist,
        "ufs": [asdict(p) for p in sorted(proj.ufs, key=lambda p: -(p.proj_lula + p.proj_flavio))],
        "regioes": list(regioes.values()),
        # Presidente: referência de imprensa (conferir) — em 2022 Lula passou Bolsonaro com ~67,8% das seções.
        "referencia_2022": cfg["referencia_2022"],
    }
    if unidades:  # RN: nome do município e chave no mapa (código IBGE)
        estado["unidades"] = unidades
    if sim_real:
        estado["sim_resultado_real"] = {"lula": sim_real[0], "flavio": sim_real[1]}
    return estado


def gravar(cfg, estado: dict) -> None:
    texto = json.dumps(estado, ensure_ascii=False)
    (RAIZ / cfg["estado_json"]).write_text(texto, encoding="utf-8")
    destino = RAIZ / cfg["painel_js"]
    tmp = destino.with_suffix(".js.tmp")
    tmp.write_text(f"window.{cfg['variavel_js']} = " + texto + ";\n", encoding="utf-8")
    # Troca atômica: o painel nunca lê arquivo pela metade. No Windows a troca falha se o servidor local
    # estiver lendo o arquivo naquele instante; tenta de novo e, em último caso, pula este ciclo.
    for tentativa in range(5):
        try:
            tmp.replace(destino)
            return
        except PermissionError:
            time.sleep(0.2 * (tentativa + 1))
    print("  painel local não atualizado neste ciclo (arquivo em uso)")


# Quem está publicando: o robô do GitHub ou o reserva no PC. O reserva só publica se o do GitHub parar.
ORIGEM = "github" if os.environ.get("GITHUB_ACTIONS") else "pc"
LIMITE_SILENCIO_S = 240  # 4 min sem atualização do GitHub = ele parou; o PC assume


def github_em_dia(ramo: str) -> tuple[bool, str]:
    """O estado publicado no ramo veio do GitHub e tem menos de 4 minutos?"""
    r = subprocess.run(["git", "fetch", "-q", "origin", ramo], cwd=RAIZ, capture_output=True, text=True)
    if r.returncode != 0:
        return False, "ramo ainda não existe"
    txt = subprocess.run(["git", "show", "FETCH_HEAD:estado.json"], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8").stdout
    try:
        e = json.loads(txt)
    except json.JSONDecodeError:
        return False, "estado ilegível"
    if e.get("origem") != "github" or not e.get("gerado_iso"):
        return False, f"último estado veio de: {e.get('origem', 'desconhecido')}"
    idade = (datetime.now(timezone.utc) - datetime.fromisoformat(e["gerado_iso"])).total_seconds()
    return idade < LIMITE_SILENCIO_S, f"GitHub publicou há {idade:.0f}s"


def manter_acordado() -> None:
    """No Windows, impede a suspensão enquanto o coletor roda (vale só para este processo)."""
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def publicar(texto: str, ramo: str = "ao-vivo") -> None:
    """Põe o estado.json num commit avulso e força o ramo (ao-vivo ou ao-vivo-rn) para ele.

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
        git("push", "--force", "--quiet", "origin", f"{commit}:refs/heads/{ramo}")
    except subprocess.CalledProcessError as e:  # sem rede ou sem permissão: a noite continua, tenta no próximo ciclo
        print("  publicação falhou:", (e.stderr or "").strip()[:200])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrida", choices=sorted(CORRIDAS), default="presidente")
    ap.add_argument("--simular", action="store_true", help="noite simulada em vez do TSE")
    ap.add_argument("--velocidade", type=float, default=1.0, help="simulação: minutos de apuração por segundo real")
    ap.add_argument("--intervalo", type=float, default=60, help="TSE: segundos entre leituras")
    ap.add_argument("--transferencia", type=float, default=0.5,
                    help="prior: fração dos votos dos demais candidatos do 1º turno que vai para o candidato A")
    ap.add_argument("--sim-transferencia", type=float, default=0.45)
    ap.add_argument("--sim-swing", type=float, default=0.0)
    ap.add_argument("--sim-vies-capital", type=float, default=-0.04)
    ap.add_argument("--ate", type=float, help="simulação: para neste minuto após as 17h (para ver o meio da noite)")
    ap.add_argument("--publicar", action="store_true", help="envia cada atualização ao ramo ao-vivo do GitHub")
    ap.add_argument("--reserva", action="store_true",
                    help="robô reserva (PC): só publica se o robô do GitHub ficar mais de 4 min sem publicar")
    ap.add_argument("--uma-vez", action="store_true", help="faz uma leitura e sai")
    a = ap.parse_args()

    cfg = CORRIDAS[a.corrida]
    manter_acordado()
    base, unidades = cfg["carregar_base"]()
    if a.simular:
        fonte = FonteSimulada(base, a.sim_transferencia, a.sim_swing, a.sim_vies_capital, regioes_lentas=cfg["regioes_lentas"])
        modo, minuto = "simulacao", 0.0
    else:
        fonte = FonteTSE(list(base), RAIZ / cfg["bruto"], cfg["url"], cfg["num_a"], cfg["num_b"])
        modo, minuto = "tse", minuto_agora()

    historico, minutos, saida_hist = [], [], []
    while True:
        leituras = fonte.ler(minuto)
        if leituras:
            historico.append(leituras)
            minutos.append(minuto)
            proj = projetar(leituras, base, a.transferencia)
            rit = ritmos(historico, minutos)
            virada = prever_virada(proj, leituras, rit)
            prob_virada = resumir_viradas(simular_viradas(proj, leituras, rit, semente=int(minuto), regioes_lentas=cfg["regioes_lentas"]), minuto)
            saida_hist.append({"min": round(minuto, 1), "hora": hora_de(minuto), "fracao_secoes": proj.fracao_secoes,
                               "margem_placar": proj.lula - proj.flavio, "margem_proj": proj.proj_lula - proj.proj_flavio,
                               "chance_lula": proj.chance_lula,
                               "prob_troca": prob_virada["prob_troca"],
                               "virada_prevista_fracao": virada.get("fracao_secoes"),
                               "virada_prevista_hora": hora_de(minuto + virada["minutos_ate"]) if "minutos_ate" in virada else None})
            estado = montar_estado(cfg, unidades, proj, virada, saida_hist, modo, a.transferencia, minuto,
                                   fonte.resultado_real() if a.simular else None, prob_virada)
            gravar(cfg, estado)
            if a.publicar and a.reserva:
                em_dia, motivo = github_em_dia(cfg["ramo"])
                if em_dia:
                    print(f"  reserva: {motivo}; não publico")
                else:
                    print(f"  reserva ASSUMIU ({motivo}); publicando do PC")
                    publicar(json.dumps(estado, ensure_ascii=False), cfg["ramo"])
            elif a.publicar:
                publicar(json.dumps(estado, ensure_ascii=False), cfg["ramo"])
            tot = proj.proj_lula + proj.proj_flavio
            ca = cfg["candidatos"]["a"]
            print(f"{hora_de(minuto)}  seções {100 * proj.fracao_secoes:5.1f}%  placar {ca} {100 * proj.lula / max(proj.lula + proj.flavio, 1):5.2f}%"
                  f"  projeção {ca} {100 * proj.proj_lula / tot:5.2f}%  chance {ca} {100 * proj.chance_lula:3.0f}%  virada {100 * prob_virada['prob_troca']:3.0f}%")
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
