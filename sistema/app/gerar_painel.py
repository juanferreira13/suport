"""Gera a página HTML da conferência de finalizados (a antiga aba FINALIZADOS (conf.Lari)).

Mostra os eventos do SIGA liberados desde PAINEL_FINALIZADOS_DESDE, com a situação de cada um
no SGA e as anotações da conferência (verificar arquivamento, por que excluir, incluir motivo).
Usa os dados já guardados; não consulta a API do SGA nem lê a pasta ENTRADA.

Uso:
    py gerar_painel.py
"""
import sys

from sinistro.pipeline import executar

if __name__ == "__main__":
    sys.exit(executar(etapa_sga=False, etapa_integracao=False, etapa_painel=True))
