"""Cruzamento SGA x SIGA: calcula em Python o que as fórmulas da planilha faziam.

Aba INTEGRAÇÃO (uma linha por evento do SIGA)
    PROTOCOLO   = primeiro bloco de números da coluna Integração (é o protocolo do SGA)
    PLACA 2     = Placa sem hífen
    COMPETENCIA = competência da linha da aba SIGA com o mesmo protocolo SGA + placa SGA
    chave       = PROTOCOLO|Proprietário|1   (|0 quando a situação é EXCLUIR)

Aba SGA (uma linha por item de evento do SGA)
    NOME        = nome do terceiro, ou do associado quando não há terceiro
    PLACA       = placa do terceiro, ou do associado
    COMPETENCIA = mês/ano da data de comunicado
    chave       = PROTOCOLO|NOME|1
    STATUS SIGA = Situação Evento da INTEGRAÇÃO com a mesma chave

Aba SIGA (preenchida à mão; uma linha por tarefa)
    PROTOCOLO SGA / STATUS SIGA = INTEGRAÇÃO, pelo número do evento no SIGA
    demais colunas = linha da aba SGA com o mesmo protocolo + cobertura (tipo de evento) + nome
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import sga_base as S
from . import siga as G
from .util import competencia, limpar, texto, trim

# Colunas da aba SIGA (letra -> índice a partir de 0).
SIGA_COLUNAS = 45  # A até AS
(A_COMPETENCIA, D_PROTOCOLO_SIGA, E_ABERTURA, G_COBERTURA, H_EVENTO, I_NOME, L_TAREFA) = (0, 3, 4, 6, 7, 8, 11)
(X, Y, Z, AA, AB, AC, AD, AE, AF, AG, AH, AI, AJ, AK, AL, AM, AN, AO, AP, AQ, AR, AS) = range(23, 45)

# Coluna da aba SIGA <- coluna da linha correspondente da aba SGA ("nome"/"placa" são as calculadas).
SIGA_DE_SGA = {
    X: S.ANALISTA, Y: S.DT_COMUNICADO, AA: S.DT_AUTORIZACAO, AC: "placa", AD: S.UF, AE: S.SITUACAO,
    AH: S.CLASSIFICACAO, AK: S.OFICINAS, AL: S.CNPJ, AM: S.VISTORIADOR, AN: S.VOLUNTARIO,
    AO: S.COOPERATIVA, AP: S.PARTICIPACAO, AR: S.CIDADE, AS: S.DT_EVENTO,
}
# Colunas da aba SIGA que o script grava como valor.
SIGA_CALCULADAS = [A_COMPETENCIA, X, Y, AA, AC, AD, AE, AF, AG, AH, AI, AK, AL, AM, AN, AO, AP, AR, AS]
# Colunas da aba SIGA que ficam como fórmula leve (dependem de HOJE() ou da aba TAREFAS).
SIGA_FORMULAS = {
    Z: '=IF(OR(Y{r}="",Y{r}="00/00/0000"),"",IFERROR(NETWORKDAYS(DATE(VALUE(RIGHT(Y{r},4)),VALUE(MID(Y{r},4,2)),VALUE(LEFT(Y{r},2))),TODAY()),""))',
    AB: '=IF(OR(AA{r}="",AA{r}="00/00/0000"),"",IFERROR(NETWORKDAYS(DATE(VALUE(RIGHT(AA{r},4)),VALUE(MID(AA{r},4,2)),VALUE(LEFT(AA{r},2))),TODAY()),""))',
    # O &"" evita que o Excel mostre 0 quando a célula encontrada na aba TAREFAS está vazia.
    AJ: '=IF(L{r}="","SEM TAREFA",IFERROR(VLOOKUP(TRIM(L{r}),TAREFAS!A:B,2,FALSE)&"","SETOR DESCONHECIDO"))',
    AQ: '=IF(L{r}="","SEM TAREFA",IFERROR(VLOOKUP(TRIM(L{r}),TAREFAS!A:C,3,FALSE)&"","SETOR DESCONHECIDO"))',
}

_DIGITOS = re.compile(r"[0-9]+")


@dataclass
class Resultado:
    sga_extra: list[list[str]] = field(default_factory=list)     # por linha do SGA: NOME, PLACA, COMPETENCIA, STATUS SIGA, chave
    integ_extra: list[list[str]] = field(default_factory=list)   # por linha da INTEGRAÇÃO: PROTOCOLO, PLACA 2, COMPETENCIA, chave
    siga: dict[int, dict[int, str]] = field(default_factory=dict)  # nº da linha na aba SIGA -> {coluna: valor}
    sga_por_chave: dict[str, int] = field(default_factory=dict)  # PROTOCOLO|TIPO|NOME (maiúsculas) -> linha do SGA
    resumo: dict = field(default_factory=dict)


FINALIZADOS_COLUNAS = ["Numero", "Origem", "STATUS SIGA", "Nome", "Cobertura", "Placa", "Abertura", "Liberação", "Duração",
                       "Oficina", "PROTOCOLO SGA", "STATUS SGA", "CLASSIFICAÇÃO NEGATIVA", "ESTADO", "COOPERATIVAS", "DATA EVENTO"]
# Anotações da conferência de finalizados (as mesmas que eram escritas à mão na planilha).
PENDENCIAS = {"arquivado": "Verificar", "excluir": "Por que excluir?", "motivo": "Incluir motivo"}


def finalizados(sga: list[list[str]], integ: list[list], resultado: "Resultado", desde, ate=None, com_cidade=False) -> list[list]:
    """Eventos do SIGA com Liberação entre `desde` e `ate`, com a situação do evento no SGA.

    Uma linha por evento, nas colunas de FINALIZADOS_COLUNAS, ordenadas pela data de liberação.
    A busca no SGA é a mesma da aba SIGA: protocolo + cobertura (tipo de evento) + nome.
    """
    inicio, fim = desde.isoformat(), ate.isoformat() if ate else "9999"
    linhas = []
    for linha, extra in zip(integ, resultado.integ_extra):
        liberacao = texto(linha[G.LIBERACAO])
        if not (inicio <= liberacao <= fim):  # datas guardadas como aaaa-mm-dd; vazio fica de fora
            continue
        protocolo = extra[0]
        i = resultado.sga_por_chave.get(
            f"{trim(protocolo).upper()}|{trim(linha[G.COBERTURA]).upper()}|{trim(linha[G.PROPRIETARIO]).upper()}")
        evento = sga[i] if i is not None else None
        nova = [
            linha[G.NUMERO], linha[G.ORIGEM], linha[G.SITUACAO], linha[G.PROPRIETARIO], linha[G.COBERTURA], linha[G.PLACA],
            linha[G.ABERTURA], liberacao, linha[G.DURACAO], linha[G.OFICINA], protocolo,
            evento[S.SITUACAO] if evento else "", evento[S.CLASSIFICACAO] if evento else "", evento[S.UF] if evento else "",
            evento[S.COOPERATIVA] if evento else "", evento[S.DT_EVENTO] if evento else "",
        ]
        if com_cidade:   # colunas extras só para a página de conferência (não afetam quem chama sem o parâmetro)
            nova.append(evento[S.CIDADE] if evento else "")        # índice 16
            nova.append(evento[S.MOTIVO] if evento else "")        # índice 17 (MOTIVO EVENTO: identifica VIDROS)
        linhas.append(nova)
    linhas.sort(key=lambda l: (l[7], l[0]))
    return linhas


def pendencia(status_siga: str, status_sga: str, classificacao: str) -> str:
    """Código da anotação de conferência de um evento finalizado ('' quando não há o que anotar)."""
    siga, sga_ = trim(status_siga).upper(), trim(status_sga).upper()
    if siga == "EXCLUIR":
        return "excluir"
    if siga.startswith("ARQUIVADO"):
        return "arquivado"
    sem_motivo = trim(classificacao).upper().replace("Ã", "A") in ("", "NAO INFORMADO")
    if "NEGADO" in (siga, sga_) and sem_motivo:
        return "motivo"
    return ""


def protocolo_da_integracao(codigo) -> str:
    """'202618615REM3G92' -> '202618615' (protocolo SGA seguido da placa, como o SIGA guarda)."""
    m = _DIGITOS.search(texto(codigo))
    return m.group(0) if m else ""


def calcular(sga: list[list[str]], integ: list[list], siga: list[tuple[int, list]]) -> Resultado:
    """sga/integ: linhas das bases. siga: (nº da linha, valores A..AS) das linhas preenchidas da aba SIGA."""
    res = Resultado()

    # ---- INTEGRAÇÃO: protocolo, placa e chave
    por_numero: dict[str, int] = {}
    status_por_chave: dict[str, str] = {}
    for i, linha in enumerate(integ):
        protocolo = protocolo_da_integracao(linha[G.INTEGRACAO])
        placa = texto(linha[G.PLACA]).replace("-", "")
        excluir = trim(linha[G.SITUACAO]).upper() == "EXCLUIR"
        chave = f"{limpar(protocolo)}|{limpar(linha[G.PROPRIETARIO])}|{'0' if excluir else '1'}" if protocolo else ""
        res.integ_extra.append([protocolo, placa, "", chave])
        por_numero.setdefault(linha[G.NUMERO], i)
        if chave:
            # As buscas da planilha (PROCX) não diferenciam maiúsculas de minúsculas.
            status_por_chave.setdefault(chave.upper(), texto(linha[G.SITUACAO]))

    # ---- SGA: nome, placa, competência, chave e status do SIGA
    por_chave_sga: dict[str, int] = {}
    com_status = 0
    for i, linha in enumerate(sga):
        nome = linha[S.NOME_TERCEIRO] or linha[S.NOME_ASSOCIADO]
        placa = linha[S.PLACA_TERCEIRO] or linha[S.PLACA]
        chave = f"{limpar(linha[S.PROTOCOLO])}|{limpar(nome)}|1"
        status = status_por_chave.get(chave.upper(), "")
        com_status += bool(status)
        res.sga_extra.append([nome, placa, competencia(linha[S.DT_COMUNICADO]), status, chave])
        por_chave_sga.setdefault(f"{trim(linha[S.PROTOCOLO]).upper()}|{trim(linha[S.TIPO]).upper()}|{trim(nome).upper()}", i)

    res.sga_por_chave = por_chave_sga

    # ---- SIGA: busca na INTEGRAÇÃO (pelo número do evento) e no SGA (protocolo + cobertura + nome)
    competencia_por_siga: dict[str, str] = {}
    sem_integracao = sem_sga = 0
    for numero_linha, atual in siga:
        atual = list(atual) + [None] * (SIGA_COLUNAS - len(atual))
        novo: dict[int, str] = {}
        i_integ = por_numero.get(trim(atual[D_PROTOCOLO_SIGA]))
        protocolo_sga = res.integ_extra[i_integ][0] if i_integ is not None else ""
        # Sem vínculo na INTEGRAÇÃO, vale o que já estiver digitado na planilha.
        novo[AF] = protocolo_sga or texto(atual[AF])
        novo[AG] = texto(integ[i_integ][G.SITUACAO]) if i_integ is not None else texto(atual[AG])
        sem_integracao += i_integ is None

        i_sga = por_chave_sga.get(f"{trim(novo[AF]).upper()}|{trim(atual[G_COBERTURA]).upper()}|{trim(atual[I_NOME]).upper()}")
        sem_sga += i_sga is None
        # Sem correspondência no SGA, o que já está na linha só é mantido se pertencer ao mesmo protocolo.
        manter = trim(atual[AF]) == novo[AF]
        for coluna, origem in SIGA_DE_SGA.items():
            if i_sga is None:
                novo[coluna] = texto(atual[coluna]) if manter else ""
            elif origem == "placa":
                novo[coluna] = res.sga_extra[i_sga][1]
            else:
                novo[coluna] = sga[i_sga][origem]
        novo[A_COMPETENCIA] = competencia(novo[Y]) or "Mês não informado"
        novo[AI] = competencia(atual[E_ABERTURA])
        res.siga[numero_linha] = novo
        if novo[AF]:
            competencia_por_siga.setdefault(f"{novo[AF]}|{novo[AC]}".upper(), novo[A_COMPETENCIA])

    # ---- INTEGRAÇÃO: competência vinda da aba SIGA
    for extra in res.integ_extra:
        if extra[0]:
            extra[2] = competencia_por_siga.get(f"{extra[0]}|{extra[1]}".upper(), "")

    res.resumo = {
        "sga_linhas": len(sga), "sga_com_status_siga": com_status, "integracao_linhas": len(integ),
        "siga_linhas": len(siga), "siga_sem_integracao": sem_integracao, "siga_sem_sga": sem_sga,
    }
    return res
