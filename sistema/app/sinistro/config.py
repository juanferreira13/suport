"""Leitura do arquivo de configuração e dos caminhos do projeto.

    <raiz>\\                    o que o cliente vê: atalhos, ENTRADA e RESULTADOS
    <raiz>\\sistema\\            tudo o que faz o sistema rodar (pasta oculta)
        app\\                   código (este pacote e os scripts)
        python\\                Python que acompanha a pasta, para rodar em qualquer máquina
        configuracao.env       credenciais do SGA e caminhos
        dados\\ logs\\ backups\\
"""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .util import data_br

APP = Path(__file__).resolve().parent.parent
SISTEMA = APP.parent
RAIZ = SISTEMA.parent                              # caminhos relativos da configuração partem daqui
ARQUIVO_CONFIG = SISTEMA / "configuracao.env"
NOME_CONFIG = rf"sistema\{ARQUIVO_CONFIG.name}"   # como o arquivo é citado nas mensagens


def ler_env(caminho: Path) -> dict[str, str]:
    """Lê linhas CHAVE=valor. Linhas iniciadas por # são comentários."""
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


@dataclass
class Config:
    api_url: str
    token: str
    usuario: str
    senha: str
    data_inicial: datetime.date
    por_pagina: int
    planilha: Path
    planilha_base: Path | None
    pasta_entrada: Path
    pasta_dados: Path
    pasta_logs: Path
    pasta_backups: Path
    backups_manter: int
    # Planilhas dos setores (None = não gerar) e as originais do Google usadas na primeira carga.
    planilha_analistas: Path | None = None
    planilha_consultores: Path | None = None
    planilha_reguladores: Path | None = None
    base_analistas: Path | None = None
    base_consultores: Path | None = None
    base_reguladores: Path | None = None
    # Página HTML da conferência de finalizados (None = não gerar) e desde quando ela mostra.
    painel_finalizados: Path | None = None
    painel_desde: datetime.date = datetime.date(2025, 1, 1)
    # Primeiro ano do SIGA que deve vir do DashBoard (o sistema confere se todos até o atual já vieram).
    siga_ano_inicial: int = 2021
    # Registro em texto de cada importação (manual ou automática). None = não registrar.
    registro: Path | None = None
    # Página HTML onde os analistas preenchem o acompanhamento (None = não gerar) e a pasta Downloads,
    # onde o navegador costuma salvar o arquivo de alterações da página (None = não olhar).
    pagina_acompanhamento: Path | None = None
    pasta_downloads: Path | None = None
    # Pastas extras onde o sistema também procura relatórios do SIGA e do SGA (ex.: a pasta de saída de uma
    # exportação automática). Os arquivos reconhecidos são copiados para a ENTRADA; os originais não são tocados.
    pastas_entrada_extra: tuple[Path, ...] = ()
    # Google Sheets: chave da conta de serviço e link (ou código) de cada planilha. Planilha configurada aqui
    # passa a ser a de trabalho: o sistema lê e grava nela, e não no .xlsx correspondente de RESULTADOS.
    google_credenciais: Path | None = None
    google_sinistro: str = ""
    google_analistas: str = ""
    google_consultores: str = ""
    google_reguladores: str = ""

    @property
    def api_configurada(self) -> bool:
        return bool(self.token and self.usuario and self.senha)

    @property
    def google_configurado(self) -> bool:
        return bool(self.google_credenciais and (self.google_sinistro or self.google_analistas or self.google_consultores
                                                 or self.google_reguladores))


