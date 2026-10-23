"""Base da aba INTEGRAÇÃO: leitura do "DashBoard SIGA" exportado e histórico acumulado."""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

from .util import chave_cabecalho, data_br, texto

COLUNAS = ["Numero", "Integração", "Origem", "Regional", "Cooperativa", "Situação Evento", "Proprietário",
           "Estado", "Tipo Veic.", "Cobertura", "Placa", "Chassi", "Cadastro", "Abertura", "Entrada Oficina",
           "Liberação", "Regulador", "Duração", "Oficina"]
N_COLUNAS = len(COLUNAS)

(NUMERO, INTEGRACAO, ORIGEM, REGIONAL, COOPERATIVA, SITUACAO, PROPRIETARIO, ESTADO, TIPO_VEICULO, COBERTURA,
 PLACA, CHASSI, CADASTRO, ABERTURA, ENTRADA_OFICINA, LIBERACAO, REGULADOR, DURACAO, OFICINA) = range(N_COLUNAS)

COLUNAS_DATA = (CADASTRO, ABERTURA, ENTRADA_OFICINA, LIBERACAO)
_CHAVES = [chave_cabecalho(c) for c in COLUNAS]
_NUMERO = re.compile(r"^\d{4}-\d{3,}$")


def _valor(coluna: int, v):
    """Datas ficam guardadas como 'aaaa-mm-dd'; duração como número; o resto como texto."""
    if coluna in COLUNAS_DATA:
        d = data_br(v)
        return d.isoformat() if d else texto(v).strip()
    if coluna == DURACAO:
        s = texto(v).strip()
        return int(s) if re.fullmatch(r"-?\d+", s) else s
    return texto(v).strip()


def linhas_de_tabela(tabela: list[list], origem: str) -> list[list]:
    """Extrai os eventos de uma tabela do SIGA (DashBoard exportado ou aba INTEGRAÇÃO).

    O cabeçalho é procurado nas primeiras linhas; linhas de grupo/total (sem número de evento
    no formato 2026-00123) são descartadas.
    """
    for i, linha in enumerate(tabela[:15]):
        chaves = [chave_cabecalho(c) for c in linha]
        if "NUMERO" in chaves and "INTEGRACAO" in chaves:
            mapa = {}
            for destino, chave in enumerate(_CHAVES):
                if chave in chaves:
                    mapa[chaves.index(chave)] = destino
            inicio = i + 1
            break
    else:
        raise ValueError(f"{origem}: não encontrei o cabeçalho (Numero / Integração) do DashBoard SIGA.")
    linhas = []
    for bruta in tabela[inicio:]:
        linha: list = [""] * N_COLUNAS
        for pos, destino in mapa.items():
            if pos < len(bruta):
                linha[destino] = _valor(destino, bruta[pos])
        if _NUMERO.match(linha[NUMERO]):
            linhas.append(linha)
    return linhas


# ----------------------------------------------------------------------------- relatório de tarefas (atribuições)
# Exportação das tarefas em aberto do SIGA ("Exported data"): é o que a equipe cola nas colunas B a W da aba SIGA.
COLUNAS_TAREFAS = ["1", "#", "Número", "Data abertura", "Dias em aberto", "Cobertura", "Evento", "Nome", "Veículo", "Placa",
                   "Tarefa", "Data início", "Data término", "Dias em atraso", "Responsável", "Oficina", "Data entrada oficina",
                   "Data início reparo", "Data liberação", "Total rateio", "Tipo Veículo", "Associação"]
DATAS_TAREFAS = (3, 11, 12, 16, 17, 18)   # abertura, início, término, entrada oficina, início reparo, liberação
NUMEROS_TAREFAS = (0, 1, 4, 13)           # 1, #, dias em aberto, dias em atraso


def _cabecalho_tarefas(tabela: list[list]) -> int | None:
    for i, linha in enumerate(tabela[:15]):
        chaves = {chave_cabecalho(c) for c in linha}
        if {"NUMERO", "TAREFA", "RESPONSAVEL"} <= chaves and "INTEGRACAO" not in chaves:
            return i
    return None


