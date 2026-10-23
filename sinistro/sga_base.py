"""Base de eventos do SGA: colunas da aba SGA, leitura do relatório exportado e mescla com a API."""
from __future__ import annotations

import collections
import datetime
import html
import json
import re
from pathlib import Path

from .util import NBSP, chave_cabecalho, data_br, sem_acento, texto

# (cabeçalho gravado na aba SGA, padrão do cabeçalho do relatório já reduzido por chave_cabecalho)
COLUNAS = [
    ("PROTOCOLO", r"PROTOCOLO"),
    ("TIPO EVENTO", r"TIPOEVENTO"),
    ("MOTIVO EVENTO", r"MOTIVOEVENTO"),
    ("NOME ASSOCIADO", r"NOMEASSOCIADO"),
    ("PLACA", r"PLACA"),
    ("ASSOCIADO CIDADE", r"ASSOCIADOCIDADE"),
    ("ASSOCIADO ESTADO", r"ASSOCIADOESTADO"),
    ("NOME TERCEIRO", r"NOMETERCEIRO"),
    ("PLACA TERCEIRO", r"PLACATERCEIRO"),
    ("ANALISTA RESPONSAVEL", r"ANALISTARESPONSAVEL"),
    ("DATA COMUNICADO EVENTO", r"DATACOMUNICADOEVENTO"),
    ("DATA DA ANALISE DO REGULADOR", r"DATADAANALISEDOREGULADOR"),
    ("DATA DA AUTORIZACAO", r"DATADAAUTORIZACAO"),
    ("DATA DA ENTREGA DO VEICULO", r"DATADAENTREGADOVE.*ULO"),
    ("DATA DA REGULACAO / ENVIO PARA OFICINA", r"DATADAREGULACAOENVIOPARAOFICINA"),
    ("DATA DE ENTREGA DA DOCUMENTACAO COMPLETA", r"DATADEENTREGADADOCUMENTACAOCOMPLETA"),
    ("DATA ENTRADA OFICINA", r"DATAENTRADAOFICINA"),
    ("DATA INICIO REPARO", r"DATAINICIOREPARO"),
    ("SITUACAO EVENTO", r"SITUACAOEVENTO"),
    ("VISTORIADOR", r"VISTORIADOR"),
    ("NOME FORNECEDOR", r"NOMEFORNECEDOR"),
    ("OFICINAS", r"CONTATO|OFICINAS"),
    ("CNPJ", r"CNPJ"),
    ("VOLUNTARIO", r"VOLUNTARIO"),
    ("COOPERATIVA", r"COOPERATIVA"),
    ("MOTIVO NEGADO", r"CLASSIFICACAO|MOTIVONEGADO"),
    ("DATA EVENTO", r"DATAEVENTO"),
    ("PARTICIPAÇÃO", r"PARTICIPACAO"),
    ("AÇÕES", None),
]
N_COLUNAS = len(COLUNAS)

(PROTOCOLO, TIPO, MOTIVO, NOME_ASSOCIADO, PLACA, CIDADE, UF, NOME_TERCEIRO, PLACA_TERCEIRO, ANALISTA,
 DT_COMUNICADO, DT_ANALISE, DT_AUTORIZACAO, DT_ENTREGA, DT_REGULACAO, DT_DOCUMENTACAO, DT_ENTRADA_OFICINA,
 DT_INICIO_REPARO, SITUACAO, VISTORIADOR, FORNECEDOR, OFICINAS, CNPJ, VOLUNTARIO, COOPERATIVA,
 CLASSIFICACAO, DT_EVENTO, PARTICIPACAO, ACOES) = range(N_COLUNAS)

# Colunas que a API (listar/evento + fornecedores + vistoriadores) preenche.
CAMPOS_API = [TIPO, MOTIVO, NOME_ASSOCIADO, PLACA, CIDADE, UF, NOME_TERCEIRO, PLACA_TERCEIRO, ANALISTA, DT_COMUNICADO,
              DT_ANALISE, DT_AUTORIZACAO, DT_ENTREGA, DT_REGULACAO, DT_DOCUMENTACAO, DT_ENTRADA_OFICINA, DT_INICIO_REPARO,
              SITUACAO, VISTORIADOR, FORNECEDOR, OFICINAS, CNPJ, VOLUNTARIO, COOPERATIVA, CLASSIFICACAO, DT_EVENTO, PARTICIPACAO]
