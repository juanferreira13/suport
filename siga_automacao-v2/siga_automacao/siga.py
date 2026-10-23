"""Abre o SIGA no navegador (Edge) e faz login automático."""
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page, BrowserContext

URL_SIGA = "https://siga.arcoconsultoria.com/SIGA/open.do?sys=SIG"
PASTA = Path(__file__).resolve().parent
PERFIL = PASTA / "perfil_navegador"   # cookies/sessão persistem aqui
ENTRADA = PASTA / "entrada"           # relatórios baixados vão para cá
LOGS = PASTA / "logs"


RE_EXPIRADA = re.compile(r"sess[ãa]o\s+(foi\s+)?(expirou|expirada|encerrada)|session\s+expired", re.I)


class ErroLogin(Exception):
    pass


def fechar_navegador_preso() -> int:
    """Fecha Edge que ficou aberto com o perfil da automação (trava o perfil e impede nova abertura)."""
    filtro = str(PERFIL).replace("'", "''")
    cmd = ("Get-CimInstance Win32_Process -Filter \"name='msedge.exe'\" | "
           f"Where-Object {{ $_.CommandLine -like '*{filtro}*' }} | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; 1 }")
    saida = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True).stdout
    fechados = sum(1 for linha in saida.splitlines() if linha.strip() == "1")
    if fechados:
        time.sleep(2)
    return fechados


def abrir_navegador(pw, headless: bool = False) -> BrowserContext:
    if fechar_navegador_preso():
        print("Navegador da automação que ficou aberto foi fechado.")
    opcoes = dict(
        user_data_dir=str(PERFIL),
        headless=headless,
        accept_downloads=True,
        chromium_sandbox=True,  # sem isso aparece o aviso "--no-sandbox"
        viewport=None if not headless else {"width": 1366, "height": 768},
        args=["--start-maximized"],
    )
    return pw.chromium.launch_persistent_context(channel="msedge", **opcoes)


def _frame_login(page: Page):
    """O formulário de login fica dentro de um iframe; procura em todos os frames."""
    for frame in page.frames:
        campo = frame.locator('input[placeholder="Login"]')
        try:
            if campo.count() and campo.first.is_visible():
                return frame
        except Exception:
            continue
    return None


def precisa_login(page: Page, espera_ms: int = 15000) -> bool:
    """Espera a página carregar e diz se a tela de login está aparecendo."""
    page.wait_for_load_state("domcontentloaded")
    for _ in range(espera_ms // 500):
        if _frame_login(page):
            return True
        page.wait_for_timeout(500)
    return False


def fazer_login(page: Page, usuario: str, senha: str, timeout_ms: int = 30000) -> None:
    alertas = []

    def ao_alerta(d):
        alertas.append(d.message)
        d.accept()

    page.on("dialog", ao_alerta)
    try:
        _enviar_login(page, usuario, senha, timeout_ms, alertas)
    finally:
        page.remove_listener("dialog", ao_alerta)


def _enviar_login(page: Page, usuario: str, senha: str, timeout_ms: int, alertas: list) -> None:
    frame = _frame_login(page)
    if frame is None:
        raise ErroLogin("Tela de login não encontrada.")

    frame.locator('input[placeholder="Login"]').fill(usuario)
    frame.locator('input[placeholder="Senha"]').fill(senha)
    frame.get_by_role("button", name="Entrar").click()

    # Sucesso = campo de login some. Falha = alerta/mensagem e campo continua.
    passos = timeout_ms // 500
    for _ in range(passos):
        page.wait_for_timeout(500)
        if alertas:
            raise ErroLogin(alertas[-1])
        if _frame_login(page) is None:
            return
    raise ErroLogin("Login não confirmado (tela de login continua aberta). Verifique usuário/senha.")


def sessao_expirada(page: Page) -> bool:
    """Tela de login de volta ou mensagem de sessão expirada em algum frame."""
    if _frame_login(page):
        return True
    for frame in page.frames:
        try:
            texto = frame.evaluate("() => document.body ? document.body.innerText.slice(0, 5000) : ''")
        except Exception:
            continue
        if RE_EXPIRADA.search(texto):
            return True
    return False


def entrar(page: Page, usuario: str, senha: str) -> None:
    """Abre o SIGA e loga se necessário."""
    page.goto(URL_SIGA)
    if precisa_login(page):
        fazer_login(page, usuario, senha)
