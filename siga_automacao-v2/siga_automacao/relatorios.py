"""Passos para baixar relatórios do SIGA depois do login."""
from datetime import datetime

from playwright.sync_api import Page, BrowserContext

from siga import ENTRADA


class ErroPasso(Exception):
    def __init__(self, passo: str, detalhe: str):
        super().__init__(f"{passo}: {detalhe}")
        self.passo = passo


# Ícone de lupa: o SIGA usa Material Icons (<i class="material-icons">search</i>);
# demais opções são reserva.
SEL_LUPA = ", ".join([
    '.material-icons:text-is("search")', '.material-icons:text-is("zoom_in")',
    '.material-icons:text-is("find_in_page")', '.material-icons:text-is("pageview")',
    'img[src*="lupa" i]', 'img[src*="search" i]', 'img[src*="zoom" i]', 'img[src*="find" i]',
    'img[src*="pesquis" i]', 'i[class*="search" i]', 'i[class*="zoom" i]', 'span[class*="search" i]',
    '[title*="analít" i]', '[title*="analit" i]', '[title*="detalh" i]', '[title*="visualizar" i]',
])
SEL_EXCEL = ':is(button, a, [role=button], [class*="btn" i]):has-text("Excel")'


def _visiveis(page: Page, seletor: str):
    """Lista (locator, caixa) de todos os elementos visíveis em todos os frames da página."""
    achados = []
    for frame in page.frames:
        try:
            loc = frame.locator(seletor)
            for i in range(loc.count()):
                item = loc.nth(i)
                caixa = item.bounding_box()
                if caixa and caixa["width"] > 0 and caixa["height"] > 0 and item.is_visible():
                    achados.append((item, caixa))
        except Exception:
            continue
    return achados


def _caixa_texto(page: Page, texto: str):
    for loc, caixa in _visiveis(page, f'text="{texto}"'):
        return loc, caixa
    return None, None


def _lupas_graficos(page: Page):
    """Lupas dentro do bloco Gráficos (entre a seta do bloco e 'Atividades a serem realizadas')."""
    achados = _visiveis(page, "#showHideGraficos")
    if not achados:
        return []
    topo = achados[0][1]
    _, fim = _caixa_texto(page, "Atividades a serem realizadas")
    lupas = [
        (loc, c) for loc, c in _visiveis(page, SEL_LUPA)
        if c["y"] > topo["y"] and (fim is None or c["y"] < fim["y"])
    ]
    # Ordem de leitura: linha de cima primeiro, depois da esquerda pra direita.
    lupas.sort(key=lambda lc: (round(lc[1]["y"] / 60), lc[1]["x"]))
    return lupas


def abrir_graficos(page: Page, timeout_s: int = 60):
    """Passo 1: clica na seta do bloco Gráficos (se ainda não estiver aberto) e espera carregar."""
    if _lupas_graficos(page):
        return
    seta = None
    for _ in range(timeout_s * 2):
        achados = _visiveis(page, "#showHideGraficos")
        if achados:
            seta = achados[0][0]
            break
        page.wait_for_timeout(500)
    if seta is None:
        raise ErroPasso("Abrir Gráficos", "seta 'ocultar/expandir' (#showHideGraficos) não encontrada")
    # keyboard_arrow_down = fechado; clicar abre e chama loadDataGraficos().
    if "down" in seta.inner_text():
        seta.click()

    for _ in range(timeout_s * 2):
        if _lupas_graficos(page):
            page.wait_for_timeout(1500)  # deixa os demais gráficos terminarem
            return
        page.wait_for_timeout(500)
    raise ErroPasso("Abrir Gráficos", "gráficos não carregaram (lupa não apareceu)")


def _marcar_excel_existentes(ctx: BrowserContext):
    for pg in ctx.pages:
        for frame in pg.frames:
            try:
                frame.locator(SEL_EXCEL).evaluate_all(
                    "els => els.forEach(e => e.setAttribute('data-siga-velho', '1'))")
            except Exception:
                pass


def _excel_novo(ctx: BrowserContext):
    for pg in ctx.pages:
        for loc, _ in _visiveis(pg, f"{SEL_EXCEL}:not([data-siga-velho])"):
            if len(loc.inner_text().strip()) < 20:  # evita pegar um bloco grande que contém "Excel"
                return pg, loc
    return None, None


