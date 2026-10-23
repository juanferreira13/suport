"""Registro em texto de cada dado que entra no sistema: o quê, quantos eventos e se foi manual ou automático.

MANUAL     = arquivo exportado por uma pessoa e salvo na pasta ENTRADA
AUTOMÁTICO = consulta feita pelo próprio sistema (API do SGA)
"""
from __future__ import annotations

import datetime
from pathlib import Path

MANUAL, AUTOMATICO = "MANUAL", "AUTOMÁTICO"

_CABECALHO = (
    "REGISTRO DE EXPORTAÇÕES\r\n"
    "Cada linha é um arquivo ou uma consulta que entrou no sistema, do mais antigo para o mais recente.\r\n"
    "MANUAL = arquivo exportado por uma pessoa e salvo na pasta ENTRADA.  "
    "AUTOMÁTICO = consulta feita pelo próprio sistema.\r\n\r\n"
    f"{'DATA E HORA':<16}  {'FORMA':<10}  {'SISTEMA':<7}  {'CONTEÚDO':<32}  {'EVENTOS':>7}  {'SITUAÇÃO':<44}  ARQUIVO\r\n"
    f"{'-' * 16}  {'-' * 10}  {'-' * 7}  {'-' * 32}  {'-' * 7}  {'-' * 44}  {'-' * 30}\r\n"
)


def _numero(n) -> str:
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else (n or "-")


def anotar(arquivo: Path | None, forma: str, sistema: str, conteudo: str, eventos, situacao: str, nome_arquivo: str = "",
           log=None) -> None:
    """Acrescenta uma linha ao registro. Uma falha aqui nunca interrompe a rotina."""
    if arquivo is None:
        return
    linha = (f"{datetime.datetime.now():%d/%m/%Y %H:%M}  {forma:<10}  {sistema:<7}  {conteudo[:32]:<32}  "
             f"{_numero(eventos):>7}  {situacao[:44]:<44}  {nome_arquivo or '-'}\r\n")
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        novo = not arquivo.exists()
        # BOM só no arquivo novo, para o Bloco de Notas reconhecer os acentos
        with open(arquivo, "a", encoding="utf-8-sig" if novo else "utf-8", newline="") as f:
            if novo:
                f.write(_CABECALHO)
            f.write(linha)
    except OSError as e:
        if log:
            log.warning("Não consegui escrever no registro %s (%s).", arquivo.name, e)
