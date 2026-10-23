"""Planilhas dos setores no Google Sheets (modo híbrido).

Para cada lista, o sistema grava uma aba fixa com os valores já calculados e mantém a coluna digitada pela
equipe, guardada por processo em dados/manuais.json, como nas planilhas .xlsx:

    ANALISTAS    ANALISTAS, VIDROS     criadas pelo sistema na primeira vez, no lugar das cópias diárias
                                       ("16/10 ANALISTAS", "VIDROS 16/10"), de onde vêm as observações iniciais
    CONSULTORES  CONSULTORES TEC.      consultor técnico calculado pela tabela Oficinas
    REGULADORES  REGULADORES, VISTORIA INICIAL, NEGADOS EM ABERTO, NEGADOS FINALIZADOS

Ficam como estão as abas com fórmulas ou digitação da equipe (Oficinas, Oficinas por Consultor, OFICINAS,
VISTORIA PRESENCIAL, REGULADORES ANALISTA) e o HISTÓRICO REGULARIZAÇÕES, mantido pela rotina da própria planilha.
"""
from __future__ import annotations

import re

from . import acompanhamento as A
from . import planilha as P
from . import setores as S
from .google_planilhas import GoogleErro, PlanilhaGoogle  # noqa: F401  (GoogleErro é tratado em setores.atualizar)

_COPIA = {S.ABA_ANALISTAS: re.compile(r"\d{1,2}/\d{1,2}\s*ANALISTAS", re.I),
          S.ABA_VIDROS: re.compile(r"VIDROS\s*\d{1,2}/\d{1,2}", re.I)}
COLUNAS_SETOR = "A:AT"


def _garantir_aba(planilha: PlanilhaGoogle, nome: str, cabecalho: list[str], manuais: tuple = (), indice: int = 0,
                  titulos: list[list] | None = None) -> bool:
    """Cria a aba se não existir (devolve True); se existir, só completa os títulos que faltam."""
    if planilha.aba(nome):
        planilha.completar_cabecalho(nome, cabecalho)
        return False
    planilha.criar_aba(nome, S._titulos(titulos, cabecalho, S.N_SIGA) if titulos else cabecalho, manuais=manuais, indice=indice)
    return True


def consultores(ctx: S.Contexto, planilha: PlanilhaGoogle) -> None:
    grupo = f"{S.ABA_CONSULTORES}/OBSERVAÇÃO"
    cabecalho = P.CABECALHO_SIGA[:S.N_SIGA] + ["CONSULTOR TECNICO", "OBSERVAÇÃO"]
    atual = planilha.ler_abas({S.ABA_CONSULTORES: COLUNAS_SETOR, S.ABA_OFICINAS: "A:L"})
    if atual[S.ABA_CONSULTORES] is not None:
        ctx.manuais.colher(grupo, S._pares(atual[S.ABA_CONSULTORES], S.N_SIGA + 1))
    _garantir_aba(planilha, S.ABA_CONSULTORES, cabecalho, manuais=(S.N_SIGA + 1,))
    if atual[S.ABA_OFICINAS] is None:
        ctx.log.warning("%s: sem a aba %s; o consultor técnico fica NÃO ENCONTRADO.", planilha.titulo, S.ABA_OFICINAS)
    por_cnpj = S.consultores_por_cnpj(S.tabela_oficinas(atual[S.ABA_OFICINAS]))
    linhas = S._linhas_aba(ctx.linhas, S.eh_consultores,
                           lambda l: [S.consultor_da_linha(l, por_cnpj), ctx.manuais.obter(grupo, l.numero)], valores=True)
    planilha.substituir_aba(S.ABA_CONSULTORES, linhas, len(cabecalho), S._formatos_setor())
    celulas = planilha.salvar()
    sem = sum(1 for l in linhas if l[S.N_SIGA] == "NÃO ENCONTRADO")
    ctx.log.info("%s (Google): %s %d linhas (%d sem consultor técnico); %d células gravadas.",
                 planilha.titulo, S.ABA_CONSULTORES, len(linhas), sem, celulas)