# Identificam o evento e formam a chave que liga ao SIGA: numa linha que já existe, a API não os sobrescreve.
CAMPOS_IDENTIDADE = {TIPO, NOME_ASSOCIADO, PLACA, CIDADE, UF, NOME_TERCEIRO, PLACA_TERCEIRO, DT_COMUNICADO, DT_EVENTO}
_DATAS_PROCESSO = range(DT_ANALISE, DT_INICIO_REPARO + 1)

_TAG = re.compile(r"<[^>]+>")
_BRANCOS = re.compile(r"\s+")


def mapear_cabecalhos(cabecalhos: list) -> dict[int, int]:
    """Posição no arquivo -> posição na aba SGA, pelo nome da coluna (a ordem do layout pode mudar)."""
    mapa: dict[int, int] = {}
    usados: set[int] = set()
    for pos, cab in enumerate(cabecalhos):
        chave = chave_cabecalho(cab)
        if not chave:
            continue
        for destino, (_, padrao) in enumerate(COLUNAS):
            if padrao and destino not in usados and re.fullmatch(padrao, chave):
                mapa[pos] = destino
                usados.add(destino)
                break
    return mapa


def coluna_de_processo(nome) -> int | None:
    """'DATA DE ENTREGA DA DOCUMENTACAO COMPLETA' (processos_data da API) -> coluna da data na aba SGA."""
    chave = chave_cabecalho(nome)
    return next((c for c in _DATAS_PROCESSO if re.fullmatch(COLUNAS[c][1], chave)), None)


def _validar_mapa(mapa: dict[int, int], origem: str) -> None:
    if PROTOCOLO not in mapa.values() or len(mapa) < 10:
        raise ValueError(f"{origem}: não reconheci as colunas do relatório de eventos do SGA.")


def _limpar_celula(bruto: str) -> str:
    return _BRANCOS.sub(" ", html.unescape(_TAG.sub("", bruto)).replace(NBSP, " ")).strip()


