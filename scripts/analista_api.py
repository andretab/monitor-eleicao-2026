"""Analista pela API do Claude: escreve um boletim (pesquisas, apuração ou balanço) e grava no site.

    python scripts/analista_api.py --corrida presidente
    python scripts/analista_api.py --corrida rn --motivo "pesquisa nova da Quaest"
    python scripts/analista_api.py --corrida presidente --se-novidade <commit>   # só escreve se entrou pesquisa nova
    python scripts/analista_api.py --corrida rn --simulacao                        # aceita estado simulado (teste)

Os números vêm de scripts/estatisticas.py (as mesmas contas do site); o modelo só interpreta e escreve.
Usa Claude Opus 5.5 com raciocínio adaptativo em esforço alto e saída num formato fixo (título, destaque,
parágrafos). A chave vem de ANTHROPIC_API_KEY (segredo do GitHub); nunca fica no código.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from estatisticas import calcular  # noqa: E402

BRASILIA = timezone(timedelta(hours=-3))
MODELO = "claude-opus-5-5"
SITE = "https://eleicao.andrefreitas.eng.br"

CORRIDAS = {
    "presidente": {
        "titulo": "2º turno para presidente: Lula (PT) × Flávio Bolsonaro (PL)",
        "boletins": RAIZ / "dados" / "boletins.json", "pesquisas": "dados/pesquisas.json",
        "ramo": "ao-vivo", "gerar_js": [sys.executable, str(RAIZ / "scripts" / "gerar_dados_js.py")],
        "pagina": SITE, "campos": ("lula", "flavio"),
        "contexto": "1º turno (TSE): Flávio 47,03% × Lula 45,16% dos válidos; demais 7,8%. No 1º turno as pesquisas "
                    "erraram em média 3,8 p.p. a favor de Lula na vantagem. 'Corrigido' = cada instituto recebe de volta "
                    "o erro que teve no 1º turno.",
    },
    "rn": {
        "titulo": "2º turno para governador do RN: Cadu (PT) × Allyson (União)",
        "boletins": RAIZ / "dados" / "rn" / "boletins.json", "pesquisas": "dados/rn/pesquisas.json",
        "ramo": "ao-vivo-rn", "gerar_js": [sys.executable, str(RAIZ / "scripts" / "atualizar_pesquisas_rn.py"), "--so-js"],
        "pagina": SITE + "/painel/rn.html", "campos": ("cadu", "allyson"),
        "contexto": "1º turno (TSE): Allyson 36,94% × Cadu 36,16% × Álvaro Dias (PL) 26,71%. Os votos de Álvaro decidem o "
                    "2º turno. No 1º turno quase todas as pesquisas do RN erraram muito (em média 15,6 p.p. a favor de "
                    "Allyson; Cadu cresceu na reta final); por isso a média 'corrigida' tende a exagerar a vantagem de Cadu "
                    "e o site mostra 'como divulgado' por padrão. Há poucas pesquisas de 2º turno.",
    },
}

SISTEMA = """Você é o analista de dados eleitorais do site Monitor Eleição 2026. Escreve boletins curtos em \
português do Brasil para leitores comuns, que querem entender as pesquisas e a apuração sem jargão.

Regras:
- Use somente os números do bloco DADOS. Não faça contas novas além de comparações simples, não invente pesquisas, \
números ou fatos, e não use conhecimento externo sobre a eleição.
- Tom neutro e factual, sem torcida, sem adjetivos sobre candidatos e sem prever o resultado como certo. \
Chance e projeção são estimativas: diga a incerteza quando ela importar.
- Diga o que mudou em relação aos boletins anteriores (se houver). Se nada relevante mudou, diga isso com clareza.
- 3 a 6 parágrafos curtos, cada um com pelo menos um número concreto. Percentuais com vírgula decimal (51,8%).
- Título com até 90 caracteres; destaque com uma frase que resuma o boletim.