def analistas(ctx: S.Contexto, planilha: PlanilhaGoogle) -> None:
    grupos = {S.ABA_ANALISTAS: f"{S.ABA_ANALISTAS}/OBSERVAÇÃO", S.ABA_VIDROS: f"{S.ABA_VIDROS}/OBSERVAÇÃO"}
    cabecalho = P.CABECALHO_SIGA[:S.N_SIGA] + ["PARTICIPAÇÃO", "OBSERVAÇÃO"]
    # Na primeira vez as abas fixas não existem: as observações vêm da cópia diária mais recente.
    leitura, origem = {}, {}
    for aba in grupos:
        if planilha.aba(aba):
            leitura[aba] = COLUNAS_SETOR
        else:
            copia = planilha.aba_por_padrao(_COPIA[aba])
            if copia:
                origem[aba] = copia
                leitura[copia] = COLUNAS_SETOR
    atual = planilha.ler_abas(leitura)
    for indice, (aba, grupo) in enumerate(grupos.items()):
        if aba not in origem and planilha.aba(aba):
            # Vale só o que foi editado na aba desde a última gravação (a página de acompanhamento também muda a observação).
            referencia = ctx.manuais.referencia(grupo)
            mudou = ctx.manuais.colher_edicoes(grupo, S._pares(atual[aba], S.N_SIGA + 1), referencia)
            if mudou and ctx.historico is not None:
                A.anotar_planilha(ctx.manuais, ctx.historico, aba,
                                  [(c, referencia.get(c, ""), ctx.manuais.obter(grupo, c)) for c in mudou])
            continue
        tabela = atual.get(origem.get(aba, ""))
        if tabela:
            ctx.manuais.colher(grupo, S._pares(tabela, S.N_SIGA + 1))
        _garantir_aba(planilha, aba, cabecalho, manuais=(S.N_SIGA + 1,), indice=indice, titulos=tabela)
        if tabela:
            # A cópia diária deixa de ser atualizada: fica oculta para ninguém trabalhar nela por engano.
            planilha.ocultar_aba(origem[aba])
            ctx.log.info("%s (Google): aba %s criada; observações trazidas da aba '%s', que foi ocultada.",
                         planilha.titulo, aba, origem[aba])

    def extras(grupo):
        return lambda l: [l.v[S.AP_PARTICIPACAO], ctx.manuais.obter(grupo, l.numero)]

    processos = dict(S.processos_analistas(ctx.linhas))
    linhas_analistas = S._linhas_aba(ctx.linhas, S._eh_analistas, extras(grupos[S.ABA_ANALISTAS]), valores=True)
    linhas_vidros = S._linhas_aba(ctx.linhas, S._eh_vidros, extras(grupos[S.ABA_VIDROS]), valores=True)
    planilha.substituir_aba(S.ABA_ANALISTAS, linhas_analistas, len(cabecalho), S._formatos_setor())
    planilha.substituir_aba(S.ABA_VIDROS, linhas_vidros, len(cabecalho), S._formatos_setor())
    celulas = planilha.salvar()
    for aba, grupo in grupos.items():
        ctx.manuais.gravou(grupo, (l.numero for l in processos[aba]))
    ctx.log.info("%s (Google): %s %d linhas; %s %d linhas; %d células gravadas.", planilha.titulo, S.ABA_ANALISTAS,
                 len(linhas_analistas), S.ABA_VIDROS, len(linhas_vidros), celulas)


def reguladores(ctx: S.Contexto, planilha: PlanilhaGoogle, base_vistoria: list[list] | None) -> None:
    grupo = f"{S.ABA_REGULADORES}/REGULARIZADO POR"
    cab_reguladores = P.CABECALHO_SIGA[:S.N_SIGA] + ["REGULARIZADO POR"]
    cab_vistoria = P.CABECALHO_SIGA[:S.N_SIGA] + ["DATA DA REGULAGEM", "MES REFERENCIA"]
    cab_negados = P.CABECALHO_SIGA[:S.N_SIGA]
    atual = planilha.ler_abas({S.ABA_REGULADORES: COLUNAS_SETOR})
    if atual[S.ABA_REGULADORES] is not None:
        ctx.manuais.colher(grupo, S._pares(atual[S.ABA_REGULADORES], S.N_SIGA, com_tarefa=True))
    for aba, cabecalho, manuais in ((S.ABA_REGULADORES, cab_reguladores, (S.N_SIGA,)), (S.ABA_VISTORIA_INICIAL, cab_vistoria, ()),
                                    (S.ABA_NEGADOS_ABERTO, cab_negados, ()), (S.ABA_NEGADOS_FINALIZADOS, S.CAB_FINALIZADOS, ())):
        _garantir_aba(planilha, aba, cabecalho, manuais=manuais)
    if base_vistoria is None:
        ctx.log.warning("%s: a aba %s do sinistro no Google não foi lida; DATA DA REGULAGEM fica em branco.",
                        planilha.titulo, S.ABA_BASE_VISTORIA)
    regulagem = S.regulagens(base_vistoria)

    reguladores_ = S._linhas_aba(ctx.linhas, S.eh_reguladores, lambda l: [ctx.manuais.obter(grupo, f"{l.numero}|{l.tarefa}")],
                                 valores=True)
    vistoria = S._linhas_aba(ctx.linhas, S.eh_vistoria, lambda l: S.extras_vistoria(l, regulagem), valores=True)
    abertos = S._linhas_aba(ctx.linhas, S.eh_negado_aberto, lambda l: [], valores=True)
    finalizados = S._negados_finalizados(ctx)
    planilha.substituir_aba(S.ABA_REGULADORES, reguladores_, len(cab_reguladores), S._formatos_setor())
    planilha.substituir_aba(S.ABA_VISTORIA_INICIAL, vistoria, len(cab_vistoria),
                            S._formatos_setor({S.N_SIGA: S.FMT_DATA, S.N_SIGA + 1: S.FMT_MES}))
    planilha.substituir_aba(S.ABA_NEGADOS_ABERTO, abertos, len(cab_negados), S._formatos_setor())
    planilha.substituir_aba(S.ABA_NEGADOS_FINALIZADOS, finalizados, len(S.CAB_FINALIZADOS), {6: S.FMT_DATA, 7: S.FMT_DATA})
    celulas = planilha.salvar()
    ctx.log.info("%s (Google): %s %d; %s %d (%d com regulagem); %s %d; %s %d; %d células gravadas.", planilha.titulo,
                 S.ABA_REGULADORES, len(reguladores_), S.ABA_VISTORIA_INICIAL, len(vistoria), sum(1 for l in vistoria if l[S.N_SIGA]),
                 S.ABA_NEGADOS_ABERTO, len(abertos), S.ABA_NEGADOS_FINALIZADOS, len(finalizados), celulas)
