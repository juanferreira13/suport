"""Orquestra as etapas: atualizar dados do SGA, atualizar dados do SIGA, cruzar e gravar o .xlsx."""
from __future__ import annotations

import collections
import datetime
import json
import re
import shutil
import time
from pathlib import Path

from . import acompanhamento, integracao, painel, planilha, registro, setores
from . import sga_base as S
from . import siga as G
from .config import NOME_CONFIG, Config, carregar_config
from .google_planilhas import GRAVANDO, ContaGoogle, GoogleErro, Marcas, PlanilhaGoogle, impressao
from .sga_api import SgaApi, SgaApiErro, completar_por_protocolo, normalizar_evento
from .util import chave_cabecalho, configurar_log, data_br, texto

OK, FALHA, PARCIAL = 0, 1, 2


def _examinar(caminho: Path, log):
    """Identifica um arquivo da pasta de entrada. Devolve (tipo, tabela) com tipo 'sga', 'siga' (DashBoard),
    'tarefas' (relatório de tarefas do SIGA, o conteúdo da aba SIGA), 'acompanhamento' (alterações salvas pela
    página dos analistas) ou None."""
    with open(caminho, "rb") as f:
        inicio = f.read(300_000)
    if acompanhamento.eh_arquivo(inicio):
        return "acompanhamento", None
    if inicio[:2] == b"PK":  # .xlsx
        tabela = planilha.ler_abas(caminho, [None])[None] or []
        for linha in tabela[:15]:
            chaves = {chave_cabecalho(c) for c in linha}
            if {"NUMERO", "INTEGRACAO"} <= chaves:
                return "siga", tabela
            if {"PROTOCOLO", "TIPOEVENTO"} <= chaves:
                return "sga", tabela
        if G.eh_relatorio_tarefas(tabela):
            return "tarefas", tabela
        return None, None
    if inicio[:4] == b"\xd0\xcf\x11\xe0":
        log.warning("Entrada: %s é um .xls binário; exporte o relatório pelo SGA (botão Excel) ou salve como .xlsx.", caminho.name)
        return None, None
    amostra = inicio.decode("utf-8", "replace").upper()
    if "<TH" in amostra and "PROTOCOLO" in amostra:
        return "sga", None  # relatório HTML do SGA; lido sob demanda
    return None, None


def _da_pagina_em_downloads(cfg: Config, log) -> list[Path]:
    """Arquivos de alterações da página de acompanhamento que o navegador salvou em Downloads."""
    pasta = cfg.pasta_downloads
    if not pasta or not pasta.is_dir():
        return []
    achados = []
    try:
        for caminho in pasta.glob(f"{acompanhamento.PREFIXO_ARQUIVO}*.json"):
            with open(caminho, "rb") as f:
                if acompanhamento.eh_arquivo(f.read(2000)):
                    achados.append(caminho)
    except OSError as e:
        log.warning("Não consegui olhar a pasta %s (%s).", pasta, e)
    return achados


