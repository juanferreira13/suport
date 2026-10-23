"""Atualiza a aba SGA da planilha do sinistro.

Fontes, nesta ordem:
  1. relatório de eventos exportado do SGA que estiver na pasta ENTRADA (traz as 28 colunas);
  2. API oficial do SGA Hinova (credenciais em sistema/configuracao.env), que acrescenta eventos novos e atualiza
     as colunas que a API fornece.

Uso:
    py atualizar_sga.py                 atualiza a aba SGA
    py atualizar_sga.py --sem-api       usa só o relatório da pasta ENTRADA
    py atualizar_sga.py --diagnostico   testa o acesso à API e mostra os campos que ela devolve
"""
import argparse
import sys

from sinistro.pipeline import diagnostico_api, executar


def main() -> int:
    p = argparse.ArgumentParser(description="Atualiza a aba SGA da planilha do sinistro.")
    p.add_argument("--sem-api", action="store_true", help="não consulta a API; usa só o relatório em ENTRADA")
    p.add_argument("--diagnostico", action="store_true", help="testa a API e mostra o que ela devolve, sem gravar nada")
    args = p.parse_args()
    if args.diagnostico:
        return diagnostico_api()
    return executar(etapa_sga=True, etapa_integracao=False, usar_api=not args.sem_api)


if __name__ == "__main__":
    sys.exit(main())
