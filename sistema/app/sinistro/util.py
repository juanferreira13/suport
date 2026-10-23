"""Funções de texto, data e log usadas por todo o projeto."""
from __future__ import annotations

import datetime
import logging
import re
import sys
import unicodedata
from pathlib import Path

NBSP = "\xa0"
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_ESPACOS = re.compile(r" +")
_DATA_BR = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")   # o Google também mostra 5/3/2021
_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def texto(v) -> str:
    """Valor de célula como texto: vazio vira '', 123.0 vira '123', data vira dd/mm/aaaa."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "VERDADEIRO" if v else "FALSO"
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v == int(v) else repr(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%d/%m/%Y")
    return str(v)


def trim(v) -> str:
    """Equivalente ao TRIM/ARRUMAR da planilha."""
    return _ESPACOS.sub(" ", texto(v)).strip(" ")


def limpar(v) -> str:
    """Equivalente a TRIM(CLEAN(SUBSTITUTE(x;CHAR(160);" "))) usado nas chaves da planilha."""
    return _ESPACOS.sub(" ", _CONTROLE.sub("", texto(v).replace(NBSP, " "))).strip(" ")


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def chave_cabecalho(v) -> str:
    """Cabeçalho reduzido a letras e números maiúsculos, para comparar nomes de colunas."""
    return re.sub(r"[^A-Z0-9]", "", sem_acento(texto(v)).upper())


def data_br(v) -> datetime.date | None:
    """Converte 'dd/mm/aaaa', 'aaaa-mm-dd' ou data em date; None se não for data válida."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    s = texto(v).strip()
    m = _DATA_BR.match(s)
    try:
        if m:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = _DATA_ISO.match(s)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def competencia(v) -> str:
    """mm/aaaa de uma data (texto dd/mm/aaaa ou data); '' se não for data válida."""
    d = data_br(v)
    return d.strftime("%m/%Y") if d else ""


def formatar_reais(valor: float) -> str:
    """1297.8 -> 'R$ 1.297,80' (mesmo formato do relatório do SGA)."""
    s = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if valor < 0 else "") + "R$ " + s


def configurar_log(pasta_logs: Path, nome: str = "sinistro") -> logging.Logger:
    """Log no console e em logs/AAAA-MM.log."""
    pasta_logs.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger(nome)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%d/%m/%Y %H:%M:%S")
    arquivo = logging.FileHandler(pasta_logs / f"{datetime.date.today():%Y-%m}.log", encoding="utf-8")
    arquivo.setFormatter(fmt)
    log.addHandler(arquivo)
    if sys.stdout is None:  # execução sem janela (pythonw, na tarefa agendada): só o arquivo de log
        return log
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)
    return log