def baixar_controle_eventos(ctx: BrowserContext, page: Page, timeout_s: int = 90, fotografar=None):
    """Gráficos → lupa do 'Controle de Eventos' → Excel → salva em entrada/.

    fotografar(rotulo): opcional, salva diagnóstico da tela entre os passos.
    """
    abrir_graficos(page)
    if fotografar:
        fotografar("diag_1_graficos")

    lupas = _lupas_graficos(page)
    if not lupas:
        raise ErroPasso("Lupa Controle de Eventos", "nenhuma lupa encontrada")
    _marcar_excel_existentes(ctx)
    lupas[0][0].click()  # 1º gráfico (canto esquerdo) = Controle de Eventos

    pg_excel, btn = None, None
    for i in range(timeout_s * 2):
        pg_excel, btn = _excel_novo(ctx)
        if btn:
            break
        if fotografar and i == 10:
            fotografar("diag_2_apos_lupa")
        page.wait_for_timeout(500)
    if not btn:
        raise ErroPasso("Botão Excel", "visão analítica não abriu ou botão Excel não apareceu")
    pg_excel.wait_for_timeout(1500)  # tabela termina de preencher

    return _baixar_para_entrada(pg_excel, btn, "Controle_Eventos", timeout_s)


def _baixar_para_entrada(pg: Page, botao, prefixo: str, timeout_s: int):
    """Clica no botão de download e salva em entrada/<prefixo>_<data>.xlsx."""
    with pg.expect_download(timeout=timeout_s * 1000) as info:
        botao.click()
    download = info.value

    ENTRADA.mkdir(exist_ok=True)
    destino = ENTRADA / f"{prefixo}_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
    download.save_as(destino)
    download.delete()
    return destino


# ---------------------------------------------------------------- Dashboard Arco

def _esperar(page: Page, achar, timeout_s: int, passo: str, detalhe: str):
    """Repete achar() até devolver algo diferente de None/vazio."""
    for _ in range(timeout_s * 2):
        resultado = achar()
        if resultado:
            return resultado
        page.wait_for_timeout(500)
    raise ErroPasso(passo, detalhe)


def abrir_dashboard_arco(ctx: BrowserContext, page: Page, timeout_s: int = 60) -> Page:
    """Menu lateral → RELATÓRIOS → Dashboard Arco. Devolve a janela do dashboard."""
    page.keyboard.press("Escape")  # fecha algum popup que tenha ficado aberto
    sel_item = 'a:has(> span.menu-item-text:text-is("Dashboard Arco"))'
    sel_grupo = 'a.menu-first-level:has(> span.menu-item-text:text-is("RELATÓRIOS"))'

    item = _esperar(page, lambda: next((f.locator(sel_item).first for f in page.frames
                                        if f.locator(sel_item).count()), None),
                    timeout_s, "Menu Dashboard Arco", "item 'Dashboard Arco' não existe no menu")
    grupo = next((f.locator(sel_grupo).first for f in page.frames if f.locator(sel_grupo).count()), None)
    if not item.is_visible() and grupo is not None:
        try:
            grupo.hover(timeout=5000)
            grupo.click(timeout=5000)
            item.wait_for(state="visible", timeout=5000)
        except Exception:
            pass

    paginas_antes = set(ctx.pages)
    if item.is_visible():
        item.click()
    else:
        item.dispatch_event("click")  # menu recolhido: dispara o clique direto no item

    def achar_dashboard():
        for pg in ctx.pages:
            if "dash-board" in pg.url and pg not in paginas_antes:
                return pg
        for pg in ctx.pages:
            if "dash-board" in pg.url and "logout" not in pg.url:
                return pg
        return None

    dash = _esperar(page, achar_dashboard, timeout_s, "Abrir Dashboard Arco",
                    "janela do dashboard não abriu")
    dash.bring_to_front()
    dash.wait_for_load_state("domcontentloaded")
    if "logout" in dash.url:
        raise ErroPasso("Abrir Dashboard Arco", "dashboard pediu login novamente (" + dash.url + ")")
    return dash


JS_MARCAR_BARRA_TOTAL = """
(aceitarVelhas) => {
  document.querySelectorAll('[data-siga-alvo]').forEach(e => e.removeAttribute('data-siga-alvo'));
  // Série 'Total Eventos Cadastrados' existe em 2 gráficos: o mensal (12 barras) e o total (1 barra).
  const series = [...document.querySelectorAll('g.apexcharts-series[seriesName="TotalxEventosxCadastrados"]')];
  const barras = s => [...s.querySelectorAll('path.apexcharts-bar-area')]
                       .filter(p => p.getBoundingClientRect().height > 0)
                       .filter(p => aceitarVelhas || !p.hasAttribute('data-siga-velho'));
  const candidatas = series.map(barras).filter(b => b.length);
  if (!candidatas.length) return 0;
  const unica = candidatas.find(b => b.length === 1)
             || candidatas.sort((a, b) => b[0].getBoundingClientRect().x - a[0].getBoundingClientRect().x)[0];
  unica[0].setAttribute('data-siga-alvo', '1');
  return unica.length;
}
"""

