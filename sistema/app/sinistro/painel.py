"""Página HTML "Conferência de finalizados" (o que era a aba FINALIZADOS (conf.Lari) do sinistro).

Gera um único arquivo .html, com os dados embutidos, na identidade visual do Grupo Support.
O arquivo contém dados de associados: é para uso interno, não para publicar.
"""
from __future__ import annotations

import base64
import datetime
import json
import re
from pathlib import Path

from . import integracao as I
from .config import SISTEMA
from .util import texto, trim

MODELO = Path(__file__).with_name("painel_modelo.html")
LOGO_SITE = "https://www.supportgrupo.com.br/assets/images/uploads/imgs/configuracoes/logo-completa-horizontal.webp"
TIPOS_IMAGEM = {".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _logo() -> str:
    """Um arquivo logo.png/.webp/.svg/.jpg na pasta sistema é embutido na página (funciona sem
    internet); sem ele, a página busca a logo no site do Grupo Support e, se não conseguir, usa texto."""
    for extensao, tipo in TIPOS_IMAGEM.items():
        arquivo = SISTEMA / f"logo{extensao}"
        if arquivo.exists():
            return f"data:{tipo};base64,{base64.b64encode(arquivo.read_bytes()).decode('ascii')}"
    return LOGO_SITE


def linhas_painel(sga: list[list[str]], integ: list[list], resultado: I.Resultado, desde: datetime.date,
                  vistos=None, veiculos=None, reguladores=None) -> list[list]:
    """Eventos finalizados no formato da página: textos em maiúsculas, datas aaaa-mm-dd, a anotação de conferência
    e o último setor em que o processo apareceu na aba SIGA (`vistos`: setores.SetoresVistos).
    `veiculos` (protocolo SGA -> {marca, modelo}) e `reguladores` (número -> regulador analista) alimentam os indicadores."""
    veiculos, reguladores = veiculos or {}, reguladores or {}
    saida = []
    for l in I.finalizados(sga, integ, resultado, desde, com_cidade=True):
        status_siga, status_sga, classificacao = trim(l[2]).upper(), trim(l[11]).upper(), trim(l[12]).upper()
        vd = veiculos.get(trim(l[10])) or {}   # marca/modelo pelo PROTOCOLO SGA
        saida.append([
            l[0], trim(l[1]).upper(), status_siga, trim(l[3]).upper(), trim(l[4]), trim(l[5]),
            l[6] if _ISO.fullmatch(texto(l[6])) else "", l[7], l[8] if isinstance(l[8], int) else None, trim(l[9]), l[10],
            status_sga, classificacao, trim(l[13]), trim(l[14]), I.pendencia(status_siga, status_sga, classificacao),
            ", ".join(vistos.setores(l[0])) if vistos else "",
            trim(l[16]), trim(vd.get("marca", "")), trim(vd.get("modelo", "")), trim(reguladores.get(l[0], "")),
        ])
    return saida


def gerar(destino: Path, sga: list[list[str]], integ: list[list], resultado: I.Resultado, desde: datetime.date,
          origem_sga: str, vistos=None, ultimo_sga: str = "", ultimo_siga: str = "",
          veiculos: dict | None = None, reguladores: dict | None = None) -> dict:
    """Grava a página e devolve um resumo (quantidades) para o log."""
    linhas = linhas_painel(sga, integ, resultado, desde, vistos, veiculos, reguladores)
    dados = {
        "gerado": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "desde": desde.strftime("%m/%Y"),
        "origem_sga": origem_sga or "sem dados",
        "eventos_siga": len(integ),
        "ultimo_sga": ultimo_sga,
        "ultimo_siga": ultimo_siga,
        "logo": _logo(),
        "linhas": linhas,
    }
    # "</" não pode aparecer dentro de <script>; "<\/" é o mesmo texto para o JSON.
    embutido = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(MODELO.read_text(encoding="utf-8").replace("__DADOS__", embutido), encoding="utf-8")
    temporario.replace(destino)
    anotacoes = {codigo: sum(1 for l in linhas if l[15] == codigo) for codigo in I.PENDENCIAS}
    return {"eventos": len(linhas), "anotacoes": anotacoes,
            "divergentes": sum(1 for l in linhas if l[11] and l[2] != l[11]), "sem_sga": sum(1 for l in linhas if not l[11]),
            "com_setor": sum(1 for l in linhas if l[16])}
