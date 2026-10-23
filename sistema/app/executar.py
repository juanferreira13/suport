"""Rotina diária: atualiza a aba SGA, gera a integração, abastece as planilhas dos setores e
gera as páginas da conferência de finalizados e do acompanhamento dos analistas.

Uso:
    py executar.py              rotina completa (é o que a tarefa agendada das 8h roda)
    py executar.py --sem-api    não consulta a API do SGA (usa só os arquivos da pasta ENTRADA)
"""
import argparse
import sys

from sinistro.pipeline import executar


def main() -> int:
    p = argparse.ArgumentParser(description="Atualiza a planilha do sinistro e as planilhas dos setores.")
    p.add_argument("--sem-api", action="store_true", help="não consulta a API do SGA")
    args = p.parse_args()
    return executar(etapa_sga=True, etapa_integracao=True, usar_api=not args.sem_api, etapa_setores=True, etapa_painel=True)


if __name__ == "__main__":
    sys.exit(main())