def eh_relatorio_tarefas(tabela: list[list]) -> bool:
    return _cabecalho_tarefas(tabela) is not None


def _valor_tarefa(coluna: int, v):
    s = texto(v).strip()
    if s == "":
        return None
    if coluna in DATAS_TAREFAS:
        return data_br(v) or s
    if coluna in NUMEROS_TAREFAS:
        return int(s) if re.fullmatch(r"-?\d+", s) else s
    return s


def linhas_de_tarefas(tabela: list[list], origem: str) -> list[list]:
    """Relatório de tarefas do SIGA -> linhas com as 22 colunas B..W da aba SIGA (datas como data, contagens como número)."""
    inicio = _cabecalho_tarefas(tabela)
    if inicio is None:
        raise ValueError(f"{origem}: não encontrei o cabeçalho (Número / Tarefa / Responsável) do relatório de tarefas do SIGA.")
    brutos = [texto(c).strip() for c in tabela[inicio]]
    chaves = [chave_cabecalho(c) for c in tabela[inicio]]
    posicao = {}
    for destino, nome in enumerate(COLUNAS_TAREFAS):
        alvo = chave_cabecalho(nome)
        if alvo and alvo in chaves:
            posicao[destino] = chaves.index(alvo)
        elif not alvo and nome in brutos:   # "#": só símbolo, compara o texto
            posicao[destino] = brutos.index(nome)
    linhas = []
    for bruta in tabela[inicio + 1:]:
        linha = [None] * len(COLUNAS_TAREFAS)
        for destino, pos in posicao.items():
            if pos < len(bruta):
                linha[destino] = _valor_tarefa(destino, bruta[pos])
        if _NUMERO.match(texto(linha[2]).strip()):
            linhas.append(linha)
    return linhas


class BaseIntegracao:
    """Histórico do SIGA guardado em dados/integracao.json entre uma execução e outra."""

    def __init__(self, pasta_dados: Path):
        self.arquivo = pasta_dados / "integracao.json"
        self.linhas: list[list] = []
        self.anos: dict[str, str] = {}  # ano do evento -> data (aaaa-mm-dd) do último DashBoard que trouxe esse ano

    def carregar(self) -> bool:
        if not self.arquivo.exists():
            return False
        dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.linhas = [(l + [""] * N_COLUNAS)[:N_COLUNAS] for l in dados["linhas"]]
        self.anos = dados.get("anos", {})
        return True

    def salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        dados = {"atualizado_em": datetime.datetime.now().isoformat(timespec="seconds"), "anos": self.anos,
                 "colunas": COLUNAS, "linhas": self.linhas}
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo)

    def incorporar(self, linhas: list[list], marcar_anos: bool = True) -> tuple[int, int]:
        """Atualiza os eventos já existentes (pelo Numero) e acrescenta os novos. Nada é removido.
        `marcar_anos`: conta como exportação do DashBoard (a aba INTEGRAÇÃO do Google não conta)."""
        posicao = {l[NUMERO]: i for i, l in enumerate(self.linhas)}
        novos = alterados = 0
        hoje = datetime.date.today().isoformat()
        for ano in {l[NUMERO][:4] for l in linhas} if marcar_anos else ():
            self.anos[ano] = hoje
        for linha in linhas:
            i = posicao.get(linha[NUMERO])
            if i is None:
                posicao[linha[NUMERO]] = len(self.linhas)
                self.linhas.append(linha)
                novos += 1
            elif self.linhas[i] != linha:
                self.linhas[i] = linha
                alterados += 1
        return novos, alterados

    def cobertura(self, ano_inicial: int, ano_final: int) -> tuple[list[str], list[str]]:
        """(anos já atualizados por DashBoard, com a data; anos que ainda nunca foram) no intervalo."""
        feitos, faltam = [], []
        for ano in map(str, range(ano_inicial, ano_final + 1)):
            if ano in self.anos:
                feitos.append(f"{ano} em {datetime.date.fromisoformat(self.anos[ano]):%d/%m/%Y}")
            else:
                faltam.append(ano)
        return feitos, faltam
