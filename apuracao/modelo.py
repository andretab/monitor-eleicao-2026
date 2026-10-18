"""Projeção do resultado final a partir da apuração parcial, UF por UF.

Por que por UF: a ordem de chegada das seções não é aleatória. Sul, Sudeste e Centro-Oeste costumam
totalizar antes do Norte e do Nordeste. Somar o placar nacional parcial engana; projetar cada UF com
o seu próprio padrão de voto e somar não.

Para cada UF:
  prior        = participação esperada de Lula antes de abrir urna: votos dele no 1º turno + uma
                 fração dos votos dos demais candidatos (config 'transferencia_outros_para_lula').
  observado    = participação de Lula no que já foi apurado na UF.
  swing        = quanto o país inteiro está se afastando do prior (média ponderada das UFs com
                 apuração relevante). Serve para UFs que ainda contaram pouco.
  votos_rest   = votos válidos que faltam: total estimado da UF − já apurado.
  parcela_rest = mistura do observado na UF com prior + swing, pesando pela fração apurada.

Limite conhecido: dentro da UF supõe que as seções que faltam votam como as já apuradas (ajustado
pelo prior). Na prática a capital costuma chegar antes do interior, o que puxa o observado do início.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

MINIMO_APURADO = 0.05  # abaixo disso a UF ainda não diz nada confiável sobre si mesma


@dataclass
class LeituraUF:
    uf: str
    secoes_totalizadas: int
    secoes_total: int
    lula: int
    flavio: int
    hora: str = ""

    @property
    def fracao(self) -> float:
        return self.secoes_totalizadas / self.secoes_total if self.secoes_total else 0.0

    @property
    def validos(self) -> int:
        return self.lula + self.flavio


@dataclass
class ProjecaoUF:
    uf: str
    regiao: str
    fracao: float
    lula: int
    flavio: int
    prior: float
    observado: float | None
    parcela_rest: float
    votos_rest: float
    proj_lula: float
    proj_flavio: float
    desvio_votos: float


@dataclass
class Projecao:
    ufs: list[ProjecaoUF]
    swing: float
    fracao_secoes: float
    lula: int
    flavio: int
    proj_lula: float
    proj_flavio: float
    desvio_margem: float
    chance_lula: float
    virada: dict | None = field(default=None)


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def prior_uf(base: dict, transferencia: float) -> float:
    return (base["lula"] + transferencia * base["outros"]) / base["validos"]


def projetar(leituras: dict[str, LeituraUF], base1t: dict, transferencia: float) -> Projecao:
    ufs = [u for u in base1t if u != "br"]

    # Swing nacional: só UFs com apuração relevante, ponderadas pelos votos já contados.
    num = den = 0.0
    for u in ufs:
        l = leituras.get(u)
        if l and l.fracao >= MINIMO_APURADO and l.validos:
            num += (l.lula / l.validos - prior_uf(base1t[u], transferencia)) * l.validos
            den += l.validos
    swing = num / den if den else 0.0

    # Comparecimento relativo ao 1º turno, para estimar o total de UFs que contaram pouco.
    num = den = 0.0
    for u in ufs:
        l = leituras.get(u)
        if l and l.fracao >= MINIMO_APURADO:
            num += l.validos / l.fracao
            den += base1t[u]["validos"]
    razao_comparecimento = num / den if den else 1.0

    resultado = []
    for u in ufs:
        b = base1t[u]
        l = leituras.get(u) or LeituraUF(u, 0, 1, 0, 0)
        f = l.fracao
        prior = prior_uf(b, transferencia)
        total_est = l.validos / f if f >= MINIMO_APURADO else b["validos"] * razao_comparecimento
        votos_rest = max(total_est - l.validos, 0.0) if f < 1 else 0.0
        observado = l.lula / l.validos if l.validos else None
        esperado = min(max(prior + swing, 0.0), 1.0)
        parcela = f * observado + (1 - f) * esperado if observado is not None else esperado
        # Incerteza da parcela que falta: encolhe conforme a UF apura.
        desvio = votos_rest * (0.005 + 0.03 * (1 - f))
        resultado.append(ProjecaoUF(
            uf=u, regiao=b["regiao"], fracao=f, lula=l.lula, flavio=l.flavio, prior=prior,
            observado=observado, parcela_rest=parcela, votos_rest=votos_rest,
            proj_lula=l.lula + votos_rest * parcela, proj_flavio=l.flavio + votos_rest * (1 - parcela),
            desvio_votos=desvio,
        ))

    secoes = sum((leituras[u].secoes_totalizadas if u in leituras else 0) for u in ufs)
    secoes_total = sum((leituras[u].secoes_total if u in leituras else 0) for u in ufs)
    proj_l = sum(p.proj_lula for p in resultado)
    proj_f = sum(p.proj_flavio for p in resultado)
    # Erros das UFs tendem a andar juntos (mesma onda nacional): somar linearmente é o conservador.
    desvio_margem = 2 * sum(p.desvio_votos for p in resultado)
    margem = proj_l - proj_f
    chance = 1.0 if desvio_margem == 0 and margem > 0 else 0.0 if desvio_margem == 0 else phi(margem / desvio_margem)
    return Projecao(
        ufs=resultado, swing=swing, fracao_secoes=secoes / secoes_total if secoes_total else 0.0,
        lula=sum(p.lula for p in resultado), flavio=sum(p.flavio for p in resultado),
        proj_lula=proj_l, proj_flavio=proj_f, desvio_margem=desvio_margem, chance_lula=chance,
    )


def ritmos(historico: list[dict[str, LeituraUF]], minutos: list[float], janela: float = 15.0) -> dict[str, float]:
    """Seções por minuto de cada UF, medidas nas leituras dos últimos `janela` minutos."""
    if len(historico) < 2:
        return {}
    agora = minutos[-1]
    i = next((k for k, m in enumerate(minutos) if agora - m <= janela), len(minutos) - 1)
    if i == len(minutos) - 1:
        i = len(minutos) - 2
    dt = agora - minutos[i]
    if dt <= 0:
        return {}
    out = {}
    for u, l in historico[-1].items():
        antes = historico[i].get(u)
        out[u] = max(l.secoes_totalizadas - (antes.secoes_totalizadas if antes else 0), 0) / dt
    return out


def prever_virada(p: Projecao, leituras: dict[str, LeituraUF], ritmo: dict[str, float], passo: float = 1.0,
                  limite_min: float = 600) -> dict:
    """Avança a apuração no tempo, UF por UF, no ritmo de cada uma, e procura quando o placar troca de líder.

    Sem ritmo medido (início da noite), supõe que todas as UFs andam juntas — o que tende a adiantar a
    virada, porque na prática o Nordeste chega por último.
    """
    ufs = [x for x in p.ufs if x.votos_rest > 0]
    lider_agora = "lula" if p.lula > p.flavio else "flavio" if p.flavio > p.lula else None
    lider_final = "lula" if p.proj_lula > p.proj_flavio else "flavio"
    info = {"lider_placar": lider_agora, "lider_projetado": lider_final, "vai_virar": lider_agora not in (None, lider_final)}

    total_secoes = sum(l.secoes_total for l in leituras.values())
    restantes = {x.uf: leituras[x.uf].secoes_total - leituras[x.uf].secoes_totalizadas if x.uf in leituras else 0 for x in ufs}
    usa_ritmo = sum(ritmo.values()) > 0
    if usa_ritmo:
        mediano = sorted(v for v in ritmo.values() if v > 0)
        mediano = mediano[len(mediano) // 2] if mediano else 1.0
        vel = {x.uf: ritmo.get(x.uf) or mediano for x in ufs}
    feito = {x.uf: 0.0 for x in ufs}  # fração do restante já "apurada" na simulação

    curva = []
    t = 0.0
    while t <= limite_min:
        L = p.lula + sum(feito[x.uf] * x.votos_rest * x.parcela_rest for x in ufs)
        F = p.flavio + sum(feito[x.uf] * x.votos_rest * (1 - x.parcela_rest) for x in ufs)
        sec = sum(l.secoes_totalizadas for l in leituras.values()) + sum(feito[x.uf] * restantes[x.uf] for x in ufs)
        curva.append({"min": t, "fracao_secoes": sec / total_secoes if total_secoes else 0, "margem_lula": L - F})
        if all(v >= 1 for v in feito.values()):
            break
        t += passo
        for x in ufs:
            if usa_ritmo:
                feito[x.uf] = min(1.0, feito[x.uf] + (vel[x.uf] * passo / restantes[x.uf] if restantes[x.uf] else 1))
            else:
                feito[x.uf] = min(1.0, feito[x.uf] + passo / 120)  # sem ritmo: termina tudo em ~2h

    if info["vai_virar"]:
        alvo = 1 if lider_final == "lula" else -1
        cruz = next((c for c in curva if c["margem_lula"] * alvo > 0), None)
        if cruz:
            info.update(minutos_ate=cruz["min"], fracao_secoes=cruz["fracao_secoes"])
    info["curva"] = curva[:: max(1, len(curva) // 60)]
    info["ritmo_medido"] = usa_ritmo
    return info
