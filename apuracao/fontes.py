"""De onde vêm as leituras da apuração: o TSE ao vivo, ou uma noite simulada para testar antes do dia 25."""
from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path

from modelo import LeituraUF, prior_uf

TSE = "https://resultados.tse.jus.br/oficial/ele2026/{ele}/dados/{uf}/{uf}-c0001-e{ele6}-u.json"
ELEICAO_2T = "6258"  # presidente 2º turno, conforme oficial/comum/config/ele-c.json
NUM_LULA, NUM_FLAVIO = "13", "22"


def ler_arquivo_tse(d: dict, uf: str) -> LeituraUF:
    votos = {}
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                votos[c["n"]] = int(c["vap"] or 0)
    return LeituraUF(
        uf=uf, secoes_totalizadas=int(d["s"]["st"]), secoes_total=int(d["s"]["ts"]),
        lula=votos.get(NUM_LULA, 0), flavio=votos.get(NUM_FLAVIO, 0), hora=d.get("hg", ""),
    )


class FonteTSE:
    """Baixa o arquivo de cada UF. Guarda o bruto em `pasta_bruto` para análise depois da eleição."""

    def __init__(self, ufs: list[str], pasta_bruto: Path, eleicao: str = ELEICAO_2T):
        self.ufs, self.pasta, self.ele = ufs, pasta_bruto, eleicao
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.ultima: dict[str, LeituraUF] = {}

    def ler(self, _minuto: float) -> dict[str, LeituraUF]:
        falhas = []
        for uf in self.ufs:
            url = TSE.format(ele=self.ele, ele6=self.ele.zfill(6), uf=uf)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "monitor-eleicao-2026"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    bruto = r.read()
                d = json.loads(bruto)
                leitura = ler_arquivo_tse(d, uf)
                anterior = self.ultima.get(uf)
                if not anterior or anterior.hora != leitura.hora:
                    (self.pasta / f"{uf}-{leitura.hora.replace(':', '')}.json").write_bytes(bruto)
                self.ultima[uf] = leitura
            except Exception as e:  # rede instável não pode derrubar a noite: segue com a última leitura
                falhas.append(f"{uf}:{getattr(e, 'code', e.__class__.__name__)}")
        if falhas and self.ultima:
            print(f"  {len(falhas)} UF(s) sem resposta, mantendo leitura anterior: {' '.join(falhas)}")
        return dict(self.ultima)


class FonteSimulada:
    """Noite fictícia construída sobre o 1º turno, com a ordem de chegada típica.

    - Sul/Sudeste/Centro-Oeste terminam entre 1h30 e 3h depois do fechamento; Norte/Nordeste entre 2h30 e 5h30.
    - No Norte/Nordeste as primeiras seções (capitais) votam menos em Lula que o interior: `vies_capital`.
    Os números são parâmetros de teste, não previsão.
    """

    def __init__(self, base1t: dict, transferencia_real: float = 0.5, swing_real: float = 0.0,
                 vies_capital: float = -0.04, semente: int = 25):
        rnd = random.Random(semente)
        self.base = {u: b for u, b in base1t.items() if u != "br"}
        self.vies = vies_capital
        self.fim, self.atraso, self.parcela = {}, {}, {}
        for u, b in self.base.items():
            lento = b["regiao"] in ("N", "NE")
            self.fim[u] = rnd.uniform(150, 330) if lento else rnd.uniform(90, 180)
            self.atraso[u] = rnd.uniform(3, 15)
            self.parcela[u] = min(max(prior_uf(b, transferencia_real) + swing_real + rnd.gauss(0, 0.01), 0), 1)

    def ler(self, minuto: float) -> dict[str, LeituraUF]:
        out = {}
        for u, b in self.base.items():
            t = max(minuto - self.atraso[u], 0)
            f = min(1.0, (t / self.fim[u]) ** 0.8)
            secoes = round(b["secoes"] * f)
            f = secoes / b["secoes"]
            validos = b["validos"] * f
            # Viés de capital: a parcela observada começa deslocada e converge para a real ao fim.
            # Ajuste para que o total da UF, ao fim, seja exatamente a parcela real.
            vies = self.vies if b["regiao"] in ("N", "NE") else 0.0
            media_ate_f = self.parcela[u] + vies * (1 - f)
            lula = round(validos * min(max(media_ate_f, 0), 1))
            out[u] = LeituraUF(u, secoes, b["secoes"], lula, round(validos) - lula, hora=f"sim+{minuto:.0f}min")
        return out

    def resultado_real(self) -> tuple[float, float]:
        lula = sum(b["validos"] * self.parcela[u] for u, b in self.base.items())
        total = sum(b["validos"] for b in self.base.values())
        return lula, total - lula