Por tipo de boletim:
- pesquisas: média como divulgada e corrigida, chance estimada, tendência (e se é distinguível de estabilidade), \
institutos que divergem, pesquisas novas ou a divulgar, e o peso do erro do 1º turno.
- apuracao: % das seções, placar, projeção e chance; chance de o placar virar e faixa de horário mais provável; \
de onde ainda vêm votos; comparação com 2022 só se houver referência nos dados.
- balanco: vencedor e margem; quem acertou e quem errou (ranking pelo erro na vantagem); como a média e a \
projeção do site se saíram; quando foi a virada (se houve); onde cada candidato mais cresceu."""

FORMATO = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "destaque": {"type": "string"},
            "paragrafos": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["titulo", "destaque", "paragrafos"],
        "additionalProperties": False,
    },
}


def git(*a) -> str:
    return subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8").stdout


def estado_ao_vivo(ramo: str) -> dict | None:
    """estado.json do ramo da apuração (ao-vivo / ao-vivo-rn), se existir."""
    subprocess.run(["git", "fetch", "-q", "origin", ramo], cwd=RAIZ, capture_output=True)
    txt = git("show", "FETCH_HEAD:estado.json")
    try:
        return json.loads(txt) if txt.strip() else None
    except json.JSONDecodeError:
        return None


def novas_pesquisas(caminho: str, desde: str) -> list[dict]:
    def ler(ref):
        try:
            return json.loads(git("show", f"{ref}:{caminho}") or "{}")
        except json.JSONDecodeError:
            return {}
    vistas = {(p["instituto"], p["fim"]) for p in ler(desde).get("segundo_turno", [])}
    return [p for p in ler("HEAD").get("segundo_turno", []) if (p["instituto"], p["fim"]) not in vistas]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrida", choices=sorted(CORRIDAS), default="presidente")
    ap.add_argument("--tipo", choices=["auto", "pesquisas", "apuracao", "balanco"], default="auto")
    ap.add_argument("--motivo", default="", help="por que este boletim está sendo escrito (vai no pedido ao modelo)")
    ap.add_argument("--se-novidade", metavar="COMMIT", help="só escreve se entrou pesquisa nova desde este commit")
    ap.add_argument("--simulacao", action="store_true", help="aceita estado de apuração simulado (teste)")
    ap.add_argument("--nao-gravar", action="store_true", help="só imprime o boletim")
    ap.add_argument("--so-apuracao", action="store_true", help="só escreve se houver apuração em andamento ou concluída")
    a = ap.parse_args()
    cfg = CORRIDAS[a.corrida]

    motivo = a.motivo
    if a.se_novidade:
        novas = novas_pesquisas(cfg["pesquisas"], a.se_novidade)
        if not novas:
            print(f"{a.corrida}: sem pesquisa nova, nenhum boletim")
            return 0
        motivo = motivo or "Pesquisa(s) nova(s): " + ", ".join(f"{p['instituto']} ({p['fim']})" for p in novas)

    estado = estado_ao_vivo(cfg["ramo"])
    if estado and estado.get("modo") == "simulacao" and not a.simulacao:
        estado = None  # ensaio não vira boletim de verdade
    if a.so_apuracao and not (estado and estado.get("fracao_secoes")):
        print(f"{a.corrida}: sem apuração em andamento, nenhum boletim")
        return 0
    tipo = a.tipo
    if tipo == "auto":
        tipo = "pesquisas" if not estado or not estado.get("fracao_secoes") else "balanco" if estado["fracao_secoes"] >= 1 else "apuracao"
    boletins = json.loads(cfg["boletins"].read_text(encoding="utf-8")) if cfg["boletins"].exists() else {"boletins": []}
    if tipo == "balanco" and boletins["boletins"] and boletins["boletins"][0].get("tipo") == "balanco" and a.tipo == "auto":
        print(f"{a.corrida}: balanço já publicado")
        return 0

    agora = datetime.now(BRASILIA)
    dados = calcular(a.corrida == "rn", estado if tipo != "pesquisas" else None)
    anteriores = [{k: b.get(k) for k in ("quando", "tipo", "titulo", "paragrafos")} for b in boletins["boletins"][:2]]
    pedido = (f"Disputa: {cfg['titulo']}\nAgora (Brasília): {agora:%d/%m/%Y %H:%M}\nTipo de boletim: {tipo}\n"
              + (f"Motivo: {motivo}\n" if motivo else "")
              + (f"Atenção: a apuração abaixo é SIMULADA (teste); diga isso no título.\n" if estado and estado.get("modo") == "simulacao" else "")
              + f"\nCONTEXTO\n{cfg['contexto']}\n\nBOLETINS ANTERIORES\n{json.dumps(anteriores, ensure_ascii=False)}\n\n"
              f"DADOS\n{json.dumps(dados, ensure_ascii=False)}\n\nEscreva o boletim.")

    cliente = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente
    try:
        resposta = cliente.beta.messages.create(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # se o modelo recusar, a própria API tenta o modelo reserva recomendado
            thinking={"type": "adaptive"},
            output_config={"effort": "high", "format": FORMATO},
            system=SISTEMA,
            messages=[{"role": "user", "content": pedido}],
        )
    except anthropic.AuthenticationError:
        print("ERRO: chave da API inválida (confira o segredo ANTHROPIC_API_KEY)")
        return 1
    except anthropic.RateLimitError:
        print("ERRO: limite de uso da API atingido; tenta na próxima rodada")
        return 1
    except anthropic.APIStatusError as e:
        print(f"ERRO da API ({e.status_code}): {e.message}")
        return 1
    except anthropic.APIConnectionError:
        print("ERRO: sem conexão com a API")
        return 1

    if resposta.stop_reason == "refusal":
        print("O modelo recusou escrever este boletim; nada gravado")
        return 1
    texto = next((b.text for b in resposta.content if b.type == "text"), "")
    boletim = json.loads(texto)
    paragrafos = [p.strip() for p in boletim["paragrafos"] if p.strip()][:6]
    novo = {"quando": agora.strftime("%Y-%m-%dT%H:%M"), "tipo": tipo, "titulo": boletim["titulo"].strip(),
            "destaque": boletim["destaque"].strip(), "paragrafos": paragrafos,
            "fontes": [cfg["pagina"]], "autor": f"{resposta.model} (API)"}
    u = resposta.usage
    custo = (u.input_tokens * 4 + u.output_tokens * 20) / 1e6  # US$ por milhão de tokens do Opus 5.5 (4 entrada / 20 saída)
    print(f"{a.corrida} · {tipo} · {novo['titulo']}\n  tokens: entrada {u.input_tokens}, saída {u.output_tokens} · ~US$ {custo:.2f}")
    for p in paragrafos:
        print("  -", p)
    if a.nao_gravar:
        return 0

    boletins["boletins"].insert(0, novo)
    boletins.setdefault("_leia", "Boletins de análise, mais novo primeiro (escritos pelo Claude via API).")
    cfg["boletins"].write_text(json.dumps(boletins, ensure_ascii=False, indent=1), encoding="utf-8")
    subprocess.run(cfg["gerar_js"], cwd=RAIZ, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
