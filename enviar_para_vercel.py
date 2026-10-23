"""Envia os paineis gerados (HTML) para o site do Grupo Support na Vercel.

Roda depois de uma atualizacao, pegando os arquivos da pasta RESULTADOS e
mandando cada um para o site, que passa a mostra-los online (protegidos por senha).

Le a configuracao de sistema\\configuracao.env:
    VERCEL_SITE_URL=https://seu-projeto.vercel.app
    VERCEL_UPLOAD_SECRET=<o mesmo UPLOAD_SECRET definido na Vercel>

Uso:
    py enviar_para_vercel.py                 envia os dois paineis
    py enviar_para_vercel.py finalizados     envia so a conferencia de finalizados
    py enviar_para_vercel.py acompanhamento  envia so o acompanhamento dos analistas

So usa a biblioteca padrao do Python (funciona no python que acompanha a pasta).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SISTEMA = ROOT / "sistema"
CONFIG = SISTEMA / "configuracao.env"
RESULTADOS = ROOT / "RESULTADOS"

# painel -> (chave do configuracao.env com o caminho, nome padrao em RESULTADOS)
PAINEIS = {
    "finalizados": ("PAINEL_FINALIZADOS", "CONFERENCIA FINALIZADOS.html"),
    "acompanhamento": ("PAGINA_ACOMPANHAMENTO", "ACOMPANHAMENTO ANALISTAS.html"),
}


def ler_env(caminho: Path) -> dict[str, str]:
    """Lê linhas CHAVE=valor (mesma regra do sistema: aceita UTF-8 com BOM ou cp1252)."""
    if not caminho.exists():
        return {}
    bruto = caminho.read_bytes()
    try:
        conteudo = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        conteudo = bruto.decode("cp1252")
    valores: dict[str, str] = {}
    for linha in conteudo.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[chave.strip()] = valor
    return valores


def caminho(valor: str) -> Path:
    p = Path(os.path.expandvars(valor)).expanduser()
    return p if p.is_absolute() else ROOT / p


def arquivo_do_painel(nome: str, env: dict[str, str]) -> Path:
    chave, padrao = PAINEIS[nome]
    valor = (os.environ.get(chave) or env.get(chave) or "").strip()
    return caminho(valor) if valor else RESULTADOS / padrao


def enviar(nome: str, arquivo: Path, site: str, segredo: str) -> None:
    if not arquivo.is_file():
        raise RuntimeError(f"nao encontrei o arquivo: {arquivo}")
    html = arquivo.read_text(encoding="utf-8")
    corpo = json.dumps({"html_base64": base64.b64encode(html.encode("utf-8")).decode("ascii")}).encode("utf-8")
    url = f"{site.rstrip('/')}/api/upload?painel={nome}"
    pedido = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {segredo}"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            resposta = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"o site respondeu {e.code}: {detalhe}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"nao consegui falar com o site ({e.reason}). Confira VERCEL_SITE_URL e a internet.") from None
    if not resposta.get("ok"):
        raise RuntimeError(f"o site recusou o envio: {resposta}")
    print(f"  OK  {nome}: {arquivo.name} ({len(html):,} caracteres)".replace(",", "."))


def main(argv: list[str]) -> int:
    env = ler_env(CONFIG)
    site = (os.environ.get("VERCEL_SITE_URL") or env.get("VERCEL_SITE_URL") or "").strip()
    segredo = (os.environ.get("VERCEL_UPLOAD_SECRET") or env.get("VERCEL_UPLOAD_SECRET") or "").strip()

    if not site or not segredo:
        print("Configuracao incompleta. Preencha em sistema\\configuracao.env:")
        print("  VERCEL_SITE_URL=https://seu-projeto.vercel.app")
        print("  VERCEL_UPLOAD_SECRET=<o mesmo UPLOAD_SECRET da Vercel>")
        return 2
    if not re.match(r"^https?://", site):
        print(f"VERCEL_SITE_URL deve comecar com https:// (valor atual: {site!r}).")
        return 2

    pedidos = [a.lower() for a in argv if not a.startswith("-")] or list(PAINEIS)
    desconhecidos = [p for p in pedidos if p not in PAINEIS]
    if desconhecidos:
        print(f"Painel desconhecido: {', '.join(desconhecidos)}. Use: {', '.join(PAINEIS)}.")
        return 2

    print(f"Enviando para {site} ...")
    erros = 0
    for nome in pedidos:
        arquivo = arquivo_do_painel(nome, env)
        try:
            enviar(nome, arquivo, site, segredo)
        except Exception as e:  # noqa: BLE001 - mensagem amigavel para o usuario final
            erros += 1
            print(f"  FALHOU  {nome}: {e}")
    if erros:
        print(f"\nTerminou com {erros} erro(s).")
        return 1
    print("\nPronto. Os paineis estao no ar (abra o site e faca login).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
