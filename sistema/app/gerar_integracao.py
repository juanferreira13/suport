"""Gera a integração SGA x SIGA na planilha do sinistro.

- Incorpora à aba INTEGRAÇÃO o "DashBoard SIGA" que estiver na pasta ENTRADA (atualiza os
  eventos existentes pelo número e acrescenta os novos; o histórico é mantido).
- Recalcula os cruzamentos entre os dois sistemas: PROTOCOLO, COMPETENCIA e chave na INTEGRAÇÃO,
  STATUS SIGA na aba SGA e as colunas buscadas do SGA na aba SIGA (preenchida à mão).

Uso:
    py gerar_integracao.py
"""
import sys

from sinistro.pipeline import executar

if __name__ == "__main__":
    sys.exit(executar(etapa_sga=False, etapa_integracao=True))
