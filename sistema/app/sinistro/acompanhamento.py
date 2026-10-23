"""Acompanhamento dos analistas: página HTML onde a equipe preenche cada processo.

    RESULTADOS\\ACOMPANHAMENTO ANALISTAS.html
        painel (a preencher, atrasados, em dia, concluídos; por situação e por analista), últimas
        alterações e a lista dos processos das abas ANALISTAS e VIDROS, com ANALISTA, SITUAÇÃO,
        PRÓXIMA AÇÃO, PRAZO e OBSERVAÇÃO para preencher

A página é um arquivo, sem servidor por trás: o botão "Salvar alterações" grava um arquivo
"ACOMPANHAMENTO ANALISTAS - <nome> - <data>.json" na pasta ENTRADA (ou em Downloads, que o sistema
também olha). Na atualização seguinte, `aplicar` incorpora o arquivo ao que está guardado por processo
(dados/manuais.json) e a página é refeita com tudo junto. A OBSERVAÇÃO é a mesma da coluna OBSERVAÇÃO
das abas ANALISTAS e VIDROS da planilha: editar em qualquer um dos dois lugares vale para os dois.
O arquivo contém dados de associados: uso interno, não publicar.
"""
from __future__ import annotations

import collections
import datetime
import json
import re
from pathlib import Path

from . import integracao as I
from . import registro
from .painel import _logo
from .util import data_br, texto, trim

MODELO = Path(__file__).with_name("acompanhamento_modelo.html")
TIPO_ARQUIVO = "acompanhamento-analistas"   # marca os arquivos salvos pela página
PREFIXO_ARQUIVO = "ACOMPANHAMENTO ANALISTAS"
LISTAS = ("ANALISTAS", "VIDROS")
SITUACOES = ["Em análise", "Aguardando associado", "Aguardando documentos", "Aguardando oficina/terceiro",
             "Aguardando outro setor", "Concluído"]
CONCLUIDO = "Concluído"
# campo da página -> grupo em dados/manuais.json (None = OBSERVAÇÃO da aba da lista, ver `grupo`)
CAMPOS = {"analista": "ACOMPANHAMENTO/ANALISTA", "situacao": "ACOMPANHAMENTO/SITUAÇÃO",
          "proxima": "ACOMPANHAMENTO/PRÓXIMA AÇÃO", "prazo": "ACOMPANHAMENTO/PRAZO", "obs": None}
GRUPO_ATUALIZADO, GRUPO_ATUALIZADO_POR = "ACOMPANHAMENTO/ATUALIZADO EM", "ACOMPANHAMENTO/ATUALIZADO POR"
QUEM_PLANILHA = "planilha ANALISTAS"
LIMITE_TEXTO = 2000
HISTORICO_MAXIMO, HISTORICO_NA_PAGINA, ARQUIVOS_MAXIMO = 5000, 300, 2000

_PROTOCOLO = re.compile(r"[0-9A-Za-z./-]{1,40}")
_MOMENTO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_MARCA = re.compile(rb'^\s*\{.*?"tipo"\s*:\s*"' + TIPO_ARQUIVO.encode() + rb'"', re.S)


def grupo(campo: str, lista: str) -> str:
    return CAMPOS[campo] or f"{lista}/OBSERVAÇÃO"


def _como_data(v):
    """Data em qualquer forma (data, dd/mm/aaaa, aaaa-mm-dd ou nº de série do Excel) -> date ou None."""
    d = data_br(v)
    if d:
        return d
    s = texto(v).strip()
    if s.isdigit() and 36500 < int(s) < 73000:   # nº de série do Excel (anos 2000 a 2099)
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(s))
    return None


def pendencia(situacao: str, prazo: str, hoje: datetime.date) -> str:
    if not situacao:
        return "PREENCHER"
    if situacao == CONCLUIDO:
        return "CONCLUÍDO"
    d = _como_data(prazo)
    return "ATRASADO" if d and d < hoje else "EM DIA"


def _marcar(manuais, protocolo: str, em: str, quem: str) -> None:
    manuais.dados.setdefault(GRUPO_ATUALIZADO, {})[protocolo] = em
    manuais.dados.setdefault(GRUPO_ATUALIZADO_POR, {})[protocolo] = quem


# ----------------------------------------------------------------------------- histórico