def ler_relatorio_html(caminho: Path) -> tuple[list[list[str]], list[str]]:
    """Lê o relatorio.xls do SGA (que é um HTML). Devolve (linhas, colunas não reconhecidas)."""
    conteudo = Path(caminho).read_bytes().decode("utf-8", "replace")
    cab = re.search(r"<thead[^>]*>(.*?)</thead>", conteudo, re.S | re.I)
    if not cab:
        raise ValueError(f"{caminho}: não encontrei o cabeçalho da tabela.")
    cabecalhos = [_limpar_celula(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", cab.group(1), re.S | re.I)]
    mapa = mapear_cabecalhos(cabecalhos)
    _validar_mapa(mapa, str(caminho))
    ignoradas = [c for i, c in enumerate(cabecalhos) if i not in mapa and chave_cabecalho(c) != "ACOES"]
    corpo = re.search(r"<tbody[^>]*>(.*)</tbody>", conteudo, re.S | re.I)
    linhas: list[list[str]] = []
    for trecho in (corpo.group(1) if corpo else conteudo[cab.end():]).split("</tr>"):
        celulas = re.findall(r"<td[^>]*>(.*?)</td>", trecho, re.S | re.I)
        if not celulas:
            continue
        linha = [""] * N_COLUNAS
        for pos, destino in mapa.items():
            if pos < len(celulas):
                linha[destino] = _limpar_celula(celulas[pos])
        if linha[PROTOCOLO]:
            linhas.append(linha)
    return linhas, ignoradas


def linhas_de_tabela(tabela: list[list], origem: str) -> list[list[str]]:
    """Converte uma tabela (aba SGA de uma planilha) com cabeçalho na 1ª linha em linhas da base."""
    if not tabela:
        return []
    mapa = mapear_cabecalhos(tabela[0][:N_COLUNAS + 6])
    _validar_mapa(mapa, origem)
    linhas = []
    for bruta in tabela[1:]:
        linha = [""] * N_COLUNAS
        for pos, destino in mapa.items():
            if pos < len(bruta):
                linha[destino] = _BRANCOS.sub(" ", texto(bruta[pos]).replace(NBSP, " ")).strip()
        if linha[PROTOCOLO]:
            linhas.append(linha)
    return linhas


def _comparavel(v: str) -> str:
    return sem_acento(v).upper().strip()


class BaseSga:
    """Eventos do SGA guardados em dados/sga.json entre uma execução e outra."""

    def __init__(self, pasta_dados: Path):
        self.arquivo = pasta_dados / "sga.json"
        self.linhas: list[list[str]] = []
        self.origem = ""

    def carregar(self) -> bool:
        if not self.arquivo.exists():
            return False
        dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        self.linhas = [(l + [""] * N_COLUNAS)[:N_COLUNAS] for l in dados["linhas"]]
        self.origem = dados.get("origem", "")
        return True

    def salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        dados = {"atualizado_em": datetime.datetime.now().isoformat(timespec="seconds"),
                 "origem": self.origem, "colunas": [c for c, _ in COLUNAS], "linhas": self.linhas}
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo)

    def substituir(self, linhas: list[list[str]], origem: str) -> None:
        self.linhas = linhas
        self.origem = origem

    def aplicar_api(self, itens: list[list[str]], data_inicial: datetime.date, log) -> dict:
        """Mescla os eventos vindos da API na base.

        - Protocolo que ainda não existe na base: entra como linha nova (só com as colunas da API).
        - Protocolo já existente: atualiza as colunas da API na linha correspondente (mesmo tipo de
          evento), exceto as de identidade (nome, placa, tipo, datas do evento), que ligam ao SIGA.
        - Antes de atualizar, cada coluna é conferida contra a base: se a API devolver a coluna em
          outro formato (poucos valores iguais), ela não é usada, nem nas linhas novas.
        """
        por_protocolo: dict[str, list[int]] = collections.defaultdict(list)
        for i, linha in enumerate(self.linhas):
            por_protocolo[linha[PROTOCOLO]].append(i)
        api_por_protocolo: dict[str, list[list[str]]] = collections.defaultdict(list)
        for item in itens:
            if item[PROTOCOLO]:
                api_por_protocolo[item[PROTOCOLO]].append(item)

        pares: list[tuple[int, list[str]]] = []
        novos: list[list[str]] = []
        ambiguos = 0
        for protocolo, itens_api in api_por_protocolo.items():
            indices = por_protocolo.get(protocolo)
            if not indices:
                novos.extend(itens_api)
                continue
            base_por_tipo = collections.defaultdict(list)
            for i in indices:
                base_por_tipo[_comparavel(self.linhas[i][TIPO])].append(i)
            api_por_tipo = collections.defaultdict(list)
            for item in itens_api:
                api_por_tipo[_comparavel(item[TIPO])].append(item)
            for tipo, lista in api_por_tipo.items():
                if len(lista) == 1 and len(base_por_tipo.get(tipo, [])) == 1:
                    pares.append((base_por_tipo[tipo][0], lista[0]))
                else:
                    ambiguos += len(lista)

        # Confere, coluna a coluna, se a API fala a mesma "língua" do relatório.
        compativeis: list[int] = []
        incompativeis: dict[str, str] = {}
        for campo in CAMPOS_API:
            iguais = total = 0
            exemplo = ""
            for i, item in pares:
                a, b = _comparavel(self.linhas[i][campo]), _comparavel(item[campo])
                if a and b:
                    total += 1
                    if a == b:
                        iguais += 1
                    elif not exemplo:
                        exemplo = f"relatório='{self.linhas[i][campo]}' / API='{item[campo]}'"
            if total >= 30 and iguais / total < 0.6:
                incompativeis[COLUNAS[campo][0]] = f"{iguais}/{total} iguais; ex.: {exemplo}"
            else:
                compativeis.append(campo)
        for nome, detalhe in incompativeis.items():
            log.warning("API: coluna %s veio em formato diferente do relatório e não foi atualizada (%s)", nome, detalhe)

        alteradas = collections.Counter()
        atualizaveis = [c for c in compativeis if c not in CAMPOS_IDENTIDADE]
        for i, item in pares:
            linha = self.linhas[i]
            for campo in atualizaveis:
                if item[campo] and _comparavel(item[campo]) != _comparavel(linha[campo]):
                    linha[campo] = item[campo]
                    alteradas[COLUNAS[campo][0]] += 1

        incluidos = 0
        descartar = [c for c in CAMPOS_API if c not in compativeis]
        novos.sort(key=lambda l: (data_br(l[DT_COMUNICADO]) or datetime.date.max, l[PROTOCOLO]))
        for item in novos:
            for campo in descartar:  # formato diferente do relatório: melhor vazio que errado
                item[campo] = ""
            comunicado = data_br(item[DT_COMUNICADO])
            if comunicado is None or comunicado >= data_inicial:
                self.linhas.append(item)
                incluidos += 1
        return {"novos": incluidos, "alteracoes": dict(alteradas), "ambiguos": ambiguos,
                "incompativeis": list(incompativeis)}
