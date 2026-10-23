"""Abastece as planilhas dos setores (ANALISTAS, CONSULTORES TECNICOS e REGULADORES) com o sinistro.

Recalcula os cruzamentos da aba SIGA do sinistro e regrava as abas de trabalho de cada setor,
mantendo o que as equipes digitaram (OBSERVAÇÃO, REGULARIZADO POR, tabela de oficinas), e refaz a
página de acompanhamento dos analistas. Não consulta a API do SGA; da pasta ENTRADA (e de Downloads)
lê só o relatório de tarefas do SIGA (aba SIGA) e os arquivos salvos pela página de acompanhamento.

Uso:
    py gerar_setores.py
"""
import sys

from sinistro.pipeline import executar

if __name__ == "__main__":
    sys.exit(executar(etapa_sga=False, etapa_integracao=False, etapa_setores=True))