class Historico:
    """Alterações já incorporadas (dados/acompanhamento.json). Alimentam as "últimas alterações" da página
    e evitam incorporar o mesmo arquivo duas vezes."""

    def __init__(self, pasta_dados: Path):
        self.arquivo = pasta_dados / "acompanhamento.json"
        self.alteracoes: list[list[str]] = []   # [em, quem, protocolo, lista, campo, de, para]
        self.arquivos: list[str] = []            # id de cada arquivo da página já incorporado

    def carregar(self) -> None:
        if self.arquivo.exists():
            d = json.loads(self.arquivo.read_text(encoding="utf-8"))
            self.alteracoes, self.arquivos = d.get("alteracoes", []), d.get("arquivos", [])

    def salvar(self) -> None:
        self.alteracoes, self.arquivos = self.alteracoes[-HISTORICO_MAXIMO:], self.arquivos[-ARQUIVOS_MAXIMO:]
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps({"alteracoes": self.alteracoes, "arquivos": self.arquivos}, ensure_ascii=False, indent=0),
                       encoding="utf-8")
        tmp.replace(self.arquivo)

    def anotar(self, em: str, quem: str, protocolo: str, lista: str, campo: str, de: str, para: str) -> None:
        self.alteracoes.append([em, quem, protocolo, lista, campo, de, para])


def anotar_planilha(manuais, historico: Historico, lista: str, mudancas: list[tuple[str, str, str]]) -> None:
    """Observações editadas direto na planilha ANALISTAS: (protocolo, de, para) entram no histórico."""
    agora = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")
    for protocolo, de, para in mudancas:
        _marcar(manuais, protocolo, agora, QUEM_PLANILHA)
        historico.anotar(agora, QUEM_PLANILHA, protocolo, lista, "obs", de, para)


# ----------------------------------------------------------------------------- arquivos salvos pela página

def eh_arquivo(inicio: bytes) -> bool:
    """O começo de um arquivo indica alterações salvas pela página?"""
    return bool(_MARCA.match(inicio[:800].removeprefix(b"\xef\xbb\xbf")))


def _ler(caminho: Path) -> dict:
    conteudo = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(conteudo, dict) or conteudo.get("tipo") != TIPO_ARQUIVO or not isinstance(conteudo.get("alteracoes"), list):
        raise ValueError("não é um arquivo de alterações do acompanhamento")
    return conteudo


def _valor(campo: str, bruto) -> str | None:
    """Valor como fica guardado; None = inválido."""
    valor = texto(bruto).replace("\r\n", "\n").strip()[:LIMITE_TEXTO]
    if campo == "prazo" and valor:
        d = _como_data(valor)
        return d.isoformat() if d else None
    if campo == "situacao" and valor and valor not in SITUACOES:
        return None
    if campo in ("analista", "proxima"):
        return trim(valor.replace("\n", " "))
    return valor


def aplicar(arquivos: list[Path], manuais, historico: Historico, arquivo_registro: Path | None, log) -> list[Path]:
    """Incorpora as alterações salvas pela página, na ordem em que foram feitas (a mais recente prevalece).

    Devolve os arquivos que já podem sair da entrada: incorporados agora, já incorporados antes ou com defeito
    (estes ficam registrados como IGNORADOS e vão para "processados", sem apagar)."""
    prontos, lidos = [], []
    for caminho in arquivos:
        try:
            conteudo = _ler(caminho)
        except (OSError, ValueError) as e:
            log.warning("Acompanhamento: %s não pôde ser lido (%s); nada foi incorporado dele.", caminho.name, e)
            registro.anotar(arquivo_registro, registro.MANUAL, "PÁGINA", "Acompanhamento dos analistas", "-",
                            "IGNORADO (arquivo com defeito)", caminho.name, log)
            prontos.append(caminho)
            continue
        ident = trim(conteudo.get("id"))
        if ident and ident in historico.arquivos:
            log.info("Acompanhamento: %s já tinha sido incorporado antes.", caminho.name)
            prontos.append(caminho)
            continue
        lidos.append((caminho, conteudo, ident))

    mudancas = []
    for caminho, conteudo, _ in lidos:
        quem = trim(conteudo.get("quem"))[:80] or "(sem nome)"
        salvo = texto(conteudo.get("salvo_em"))
        for a in conteudo["alteracoes"]:
            if isinstance(a, dict):
                em = texto(a.get("em"))
                mudancas.append(((em if _MOMENTO.match(em) else salvo)[:16], quem, a, caminho))
    mudancas.sort(key=lambda m: m[0])

    contagem = {caminho: [set(), 0, 0] for caminho, _, _ in lidos}   # processos, aplicadas, inválidas
    for em, quem, a, caminho in mudancas:
        protocolo, lista, campo = trim(a.get("protocolo")), trim(a.get("lista")).upper(), trim(a.get("campo"))
        valor = _valor(campo, a.get("valor")) if campo in CAMPOS else None
        if valor is None or not _PROTOCOLO.fullmatch(protocolo) or lista not in LISTAS:
            contagem[caminho][2] += 1
            continue
        g = grupo(campo, lista)
        de = manuais.obter(g, protocolo)
        if valor == de:
            continue
        guardado = manuais.dados.setdefault(g, {})
        if valor:
            guardado[protocolo] = valor
        else:
            guardado.pop(protocolo, None)
        _marcar(manuais, protocolo, em, quem)
        historico.anotar(em, quem, protocolo, lista, campo, de, valor)
        contagem[caminho][0].add(protocolo)
        contagem[caminho][1] += 1

    for caminho, conteudo, ident in lidos:
        processos, aplicadas, invalidas = contagem[caminho]
        quem = trim(conteudo.get("quem")) or "sem nome"
        if ident:
            historico.arquivos.append(ident)
        log.info("Acompanhamento: %s (%s): %d alterações em %d processos%s.", caminho.name, quem, aplicadas, len(processos),
                 f"; {invalidas} ignoradas por valor inválido" if invalidas else "")
        registro.anotar(arquivo_registro, registro.MANUAL, "PÁGINA", "Acompanhamento dos analistas", len(processos),
                        f"importado: {aplicadas} alterações ({quem})", caminho.name, log)
        prontos.append(caminho)
    return prontos