def _recolher_de_pastas_extra(cfg: Config, log) -> None:
    """Copia para a ENTRADA os relatórios do SIGA/SGA que aparecerem nas pastas extras configuradas
    (ex.: a pasta de saída de uma exportação automática). Os arquivos originais não são tocados; cada um é
    copiado uma única vez (controlado por dados/pastas_extra.json)."""
    if not cfg.pastas_entrada_extra:
        return
    arquivo = cfg.pasta_dados / "pastas_extra.json"
    try:
        vistos = set(json.loads(arquivo.read_text(encoding="utf-8"))) if arquivo.exists() else set()
    except (OSError, ValueError):
        vistos = set()
    novos: list[str] = []
    for pasta in cfg.pastas_entrada_extra:
        if not pasta.is_dir():
            log.warning("Pasta extra %s não encontrada; ignorada nesta execução.", pasta)
            continue
        try:
            candidatos = [p for p in pasta.iterdir()
                          if p.is_file() and p.suffix.lower() in (".xlsx", ".xls", ".xlsm") and not p.name.startswith(("~", "."))]
        except OSError as e:
            log.warning("Não consegui olhar a pasta extra %s (%s).", pasta, e)
            continue
        for caminho in sorted(candidatos, key=lambda p: p.stat().st_mtime):
            try:
                info = caminho.stat()
                marca = f"{caminho.resolve()}|{info.st_size}|{info.st_mtime_ns}"
            except OSError:
                continue
            if marca in vistos:
                continue
            vistos.add(marca)
            novos.append(marca)
            try:
                tipo, _ = _examinar(caminho, log)
            except Exception as e:
                log.warning("Pasta extra: não consegui ler %s (%s).", caminho.name, e)
                continue
            if tipo not in ("sga", "siga", "tarefas"):
                continue
            destino = cfg.pasta_entrada / caminho.name
            if destino.exists():
                destino = cfg.pasta_entrada / f"{caminho.stem}_{info.st_mtime_ns}{caminho.suffix}"
            try:
                shutil.copy2(caminho, destino)
                log.info("Pasta extra: %s copiado de %s para a ENTRADA.", caminho.name, pasta)
            except OSError as e:
                log.warning("Não consegui copiar %s da pasta extra (%s).", caminho.name, e)
                vistos.discard(marca)
    if novos:
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(json.dumps(sorted(vistos)[-2000:], ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            log.warning("Não consegui registrar os arquivos já recolhidos das pastas extras (%s).", e)


def _listar_entrada(cfg: Config, log) -> tuple[list, list, list, list]:
    """Arquivos novos, do mais antigo para o mais recente: ([(caminho, tabela)] do SGA, idem do DashBoard SIGA,
    idem do relatório de tarefas do SIGA, [caminho] de alterações da página de acompanhamento, que também são
    procurados em Downloads)."""
    cfg.pasta_entrada.mkdir(parents=True, exist_ok=True)
    _recolher_de_pastas_extra(cfg, log)
    sga, siga, tarefas, pagina = [], [], [], []
    arquivos = [p for p in cfg.pasta_entrada.iterdir() if p.is_file() and not p.name.startswith(("~", "."))]
    for caminho in sorted(arquivos, key=lambda p: p.stat().st_mtime):
        try:
            tipo, tabela = _examinar(caminho, log)
        except Exception as e:  # arquivo ilegível não pode derrubar a rotina diária
            log.warning("Entrada: não consegui ler %s (%s).", caminho.name, e)
            continue
        if tipo == "sga":
            sga.append((caminho, tabela))
        elif tipo == "siga":
            siga.append((caminho, tabela))
        elif tipo == "tarefas":
            tarefas.append((caminho, tabela))
        elif tipo == "acompanhamento":
            pagina.append(caminho)
        else:
            # Sai da ENTRADA (sem apagar) para não ser examinado de novo a cada execução.
            destino = cfg.pasta_entrada / "nao reconhecidos"
            destino.mkdir(parents=True, exist_ok=True)
            try:
                caminho.replace(destino / caminho.name)
            except OSError:
                pass
            log.warning("Entrada: %s não é relatório do SGA, DashBoard do SIGA nem relatório de tarefas do SIGA; movido para '%s'.",
                        caminho.name, destino.name)
            registro.anotar(cfg.registro, registro.MANUAL, "-", "arquivo não reconhecido", "-",
                            "IGNORADO (movido para 'nao reconhecidos')", caminho.name, log)
    pagina += _da_pagina_em_downloads(cfg, log)
    return sga, siga, tarefas, pagina


def _arquivar(arquivos: list[Path], cfg: Config, log) -> None:
    destino = cfg.pasta_entrada / "processados"
    destino.mkdir(parents=True, exist_ok=True)
    for caminho in arquivos:
        try:   # move, não replace: o arquivo pode vir de Downloads, em outra unidade
            shutil.move(caminho, destino / f"{datetime.datetime.now():%Y%m%d_%H%M%S}__{caminho.name}")
        except OSError as e:
            log.warning("Não consegui mover %s para processados (%s).", caminho.name, e)


def _normalizar(api: SgaApi, itens: list[dict], classificacoes: dict[str, str]) -> list[list[str]]:
    """Itens da API -> linhas da aba SGA, com nomes de oficina e vistoriador e o associado nos itens de terceiro."""
    fornecedores, vistoriadores = api.fornecedores(), api.vistoriadores()
    return completar_por_protocolo([normalizar_evento(i, classificacoes, fornecedores, vistoriadores) for i in itens])


def _consultar_api(cfg: Config, base: S.BaseSga, log) -> None:
    api = SgaApi(cfg.api_url, cfg.token, cfg.usuario, cfg.senha, log)
    api.autenticar()
    log.info("API SGA: autenticado. Buscando eventos cadastrados desde %s...", cfg.data_inicial.strftime("%d/%m/%Y"))
    classificacoes = api.classificacoes()
    itens = api.listar_eventos(cfg.data_inicial, datetime.date.today(), cfg.por_pagina)
    if not itens:
        log.warning("API SGA: nenhum evento retornado; a aba SGA ficou como estava.")
        return
    resumo = base.aplicar_api(_normalizar(api, itens, classificacoes), cfg.data_inicial, log)
    log.info("API SGA: %d itens em %d chamadas -> %d linhas novas; alterações por coluna: %s; %d itens sem par único (mantidos como estavam).",
             len(itens), api.chamadas, resumo["novos"], resumo["alteracoes"] or "nenhuma", resumo["ambiguos"])
    # Marca/modelo do veículo (só a API traz): guardados à parte, para os indicadores de Vidros do painel.
    veiculos = S.BaseVeiculos(cfg.pasta_dados)
    veiculos.carregar()
    mudou = veiculos.aplicar_api(itens)
    veiculos.salvar()
    log.info("API SGA: marca/modelo guardados para %d veículos novos/alterados (total %d).", mudou, len(veiculos.dados))
    registro.anotar(cfg.registro, registro.AUTOMATICO, "SGA", f"API desde {cfg.data_inicial:%d/%m/%Y}",
                    len(itens), f"importado: {resumo['novos']} novos, {sum(resumo['alteracoes'].values())} alterações", "", log)
    base.origem = f"{base.origem} + API em {datetime.datetime.now():%d/%m/%Y %H:%M}".strip(" +")


# ---------------------------------------------------------------- sinistro no Google Sheets
ABAS_GOOGLE = {planilha.ABA_SGA: "A:AB", planilha.ABA_INTEGRACAO: "A:S", planilha.ABA_SIGA: "A:AS",
               planilha.ABA_TAREFAS: "A:C", setores.ABA_BASE_VISTORIA: "A:C"}
SGA_FORMULAS = (S.N_COLUNAS + 1, S.N_COLUNAS + 5)          # AD..AH: NOME, PLACA, COMPETENCIA, STATUS SIGA, chave
INTEGRACAO_FORMULAS = (G.N_COLUNAS + 1, G.N_COLUNAS + 3)   # T..V: PROTOCOLO, PLACA 2, COMPETENCIA
SIGA_FORMULAS_A, SIGA_FORMULAS_X = (1, 1), (len(G.COLUNAS_TAREFAS) + 2, integracao.SIGA_COLUNAS)   # A e X..AS da aba SIGA


def _ler_sinistro_google(cfg: Config, conta: ContaGoogle, log) -> tuple[PlanilhaGoogle, dict]:
    sinistro = conta.planilha(cfg.google_sinistro)
    log.info("Google: lendo a planilha %s (SGA, INTEGRAÇÃO, SIGA, TAREFAS)...", sinistro.titulo)
    tabelas = sinistro.ler_abas(ABAS_GOOGLE)
    faltam = [aba for aba in (planilha.ABA_SIGA, planilha.ABA_TAREFAS, planilha.ABA_SGA, planilha.ABA_INTEGRACAO) if tabelas[aba] is None]
    if faltam:
        raise GoogleErro(f"a planilha {sinistro.titulo} não tem as abas {', '.join(faltam)}")
    return sinistro, tabelas


def _so_texto(v) -> str:
    return re.sub(r"\s+", " ", texto(v).replace("\xa0", " ")).strip()


def _impressao_sga(linhas: list[list]) -> str:
    return impressao([[_so_texto(v) for v in l[:S.N_COLUNAS - 1]] for l in linhas])


def _impressao_integracao(linhas: list[list]) -> str:
    return impressao([[G._valor(c, v) for c, v in enumerate(l[:G.N_COLUNAS])] for l in linhas])


def _partir_do_google(sinistro: PlanilhaGoogle, tabelas: dict, base_sga: S.BaseSga, base_integ: G.BaseIntegracao,
                      marcas: Marcas, log) -> None:
    """Junta à base o que a equipe pôs nas abas SGA e INTEGRAÇÃO do Google.

    Se a aba mudou desde a última gravação do sistema (a equipe colou um relatório ou um DashBoard), ela vira o
    ponto de partida. Na primeira vez (ou depois de uma gravação interrompida) vale a base do sistema, e do Google
    entra só o que falta nela. Depois vêm os arquivos da pasta ENTRADA e a API; o resultado volta para as mesmas abas."""
    agora = datetime.datetime.now()
    chave = lambda l: (l[S.PROTOCOLO], S._comparavel(l[S.TIPO]))
    sga = S.linhas_de_tabela(tabelas[planilha.ABA_SGA], "aba SGA do Google")
    marca = marcas.obter(sinistro.id, planilha.ABA_SGA)
    mudou = bool(sga) and marca not in ("", GRAVANDO) and _impressao_sga(sga) != marca
    if mudou and not (base_sga.linhas and len(sga) < 0.8 * len(base_sga.linhas)):
        base_sga.substituir(sga, f"aba SGA do Google em {agora:%d/%m/%Y %H:%M}")
        log.info("Aba SGA do Google mudou desde a última gravação (relatório colado pela equipe): %d linhas, que passam a "
                 "ser o ponto de partida.", len(sga))
    elif sga and (mudou or marca in ("", GRAVANDO)):
        existentes = {chave(l) for l in base_sga.linhas}
        novas = [l for l in sga if chave(l) not in existentes]
        base_sga.linhas.extend(novas)
        motivo = ("aba bem menor que a base, então não substitui" if mudou else "primeira gravação no Google: vale a base do sistema")
        log.info("Aba SGA do Google (%d linhas; %s): %d linhas que faltavam na base foram acrescentadas.", len(sga), motivo, len(novas))
    try:
        integ = G.linhas_de_tabela(tabelas[planilha.ABA_INTEGRACAO], "aba INTEGRAÇÃO do Google")
    except ValueError as e:
        log.warning("%s", e)
        integ = []
    marca = marcas.obter(sinistro.id, planilha.ABA_INTEGRACAO)
    if integ and marca not in ("", GRAVANDO) and _impressao_integracao(integ) != marca:
        novos, alterados = base_integ.incorporar(integ, marcar_anos=False)
        log.info("Aba INTEGRAÇÃO do Google mudou desde a última gravação (DashBoard colado pela equipe): %d eventos; "
                 "%d novos e %d atualizados na base.", len(integ), novos, alterados)
    elif integ and marca in ("", GRAVANDO):
        existentes = {l[G.NUMERO] for l in base_integ.linhas}
        novos = [l for l in integ if l[G.NUMERO] not in existentes]
        base_integ.linhas.extend(novos)
        log.info("Aba INTEGRAÇÃO do Google (%d eventos; primeira gravação no Google: vale a base do sistema): %d eventos que "
                 "faltavam na base foram acrescentados.", len(integ), len(novos))


def _gravar_sinistro_google(sinistro: PlanilhaGoogle, base_sga: S.BaseSga, base_integ: G.BaseIntegracao, marcas: Marcas, log,
                            tarefas: list[list] | None = None) -> None:
    """Grava SGA (A:AB), INTEGRAÇÃO (A:S) e, com o relatório de tarefas do SIGA, a aba SIGA (B:W). As fórmulas das
    colunas seguintes são do Google e só são estendidas para baixo quando há mais linhas do que fórmulas; a coluna
    AÇÕES (AC) da SGA fica com a equipe."""
    for aba in (planilha.ABA_SGA, planilha.ABA_INTEGRACAO):   # se a gravação parar no meio, a próxima não confia na aba
        marcas.definir(sinistro.id, aba, GRAVANDO)
    n_sga = sinistro.substituir_aba(planilha.ABA_SGA, base_sga.linhas, S.N_COLUNAS - 1)
    integ = []
    for linha in base_integ.linhas:
        linha = list(linha)
        for c in G.COLUNAS_DATA:   # datas de verdade, como estão na aba
            linha[c] = data_br(linha[c]) or linha[c]
        integ.append(linha)
    n_integ = sinistro.substituir_aba(planilha.ABA_INTEGRACAO, integ, G.N_COLUNAS, {c: setores.FMT_DATA for c in G.COLUNAS_DATA})
    novas = sinistro.estender_formulas(planilha.ABA_SGA, *SGA_FORMULAS, n_sga)
    novas += sinistro.estender_formulas(planilha.ABA_INTEGRACAO, *INTEGRACAO_FORMULAS, n_integ)
    if tarefas is not None:
        n_siga = sinistro.substituir_aba(planilha.ABA_SIGA, [[None] + l for l in tarefas], len(G.COLUNAS_TAREFAS) + 1,
                                         {c + 1: setores.FMT_DATA for c in G.DATAS_TAREFAS}, primeira_coluna=1)
        novas += sinistro.estender_formulas(planilha.ABA_SIGA, *SIGA_FORMULAS_A, n_siga)
        novas += sinistro.estender_formulas(planilha.ABA_SIGA, *SIGA_FORMULAS_X, n_siga)
    celulas = sinistro.salvar()
    marcas.definir(sinistro.id, planilha.ABA_SGA, _impressao_sga(base_sga.linhas))
    marcas.definir(sinistro.id, planilha.ABA_INTEGRACAO, _impressao_integracao(base_integ.linhas))
    log.info("Gravado no Google: %s, abas SGA (%d linhas) e INTEGRAÇÃO (%d linhas)%s; %d células%s.", sinistro.titulo,
             n_sga - 1, n_integ - 1, f" e SIGA ({len(tarefas)} tarefas)" if tarefas is not None else "", celulas,
             f"; fórmulas estendidas em {novas} linhas" if novas else "")
    # A fórmula de W2 da INTEGRAÇÃO vai até uma linha fixa (T2:T20000): avisa antes de os eventos passarem dela.
    w2 = sinistro.formulas(planilha.ABA_INTEGRACAO, "W2")
    limite = max((int(n) for n in re.findall(r"[A-Z]+2:[A-Z]+(\d+)", str(w2[0][0]) if w2 and w2[0] else "")), default=0)
    if limite and n_integ > limite * 0.95:
        log.warning("INTEGRAÇÃO no Google: %d linhas; a fórmula de W2 só vai até a linha %d. Aumente o intervalo dela.", n_integ, limite)


def executar(etapa_sga: bool, etapa_integracao: bool, usar_api: bool = True, etapa_setores: bool = False,
             etapa_painel: bool = False) -> int:
    cfg = carregar_config()
    log = configurar_log(cfg.pasta_logs)
    inicio = time.time()
    codigo = OK
    log.info("==== Início (%s) ====", " + ".join(n for n, on in (
        ("SGA", etapa_sga), ("INTEGRAÇÃO", etapa_integracao), ("SETORES", etapa_setores), ("PÁGINA", etapa_painel)) if on))
    try:
        # Com o sinistro no Google, é lá que a equipe cola a aba SIGA e é lá que o sistema grava SGA e INTEGRAÇÃO.
        conta = ContaGoogle(cfg) if cfg.google_configurado else None
        sinistro_google, tabelas_google = None, {}
        if conta and cfg.google_sinistro:
            sinistro_google, tabelas_google = _ler_sinistro_google(cfg, conta, log)
        local = sinistro_google is None
        if local and cfg.planilha.exists() and planilha.planilha_bloqueada(cfg.planilha):
            log.warning("A planilha %s está aberta. Os dados serão atualizados, mas a gravação vai falhar se ela continuar aberta.", cfg.planilha.name)

        entrada_sga, entrada_siga, entrada_tarefas, entrada_pagina = _listar_entrada(cfg, log)
        base_sga, base_integ = S.BaseSga(cfg.pasta_dados), G.BaseIntegracao(cfg.pasta_dados)
        tem_sga, tem_integ = base_sga.carregar(), base_integ.carregar()

        # Primeira execução: histórico e aba SIGA vêm da planilha base (a baixada do Google Sheets).
        precisa = [aba for aba, falta in ((planilha.ABA_SIGA, local and not cfg.planilha.exists()),
                                          (planilha.ABA_TAREFAS, local and not cfg.planilha.exists()),
                                          (planilha.ABA_INTEGRACAO, local and not tem_integ),
                                          (planilha.ABA_SGA, local and not tem_sga and not (etapa_sga and entrada_sga))) if falta]
        origem: dict = {}
        if precisa:
            if cfg.planilha_base and cfg.planilha_base.exists():
                log.info("Primeira carga: lendo %s de %s (pode levar alguns minutos)...", ", ".join(precisa), cfg.planilha_base.name)
                origem = planilha.ler_abas(cfg.planilha_base, precisa)
            else:
                log.warning("PLANILHA_BASE não encontrada; começando sem histórico para: %s.", ", ".join(precisa))
        if origem.get(planilha.ABA_SGA):
            base_sga.substituir(S.linhas_de_tabela(origem[planilha.ABA_SGA], "aba SGA da planilha base"), "planilha base")
            base_sga.salvar()
        if origem.get(planilha.ABA_INTEGRACAO):
            base_integ.linhas = G.linhas_de_tabela(origem[planilha.ABA_INTEGRACAO], "aba INTEGRAÇÃO da planilha base")
            base_integ.salvar()
        marcas = Marcas(cfg.pasta_dados)
        marcas.carregar()
        if sinistro_google:
            _partir_do_google(sinistro_google, tabelas_google, base_sga, base_integ, marcas, log)

        usados: list[Path] = []
        # ---------------- SGA
        if etapa_sga:
            if entrada_sga:
                caminho, tabela = entrada_sga[-1]  # o relatório é uma foto completa: vale o mais recente
                if tabela is None:
                    linhas, ignoradas = S.ler_relatorio_html(caminho)
                    if ignoradas:
                        log.warning("Relatório SGA: colunas não usadas pela aba SGA: %s", ", ".join(ignoradas))
                else:
                    linhas = S.linhas_de_tabela(tabela, caminho.name)
                gerado = datetime.datetime.fromtimestamp(caminho.stat().st_mtime)
                base_sga.substituir(linhas, f"relatório {caminho.name} de {gerado:%d/%m/%Y %H:%M}")
                log.info("Relatório SGA %s: %d linhas.", caminho.name, len(linhas))
                registro.anotar(cfg.registro, registro.MANUAL, "SGA", "Relatório de eventos (por item)", len(linhas),
                                f"importado (salvo em {gerado:%d/%m/%Y %H:%M})", caminho.name, log)
                for antigo, _ in entrada_sga[:-1]:
                    registro.anotar(cfg.registro, registro.MANUAL, "SGA", "Relatório de eventos (por item)", "-",
                                    "não usado: havia um arquivo mais novo", antigo.name, log)
                usados += [c for c, _ in entrada_sga]
            if usar_api and cfg.api_configurada:
                try:
                    _consultar_api(cfg, base_sga, log)
                except SgaApiErro as e:
                    log.error("API SGA: %s", e)
                    registro.anotar(cfg.registro, registro.AUTOMATICO, "SGA", "API", "-", f"FALHOU: {e}", "", log)
                    codigo = PARCIAL
            elif usar_api:
                log.info("API SGA não configurada em %s (SGA_TOKEN, SGA_USUARIO, SGA_SENHA); usando só o relatório exportado.", NOME_CONFIG)
            base_sga.salvar()

        # ---------------- SIGA (DashBoard) -> INTEGRAÇÃO
        if etapa_integracao:
            for caminho, tabela in entrada_siga:
                linhas = G.linhas_de_tabela(tabela, caminho.name)
                novos, alterados = base_integ.incorporar(linhas)
                anos = ", ".join(sorted({l[G.NUMERO][:4] for l in linhas}))
                log.info("DashBoard SIGA %s (%s): %d eventos (%d novos, %d atualizados).", caminho.name, anos or "sem eventos",
                         len(linhas), novos, alterados)
                # No registro vale o ano exportado (o da maioria dos eventos); o log acima lista todos.
                contagem = collections.Counter(l[G.NUMERO][:4] for l in linhas)
                principal = contagem.most_common(1)[0][0] if contagem else ""
                rotulo = f"DashBoard {principal}" + (" (+ outros anos)" if len(contagem) > 1 else "") if principal else "DashBoard (sem eventos)"
                registro.anotar(cfg.registro, registro.MANUAL, "SIGA", rotulo, len(linhas),
                                f"importado: {novos} novos, {alterados} atualizados", caminho.name, log)
                usados.append(caminho)
            base_integ.salvar()
            # O SIGA não tem API: cada ano vem de uma exportação do DashBoard. Mostra o que já foi trazido.
            feitos, faltam = base_integ.cobertura(cfg.siga_ano_inicial, datetime.date.today().year)
            if feitos:
                log.info("SIGA: anos atualizados pelo DashBoard: %s.", "; ".join(feitos))
            if faltam:
                log.warning("SIGA: falta exportar o DashBoard dos anos %s (Dashboard Arco > Gerencial > Total Eventos "
                            "Cadastrados > Excel) e salvar na pasta ENTRADA.", ", ".join(faltam))

        # ---------------- cruzamento e gravação
        if sinistro_google:
            abas = {planilha.ABA_SIGA: tabelas_google[planilha.ABA_SIGA], planilha.ABA_TAREFAS: tabelas_google[planilha.ABA_TAREFAS]}
        else:
            nova = not cfg.planilha.exists()
            if nova:
                planilha.criar_modelo(cfg.planilha, origem.get(planilha.ABA_SIGA), origem.get(planilha.ABA_TAREFAS))
                log.info("Planilha criada: %s", cfg.planilha)
            abas = planilha.ler_abas(cfg.planilha, [planilha.ABA_SIGA, planilha.ABA_TAREFAS])
        # Relatório de tarefas do SIGA na ENTRADA: é a aba SIGA nova (colunas B a W); vale o mais recente.
        tarefas = None
        if entrada_tarefas:
            arquivo_tarefas, tabela = entrada_tarefas[-1]
            tarefas = G.linhas_de_tarefas(tabela, arquivo_tarefas.name)
            log.info("Relatório de tarefas do SIGA %s: %d tarefas; substitui a aba SIGA.", arquivo_tarefas.name, len(tarefas))
            for antigo, _ in entrada_tarefas[:-1]:
                registro.anotar(cfg.registro, registro.MANUAL, "SIGA", "Tarefas (aba SIGA)", "-",
                                "não usado: havia um arquivo mais novo", antigo.name, log)
                usados.append(antigo)
            siga = [(r, [None] + l + [None] * (integracao.SIGA_COLUNAS - 1 - len(l))) for r, l in enumerate(tarefas, 2)]
        else:
            siga = planilha.linhas_siga(abas[planilha.ABA_SIGA])
        resultado = integracao.calcular(base_sga.linhas, base_integ.linhas, siga)
        vistos = setores.SetoresVistos(cfg.pasta_dados)
        vistos.carregar()
        vistos.registrar(siga, abas[planilha.ABA_TAREFAS], datetime.date.today().isoformat())
        vistos.salvar()
        gravou_siga = False
        if sinistro_google:
            base_sga.salvar()
            base_integ.salvar()
            try:
                _gravar_sinistro_google(sinistro_google, base_sga, base_integ, marcas, log, tarefas)
                gravou_siga = tarefas is not None
            except GoogleErro as e:   # os setores e as páginas não dependem dessa gravação
                log.error("Google Sheets: %s", e)
                codigo = PARCIAL
                if tarefas is not None:
                    log.warning("O relatório de tarefas %s fica na pasta ENTRADA e é aplicado na próxima atualização.",
                                arquivo_tarefas.name)
        else:
            info = planilha.gravar(cfg.planilha, base_sga.linhas, base_integ.linhas, resultado, cfg.pasta_backups,
                                   cfg.backups_manter, fazer_backup=not nova, siga_nova=[l for _, l in siga] if tarefas is not None else None)
            gravou_siga = tarefas is not None
        if gravou_siga:
            gerado = datetime.datetime.fromtimestamp(arquivo_tarefas.stat().st_mtime)
            registro.anotar(cfg.registro, registro.MANUAL, "SIGA", "Tarefas (aba SIGA)", len(tarefas),
                            f"importado (salvo em {gerado:%d/%m/%Y %H:%M})", arquivo_tarefas.name, log)
            usados.append(arquivo_tarefas)
        _arquivar(usados, cfg, log)

        r = resultado.resumo
        log.info("Aba SGA: %d linhas (%d com STATUS SIGA). Origem dos dados: %s.", r["sga_linhas"], r["sga_com_status_siga"], base_sga.origem or "-")
        log.info("Aba INTEGRAÇÃO: %d eventos do SIGA.", r["integracao_linhas"])
        log.info("Aba SIGA: %d linhas; %d sem vínculo na INTEGRAÇÃO; %d sem correspondência no SGA.",
                 r["siga_linhas"], r["siga_sem_integracao"], r["siga_sem_sga"])
        if not sinistro_google:
            log.info("Gravado: %s (backup da versão anterior: %s).", cfg.planilha, info["backup"] or "não há")

        # ---------------- planilhas dos setores, abastecidas pelo sinistro
        if etapa_setores:
            falhas, incorporados = setores.atualizar(cfg, log, siga, resultado, abas[planilha.ABA_TAREFAS], base_sga.linhas,
                                                     base_integ.linhas, entrada_pagina, google=conta,
                                                     base_vistoria=tabelas_google.get(setores.ABA_BASE_VISTORIA))
            _arquivar(incorporados, cfg, log)
            if falhas:
                codigo = PARCIAL
        elif entrada_pagina:
            log.info("%d arquivo(s) da página de acompanhamento ficam para a próxima atualização completa.", len(entrada_pagina))
        # ---------------- página HTML da conferência de finalizados
        if etapa_painel and cfg.painel_finalizados:
            try:
                r = painel.gerar(cfg.painel_finalizados, base_sga.linhas, base_integ.linhas, resultado, cfg.painel_desde, base_sga.origem,
                                 vistos)
                log.info("Página %s: %d eventos liberados desde %s; anotações: %d a verificar, %d a excluir, %d sem motivo; "
                         "%d com status diferente SIGA x SGA; %d sem correspondência no SGA; %d com setor registrado.",
                         cfg.painel_finalizados.name, r["eventos"], cfg.painel_desde.strftime("%d/%m/%Y"), r["anotacoes"]["arquivado"],
                         r["anotacoes"]["excluir"], r["anotacoes"]["motivo"], r["divergentes"], r["sem_sga"], r["com_setor"])
            except OSError as e:
                log.error("Não consegui gravar a página %s (%s).", cfg.painel_finalizados, e)
                codigo = PARCIAL
        log.info("Tempo total: %.0fs.", time.time() - inicio)
    except planilha.PlanilhaAberta as e:
        log.error("%s Os dados já foram atualizados; basta rodar de novo com a planilha fechada.", e)
        codigo = FALHA
    except GoogleErro as e:
        log.error("Google Sheets: %s", e)
        codigo = FALHA
    except Exception:
        log.exception("Erro inesperado; a planilha não foi alterada.")
        codigo = FALHA
    log.info("==== Fim (%s) ====", {OK: "sucesso", PARCIAL: "concluído com avisos", FALHA: "falhou"}[codigo])
    return codigo


def diagnostico_api() -> int:
    """Testa o acesso à API com os últimos 30 dias e mostra o que ela devolve."""
    cfg = carregar_config()
    log = configurar_log(cfg.pasta_logs)
    if not cfg.api_configurada:
        log.error("Preencha SGA_TOKEN, SGA_USUARIO e SGA_SENHA no arquivo %s.", NOME_CONFIG)
        return FALHA
    try:
        api = SgaApi(cfg.api_url, cfg.token, cfg.usuario, cfg.senha, log)
        api.autenticar()
        log.info("Autenticação OK.")
        classificacoes = api.classificacoes()
        hoje = datetime.date.today()
        itens = api.listar_eventos(hoje - datetime.timedelta(days=29), hoje, cfg.por_pagina)
    except SgaApiErro as e:
        log.error("API SGA: %s", e)
        return FALHA
    log.info("Itens de evento nos últimos 30 dias: %d (em %d chamadas). Classificações: %d.", len(itens), api.chamadas, len(classificacoes))
    if not itens:
        # A busca de eventos não trouxe nada: testa outros formatos da mesma chamada para achar o que a API aceita.
        base = S.BaseSga(cfg.pasta_dados)
        protocolo = base.linhas[-1][S.PROTOCOLO] if base.carregar() and base.linhas else ""
        log.warning("Nenhum evento veio na busca padrão. Testando outros formatos da chamada listar/evento:")
        try:
            for nome, status, quantidade, mensagem in api.sondar_eventos(hoje - datetime.timedelta(days=29), hoje, protocolo):
                log.info("  %-30s HTTP %s  itens: %-5d %s", nome, status, quantidade, mensagem)
        except SgaApiErro as e:
            log.error("API SGA: %s", e)
        log.info("Copie as linhas acima e envie para ajustar a integração.")
        return PARCIAL
    campos = sorted({(f"{k}.{k2}" if isinstance(v, dict) else k) for item in itens for k, v in item.items()
                     for k2 in (v if isinstance(v, dict) else [None])})
    log.info("Campos devolvidos pela API: %s", ", ".join(campos))
    amostra = cfg.pasta_logs / "diagnostico_api.json"
    amostra.write_text(json.dumps(itens[:3], ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Amostra de 3 itens salva em %s (contém dados de associados; não compartilhe sem necessidade).", amostra)

    base = S.BaseSga(cfg.pasta_dados)
    if base.carregar():
        por_chave = {}
        for linha in base.linhas:
            por_chave.setdefault((linha[S.PROTOCOLO], S._comparavel(linha[S.TIPO])), []).append(linha)
        normalizados = _normalizar(api, itens, classificacoes)
        log.info("Comparação com a base atual (%s), nos protocolos em comum. (*) = coluna de identidade, "
                 "que a API nunca sobrescreve numa linha existente:", base.origem or "sem origem")
        for campo in S.CAMPOS_API:
            iguais = total = 0
            exemplo = ""
            for item in normalizados:
                candidatas = por_chave.get((item[S.PROTOCOLO], S._comparavel(item[S.TIPO])), [])
                if len(candidatas) == 1 and candidatas[0][campo] and item[campo]:
                    total += 1
                    if S._comparavel(candidatas[0][campo]) == S._comparavel(item[campo]):
                        iguais += 1
                    elif not exemplo:
                        exemplo = f" | ex.: base='{candidatas[0][campo]}' API='{item[campo]}'"
            nome = S.COLUNAS[campo][0] + (" (*)" if campo in S.CAMPOS_IDENTIDADE else "")
            log.info("  %-44s %d de %d iguais%s", nome, iguais, total, exemplo)

    # A busca completa trouxe bem menos itens que a base (e nada em alguns meses): testa como a API pagina.
    fim_mes = hoje.replace(day=1) - datetime.timedelta(days=1)
    janelas = [("Mês passado", fim_mes.replace(day=1), fim_mes), ("Período que respondeu 406", datetime.date(2023, 8, 13), datetime.date(2023, 9, 11))]
    linhas_base = base.linhas if base.linhas else []
    def esperado(ini, fim):
        return sum(1 for l in linhas_base if (d := data_br(l[S.DT_COMUNICADO])) and ini <= d <= fim)
    log.info("Teste da paginação de listar/evento (leva alguns minutos):")
    try:
        for texto_linha in api.sondar_paginacao([(n, a, b, esperado(a, b)) for n, a, b in janelas]):
            log.info("%s", texto_linha)
    except SgaApiErro as e:
        log.error("API SGA: %s", e)
    log.info("Copie tudo a partir de 'Teste da paginação' e envie para ajustar a busca de eventos.")
    return OK