def _pasta_downloads() -> Path:
    """A pasta Downloads do Windows, mesmo quando foi movida (para o OneDrive, por exemplo)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as chave:
            valor, _ = winreg.QueryValueEx(chave, "{374DE290-123F-4565-9164-39C4925E467B}")
        return Path(os.path.expandvars(valor))
    except (ImportError, OSError):
        return Path.home() / "Downloads"


def _caminho(valor: str) -> Path:
    p = Path(os.path.expandvars(valor)).expanduser()
    return p if p.is_absolute() else RAIZ / p


def carregar_config(arquivo_env: Path | None = None) -> Config:
    env = ler_env(arquivo_env or ARQUIVO_CONFIG)

    def obter(chave: str, padrao: str = "") -> str:
        return os.environ.get(chave, env.get(chave, padrao)).strip()

    inicial = data_br(obter("SGA_DATA_INICIAL", "01/01/2020"))
    if inicial is None:
        raise SystemExit(f"SGA_DATA_INICIAL em {NOME_CONFIG} deve estar no formato dd/mm/aaaa.")
    base = obter("PLANILHA_BASE")

    def opcional(chave: str) -> Path | None:
        return _caminho(obter(chave)) if obter(chave) else None

    painel_desde = data_br(obter("PAINEL_FINALIZADOS_DESDE", "01/01/2025"))
    if painel_desde is None:
        raise SystemExit(f"PAINEL_FINALIZADOS_DESDE em {NOME_CONFIG} deve estar no formato dd/mm/aaaa.")

    ano_siga = obter("SIGA_ANO_INICIAL", "2021")
    if not ano_siga.isdigit():
        raise SystemExit(f"SIGA_ANO_INICIAL em {NOME_CONFIG} deve ser um ano, por exemplo 2021.")

    registro = obter("REGISTRO_EXPORTACOES", r"RESULTADOS\REGISTRO DE EXPORTACOES.txt")
    # Sem a chave no arquivo, olha a pasta Downloads do usuário; com a chave em branco, não olha nenhuma.
    tem_downloads = "PASTA_DOWNLOADS" in os.environ or "PASTA_DOWNLOADS" in env
    # Uma ou mais pastas separadas por ; (ou por quebra de linha). Caminhos relativos partem da pasta do projeto.
    extras = tuple(_caminho(p.strip()) for p in re.split(r"[;\n]", obter("PASTAS_ENTRADA_EXTRA")) if p.strip())

    return Config(
        pastas_entrada_extra=extras,
        google_credenciais=opcional("GOOGLE_CREDENCIAIS"),
        google_sinistro=obter("GOOGLE_SINISTRO"),
        google_analistas=obter("GOOGLE_ANALISTAS"),
        google_consultores=obter("GOOGLE_CONSULTORES"),
        google_reguladores=obter("GOOGLE_REGULADORES"),
        pagina_acompanhamento=opcional("PAGINA_ACOMPANHAMENTO"),
        pasta_downloads=opcional("PASTA_DOWNLOADS") if tem_downloads else _pasta_downloads(),
        registro=_caminho(registro) if registro else None,
        siga_ano_inicial=int(ano_siga),
        painel_finalizados=opcional("PAINEL_FINALIZADOS"),
        painel_desde=painel_desde,
        planilha_analistas=opcional("PLANILHA_ANALISTAS"),
        planilha_consultores=opcional("PLANILHA_CONSULTORES"),
        planilha_reguladores=opcional("PLANILHA_REGULADORES"),
        base_analistas=opcional("PLANILHA_BASE_ANALISTAS"),
        base_consultores=opcional("PLANILHA_BASE_CONSULTORES"),
        base_reguladores=opcional("PLANILHA_BASE_REGULADORES"),
        api_url=obter("SGA_API_URL", "https://api.hinova.com.br/api/sga/v2").rstrip("/"),
        token=obter("SGA_TOKEN"),
        usuario=obter("SGA_USUARIO"),
        senha=obter("SGA_SENHA"),
        data_inicial=inicial,
        por_pagina=int(obter("SGA_API_POR_PAGINA", "100") or 100),
        planilha=_caminho(obter("PLANILHA_SINISTRO", r"RESULTADOS\GERENCIAL SINISTRO.xlsx")),
        planilha_base=_caminho(base) if base else None,
        pasta_entrada=_caminho(obter("PASTA_ENTRADA", "ENTRADA")),
        pasta_dados=SISTEMA / "dados",
        pasta_logs=SISTEMA / "logs",
        pasta_backups=SISTEMA / "backups",
        backups_manter=int(obter("BACKUPS_MANTER", "7") or 7),
    )