# ----------------------------------------------------------------------------- a página

def _linhas_pagina(listas: list[tuple[str, list]], manuais) -> list[list[str]]:
    """Um item por processo, na ordem das colunas que a página espera (ver `P` no modelo)."""
    saida, vistos = [], {}
    for nome_lista, processos in listas:
        for l in processos:
            v, numero = l.v, l.numero
            if not numero:
                continue
            tarefa = trim(v[I.L_TAREFA])
            if numero in vistos:   # o mesmo processo em mais de uma tarefa: um item só, com as tarefas juntas
                anterior = vistos[numero]
                if tarefa and tarefa not in anterior[6].split("; "):
                    anterior[6] = f"{anterior[6]}; {tarefa}".strip("; ")
                continue
            abertura = _como_data(v[I.E_ABERTURA])
            linha = [nome_lista, numero, trim(v[I.AF]), trim(v[I.I_NOME]), trim(v[10]), trim(v[I.H_EVENTO]), tarefa, trim(v[15]),
                     abertura.isoformat() if abertura else "", trim(v[I.AE]), trim(v[I.AG]),
                     manuais.obter(CAMPOS["analista"], numero), manuais.obter(CAMPOS["situacao"], numero),
                     manuais.obter(CAMPOS["proxima"], numero), manuais.obter(CAMPOS["prazo"], numero),
                     manuais.obter(grupo("obs", nome_lista), numero),
                     manuais.obter(GRUPO_ATUALIZADO, numero), manuais.obter(GRUPO_ATUALIZADO_POR, numero)]
            vistos[numero] = linha
            saida.append(linha)
    return saida


def gerar_pagina(destino: Path, listas: list[tuple[str, list]], manuais, historico: Historico) -> collections.Counter:
    """Grava a página e devolve quantos processos há em cada pendência (para o log)."""
    agora = datetime.datetime.now()
    processos = _linhas_pagina(listas, manuais)
    analistas = sorted({p[7] for p in processos if p[7]} | {p[11] for p in processos if p[11]}, key=str.upper)
    pessoas = sorted(set(analistas) | {a[1] for a in historico.alteracoes if a[1] and a[1] != QUEM_PLANILHA}, key=str.upper)
    dados = {
        "gerado": agora.strftime("%d/%m/%Y %H:%M"),
        "gerado_iso": agora.strftime("%Y-%m-%dT%H:%M:%S"),
        "logo": _logo(),
        "tipo": TIPO_ARQUIVO,
        "prefixo": PREFIXO_ARQUIVO,
        "situacoes": SITUACOES,
        "concluido": CONCLUIDO,
        "analistas": analistas,
        "pessoas": pessoas,
        "processos": processos,
        "historico": sorted(historico.alteracoes, key=lambda a: a[0], reverse=True)[:HISTORICO_NA_PAGINA],
        "arquivos": historico.arquivos[-500:],
    }
    # "</" não pode aparecer dentro de <script>; "<\/" é o mesmo texto para o JSON.
    embutido = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(MODELO.read_text(encoding="utf-8").replace("__DADOS__", embutido), encoding="utf-8")
    temporario.replace(destino)
    hoje = agora.date()
    return collections.Counter(pendencia(p[12], p[14], hoje) for p in processos)