# Marca as barras atuais para saber quando o gráfico foi redesenhado com o ano novo.
JS_MARCAR_BARRAS_VELHAS = """
() => document.querySelectorAll('path.apexcharts-bar-area')
                .forEach(p => p.setAttribute('data-siga-velho', '1'))
"""

_dashboard = None  # janela do Dashboard Arco reaproveitada entre os anos


def esquecer_dashboard():
    """Após novo login, a janela antiga do dashboard não vale mais."""
    global _dashboard
    if _dashboard is not None and not _dashboard.is_closed():
        _dashboard.close()
    _dashboard = None


def _obter_dashboard(ctx: BrowserContext, page: Page) -> Page:
    global _dashboard
    if _dashboard is not None and not _dashboard.is_closed() and "logout" in _dashboard.url:
        _dashboard.close()  # dashboard perdeu a sessão; reabre pelo menu
    if _dashboard is None or _dashboard.is_closed():
        _dashboard = abrir_dashboard_arco(ctx, page)
    return _dashboard


def _fechar_popup(dash: Page):
    modal = dash.locator(".modal.show")
    if not modal.count() or not modal.first.is_visible():
        return
    dash.keyboard.press("Escape")
    dash.wait_for_timeout(1000)
    if modal.count() and modal.first.is_visible():
        fechar = dash.locator('.modal.show :is(.btn-close, .close, [data-dismiss="modal"], '
                              '[data-bs-dismiss="modal"], [aria-label="Close"])')
        if fechar.count():
            fechar.first.click()
    try:
        modal.first.wait_for(state="hidden", timeout=10000)
    except Exception:
        pass


def baixar_total_eventos_cadastrados(ctx: BrowserContext, page: Page, ano: int,
                                     timeout_s: int = 300, fotografar=None):
    """Dashboard Arco → Gerencial → ano → Buscar → gráfico 'Total Eventos Cadastrados' → Excel.

    A janela do dashboard fica aberta para o próximo ano.
    """
    dash = _obter_dashboard(ctx, page)
    _fechar_popup(dash)

    aba = dash.locator('li:text-is("Gerencial")').first
    aba.wait_for(state="visible", timeout=60000)
    aba.click()

    ano_sel = dash.locator("#select_ano")
    ano_sel.wait_for(state="visible", timeout=60000)
    dash.evaluate(JS_MARCAR_BARRAS_VELHAS)
    ano_sel.select_option(label=str(ano))
    dash.locator('button[title="Buscar"]').click()
    try:
        dash.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    dash.wait_for_timeout(2000)
    if fotografar:
        fotografar("diag_dash_1_filtrado")

    # Espera o gráfico redesenhar com o ano novo; se ele não mudar o DOM, usa o que estiver lá.
    try:
        _esperar(dash, lambda: dash.evaluate(JS_MARCAR_BARRA_TOTAL, False), 45, "", "")
    except ErroPasso:
        print(f"  aviso {ano}: gráfico não redesenhou; usando o que está na tela")
        _esperar(dash, lambda: dash.evaluate(JS_MARCAR_BARRA_TOTAL, True), 30,
                 "Gráfico Total Eventos Cadastrados", "barra do gráfico não encontrada")
    barra = dash.locator("[data-siga-alvo]")
    barra.scroll_into_view_if_needed()
    dash.wait_for_timeout(1000)
    dash.evaluate(JS_MARCAR_BARRA_TOTAL, True)  # remarca após rolar (gráfico pode redesenhar)
    barra.click()

    # Popup com a tabela #table_relatorio_eventos e botões Excel/Copiar/CSV/Imprimir.
    sel_excel = ('#table_relatorio_eventos_wrapper :is(button, a):has-text("Excel"), '
                 '.modal.show :is(button, a):has-text("Excel")')
    btn = _esperar(dash, lambda: next((loc for loc, _ in _visiveis(dash, sel_excel)), None), 60,
                   "Botão Excel (popup)", "popup com a tabela não abriu")
    # Espera a tabela terminar de carregar (some o "processando").
    try:
        dash.locator("#table_relatorio_eventos tbody tr").first.wait_for(timeout=60000)
        dash.locator(".dataTables_processing").first.wait_for(state="hidden", timeout=60000)
    except Exception:
        pass
    dash.wait_for_timeout(1000)
    if fotografar:
        fotografar("diag_dash_2_popup")

    destino = _baixar_para_entrada(dash, btn, f"Total_Eventos_Cadastrados_{ano}", timeout_s)
    _fechar_popup(dash)
    return destino
