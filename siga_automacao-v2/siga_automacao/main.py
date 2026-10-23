"""Ponto de entrada: login automático no SIGA + download de relatórios.

Uso:
    python main.py            -> loga (pede senha só na 1ª vez) e baixa os relatórios
    python main.py --trocar   -> pede login/senha de novo
    python main.py --esquecer -> apaga credencial salva
    python main.py --so-login -> só loga e deixa o navegador aberto
"""
import sys
from datetime import date
from tkinter import messagebox, Tk

from playwright.sync_api import sync_playwright

import credenciais
import relatorios
import siga
from gravador import Gravador
from tela_login import pedir_credenciais

ANO_DASHBOARD_INICIO = 2021  # Dashboard Arco → Gerencial: baixa deste ano até o ano atual


def obter_credenciais(forcar_tela: bool, erro: str = "", usuario: str = ""):
    """Retorna (usuario, senha, lembrar, veio_do_cofre) ou None."""
    salvo = None if forcar_tela else credenciais.carregar()
    if salvo:
        return salvo[0], salvo[1], True, True
    if not usuario and (antigo := credenciais.carregar()):
        usuario = antigo[0]
    resp = pedir_credenciais(usuario, erro)
    if resp is None:
        return None
    return (*resp, False)


def logar(page, creds):
    """Tenta logar; se falhar, reabre a tela de login.

    Retorna (usuario, senha) que funcionaram, ou None se o usuário cancelar.
    """
    while True:
        usuario, senha, lembrar, do_cofre = creds
        try:
            siga.entrar(page, usuario, senha)
            break
        except siga.ErroLogin as e:
            creds = obter_credenciais(True, erro=f"Falha no login: {e}", usuario=usuario)
            if creds is None:
                return None
    if lembrar and not do_cofre:
        credenciais.salvar(usuario, senha)
    elif not lembrar:
        credenciais.apagar()
    return usuario, senha


def avisar(titulo: str, texto: str, erro: bool = False):
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    (messagebox.showerror if erro else messagebox.showinfo)(titulo, texto, parent=root)
    root.destroy()


def main():
    if "--esquecer" in sys.argv:
        credenciais.apagar()
        print("Credencial apagada.")
        return

    creds = obter_credenciais("--trocar" in sys.argv)
    if creds is None:
        print("Cancelado.")
        return

    with sync_playwright() as pw:
        ctx = siga.abrir_navegador(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        gravador = Gravador(ctx)

        creds = logar(page, creds)
        if creds is None:
            ctx.close()
            print("Cancelado.")
            return
        usuario, senha = creds
        print("Login OK no SIGA.")

        if "--so-login" in sys.argv:
            print("Navegador aberto. Feche a janela para encerrar.")
            page.wait_for_event("close", timeout=0)
            ctx.close()
            return

        # Dashboard primeiro: ele abre em outra janela e deixa a tela inicial intacta.
        # Recarregar a tela inicial do SIGA no meio derruba a sessão, então não recarregamos.
        tarefas = []
        for ano in range(ANO_DASHBOARD_INICIO, date.today().year + 1):
            tarefas.append((
                f"Total Eventos Cadastrados {ano}",
                lambda ano=ano: relatorios.baixar_total_eventos_cadastrados(
                    ctx, page, ano,
                    fotografar=gravador.fotografar if ano == ANO_DASHBOARD_INICIO else None),
            ))
        tarefas.append(("Controle de Eventos",
                        lambda: relatorios.baixar_controle_eventos(ctx, page)))

        falhas = []
        for nome, baixar in tarefas:
            try:
                if siga.sessao_expirada(page):
                    print("Sessão expirada; fazendo login de novo.")
                    relatorios.esquecer_dashboard()
                    siga.entrar(page, usuario, senha)
                arquivo = baixar()
                print(f"OK  {nome}: {arquivo}")
            except Exception as e:
                pasta = gravador.fotografar("falha")
                print(f"FALHA  {nome}: {e}\n      diagnóstico: {pasta}")
                falhas.append(f"{nome}: {e}")

        if falhas:
            avisar("SIGA - automação parou",
                   "Não consegui completar:\n- " + "\n- ".join(falhas) + "\n\n"
                   "Se puder, faça os passos manualmente no navegador. Seus cliques serão "
                   "gravados para eu ajustar a automação.\n\nFeche o navegador quando terminar.",
                   erro=True)
            page.wait_for_event("close", timeout=0)
            gravador.fotografar("depois_manual")
            ctx.close()
            sys.exit(1)
        ctx.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        siga.LOGS.mkdir(exist_ok=True)
        detalhe = traceback.format_exc()
        (siga.LOGS / "ultimo_erro.txt").write_text(detalhe, encoding="utf-8")
        print(detalhe)
        avisar("SIGA - erro", f"Erro inesperado (salvo em logs\\ultimo_erro.txt):\n\n{detalhe[-800:]}", erro=True)
        sys.exit(1)
