"""De onde vêm as leituras da apuração: o TSE ao vivo, ou uma noite simulada para testar antes do dia 25."""
from __future__ import annotations

import json
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from modelo import LeituraUF, prior_uf

def ler_arquivo_tse(d: dict, uf: str, num_a: str = "13", num_b: str = "22") -> LeituraUF:
    votos = {}
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                votos[c["n"]] = int(c["vap"] or 0)
    return LeituraUF(
        uf=uf, secoes_totalizadas=int(d["s"]["st"]), secoes_total=int(d["s"]["ts"]),
        lula=votos.get(num_a, 0), flavio=votos.get(num_b, 0), hora=d.get("hg", ""),
    )


class FonteTSE:
    """Baixa o arquivo de cada unidade (UF ou município), em paralelo: são 27 no presidente e 167 no RN,
    e tudo precisa caber em um ciclo de 1 minuto. Guarda o bruto em `pasta_bruto` para análise depois."""

    def __init__(self, unidades: list[str], pasta_bruto: Path, url, num_a: str, num_b: str):
        self.unidades, self.pasta, self.url, self.num_a, self.num_b = unidades, pasta_bruto, url, num_a, num_b
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.ultima: dict[str, LeituraUF] = {}

    def _uma(self, u: str):
        try:
            req = urllib.request.Request(self.url(u), headers={"User-Agent": "monitor-eleicao-2026"})
            with urllib.request.urlopen(req, timeout=20) as r:
                bruto = r.read()
            return u, bruto, ler_arquivo_tse(json.loads(bruto), u, self.num_a, self.num_b), None
        except Exception as e:  # rede instável não pode derrubar a noite: segue com a última leitura
            return u, None, None, f"{u}:{getattr(e, 'code', e.__class__.__name__)}"

    def ler(self, _minuto: float) -> dict[str, LeituraUF]:
        falhas = []
        with ThreadPoolExecutor(12) as ex:
            for u, bruto, leitura, erro in ex.map(self._uma, self.unidades):
                if erro:
                    falhas.append(erro)
                    continue
                anterior = self.ultima.get(u)
                if not anterior or anterior.hora != leitura.hora:
                    (self.pasta / f"{u}-{leitura.hora.replace(':', '')}.json").write_bytes(bruto)
                self.ultima[u] = leitura
        if falhas and self.ultima:
            print(f"  {len(falhas)} unidade(s) sem resposta, mantendo leitura anterior: {' '.join(falhas[:10])}")
        return dict(self.ultima)


class FonteSimulada:
    """Noite fictícia construída sobre o 1º turno, com a ordem de chegada típica.

    - Sul/Sudeste/Centro-Oeste terminam entre 1h30 e 3h depois do fechamento; Norte/Nordeste entre 2h30 e 5h30.
    - No Norte/Nordeste as primeiras seções (capitais) votam menos em Lula que o interior: `vies_capital`.
    Os números são parâmetros de teste, não previsão.
    """

    def __init__(self, base1t: dict, transferencia_real: float = 0.5, swing_real: float = 0.0,
                 vies_capital: float = -0.04, semente: int = 25, regioes_lentas=("N", "NE")):
        rnd = random.Random(semente)
        self.base = {u: b for u, b in base1t.items() if u != "br"}
        self.vies, self.lentas = vies_capital, regioes_lentas
        self.fim, self.atraso, self.parcela = {}, {}, {}
        for u, b in self.base.items():
            lento = b["regiao"] in self.lentas
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
            vies = self.vies if b["regiao"] in self.lentas else 0.0
            media_ate_f = self.parcela[u] + vies * (1 - f)
            lula = round(validos * min(max(media_ate_f, 0), 1))
            out[u] = LeituraUF(u, secoes, b["secoes"], lula, round(validos) - lula, hora=f"sim+{minuto:.0f}min")
        return out

    def resultado_real(self) -> tuple[float, float]:
        lula = sum(b["validos"] * self.parcela[u] for u, b in self.base.items())
        total = sum(b["validos"] for b in self.base.values())
        return lula, total - lula
