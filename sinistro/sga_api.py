"""Cliente da API oficial do SGA Hinova (https://api.hinova.com.br/api/sga/v2/doc/).

Autenticação: o token gerado no SGA (Área Cliente > APIs > Gerenciar APIs) vai no cabeçalho
Authorization de POST /usuario/autenticar junto com usuário e senha; a resposta traz o
token_usuario, usado nas demais chamadas.

Eventos: POST /listar/evento filtra por data de cadastro em janelas de no máximo 30 dias.
"""
from __future__ import annotations

import datetime
import json
import re
import time
import urllib.error
import urllib.request

from . import sga_base as S
from .util import formatar_reais, sem_acento, texto

JANELA_DIAS = 30
MAX_PAGINAS = 2000
TENTATIVAS = 6   # esperas de 2, 4, 8, 16 e 32 s entre elas: quedas curtas da API não derrubam a rotina
LIMITE_POR_PAGINA = 100  # acima disso listar/evento responde HTTP 406 "Não aceitável" (testado em 14/10/2026)

UFS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
    "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA",
    "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO",
}


class SgaApiErro(Exception):
    pass


def _data_para_br(v) -> str:
    """'2026-10-08' ou '2026-10-08T00:00:00-0300' -> '08/10/2026'. Mantém o que já vier em dd/mm/aaaa."""
    s = texto(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return s


def _uf(v) -> str:
    s = texto(v).strip()
    if len(s) <= 2:
        return s.upper()
    return UFS.get(sem_acento(s).upper(), s)


def _reais(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return formatar_reais(float(v))
    s = texto(v).replace("R$", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return formatar_reais(float(s))
    except ValueError:
        return texto(v)


def _sub(item: dict, grupo: str, campo: str) -> str:
    g = item.get(grupo)
    return texto(g.get(campo)).strip() if isinstance(g, dict) else ""


def normalizar_evento(item: dict, classificacoes: dict[str, str], fornecedores: dict[str, dict] | None = None,
                      vistoriadores: dict[str, str] | None = None) -> list[str]:
    """Item devolvido por listar/evento -> linha no formato da aba SGA (colunas da API preenchidas).

    Nos itens de terceiro, o "veiculo" que a API devolve é o do terceiro e não vem o associado;
    nome e placa do associado são completados depois por completar_por_protocolo().
    """
    linha = [""] * S.N_COLUNAS
    linha[S.PROTOCOLO] = texto(item.get("protocolo") or item.get("protocolo_evento")).strip()
    linha[S.TIPO] = texto(item.get("evento_tipo")).strip()
    linha[S.MOTIVO] = texto(item.get("motivo")).strip()
    linha[S.NOME_ASSOCIADO] = _sub(item, "associado", "nome")
    placa = _sub(item, "veiculo", "placa").replace("-", "")
    if linha[S.TIPO].upper() == "ASSOCIADO":
        linha[S.PLACA] = placa
    else:
        linha[S.PLACA_TERCEIRO] = placa
        linha[S.NOME_TERCEIRO] = _sub(item, "terceiro", "nome")
    linha[S.CIDADE] = _sub(item, "associado", "cidade")
    linha[S.UF] = _uf(_sub(item, "associado", "estado"))
    linha[S.ANALISTA] = texto(item.get("usuario_analista_responsavel")).strip()
    linha[S.DT_COMUNICADO] = _data_para_br(item.get("data_comunicado_evento"))
    for processo in item.get("processos_data") or []:  # as 7 datas de processo (análise do regulador, autorização...)
        if isinstance(processo, dict):
            coluna = S.coluna_de_processo(processo.get("tipo"))
            if coluna is not None:
                linha[coluna] = _data_para_br(processo.get("data"))
    linha[S.SITUACAO] = texto(item.get("situacao_evento")).strip()
    vistoriador = _sub(item, "vistoriador", "codigo")
    if vistoriador not in ("", "0") and vistoriadores:
        linha[S.VISTORIADOR] = vistoriadores.get(vistoriador, "")
    fornecedor = (fornecedores or {}).get(texto(item.get("codigo_fornecedor_oficina")).strip())
    if fornecedor:
        linha[S.FORNECEDOR] = texto(fornecedor.get("nome")).strip()
        linha[S.OFICINAS] = texto(fornecedor.get("nome_fantasia")).strip()
        linha[S.CNPJ] = re.sub(r"\D", "", texto(fornecedor.get("cpf_cnpj")))
    linha[S.VOLUNTARIO] = _sub(item, "voluntario", "nome") or _sub(item, "voluntario", "descricao")
    linha[S.COOPERATIVA] = _sub(item, "cooperativa", "descricao")
    linha[S.CLASSIFICACAO] = classificacoes.get(texto(item.get("codigo_classificacao")).strip(), "")
    linha[S.DT_EVENTO] = _data_para_br(item.get("data_evento"))
    linha[S.PARTICIPACAO] = _reais(item.get("participacao"))
    return linha


def completar_por_protocolo(linhas: list[list[str]]) -> list[list[str]]:
    """Copia nome, placa, cidade e estado do associado para os itens de terceiro do mesmo protocolo."""
    associado: dict[str, list[str]] = {}
    for linha in linhas:
        if linha[S.TIPO].upper() == "ASSOCIADO":
            associado.setdefault(linha[S.PROTOCOLO], linha)
    for linha in linhas:
        origem = associado.get(linha[S.PROTOCOLO])
        if origem is not None and origem is not linha:
            for campo in (S.NOME_ASSOCIADO, S.PLACA, S.CIDADE, S.UF):
                linha[campo] = linha[campo] or origem[campo]
    return linhas


class SgaApi:
    def __init__(self, url: str, token: str, usuario: str, senha: str, log, pausa: float = 0.15, timeout: int = 90):
        self.url = url.rstrip("/")
        self.token = token
        self.usuario = usuario
        self.senha = senha
        self.log = log
        self.pausa = pausa
        self.timeout = timeout
        self.token_usuario = ""
        self.chamadas = 0
        self._avisos: set[str] = set()

    def _requisicao(self, metodo: str, caminho: str, corpo: dict | None = None, token: str | None = None):
        """Devolve (status, dados). Repete em falhas de rede, 429 e 5xx."""
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(f"{self.url}/{caminho.lstrip('/')}", data=dados, method=metodo, headers={
            "Authorization": f"Bearer {token or self.token_usuario}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sinistro-sga/1.0",
        })
        ultimo_erro = None
        for tentativa in range(TENTATIVAS):
            if tentativa:
                time.sleep(2 ** tentativa)
            self.chamadas += 1
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status, bruto = resp.status, resp.read()
            except urllib.error.HTTPError as e:
                status, bruto = e.code, e.read()
                if status == 429 or status >= 500:
                    ultimo_erro = f"HTTP {status}"
                    continue
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                ultimo_erro = str(e)
                continue
            time.sleep(self.pausa)
            try:
                return status, json.loads(bruto.decode("utf-8", "replace")) if bruto.strip() else None
            except json.JSONDecodeError:
                return status, bruto.decode("utf-8", "replace")[:500]
        if ultimo_erro in ("HTTP 502", "HTTP 503", "HTTP 504"):
            raise SgaApiErro(f"a API do SGA (Hinova) está fora do ar ({ultimo_erro} em {caminho}, mesmo depois de {TENTATIVAS} tentativas "
                             "em cerca de 1 minuto). Não é problema de senha nem do sistema: tente de novo mais tarde.")
        raise SgaApiErro(f"Sem resposta de {caminho} após {TENTATIVAS} tentativas ({ultimo_erro}).")

    def autenticar(self) -> None:
        status, dados = self._requisicao("POST", "usuario/autenticar",
                                         {"usuario": self.usuario, "senha": self.senha}, token=self.token)
        tok = dados.get("token_usuario") if isinstance(dados, dict) else None
        if status != 200 or not tok:
            raise SgaApiErro(
                f"Falha na autenticação (HTTP {status}): {_resumo(dados)}. Confira SGA_TOKEN, SGA_USUARIO e "
                "SGA_SENHA na configuração e se o token está com 'Permitir Acesso = SIM' em Área Cliente > APIs > Gerenciar APIs.")
        self.token_usuario = tok

    def classificacoes(self) -> dict[str, str]:
        """Código -> descrição das classificações de evento. Vazio se o endpoint não estiver liberado."""
        status, dados = self._requisicao("GET", "listar/classificacao-evento/todos")
        if status != 200 or not isinstance(dados, list):
            self.log.warning("API: não consegui listar as classificações de evento (HTTP %s): %s", status, _resumo(dados))
            return {}
        return {texto(c.get("codigo")).strip(): texto(c.get("descricao")).strip() for c in dados if isinstance(c, dict)}

    def _lista(self, caminho: str) -> list[dict]:
        """GET de uma listagem; vazio (com aviso) se o endpoint não estiver liberado no token."""
        status, dados = self._requisicao("GET", caminho)
        if isinstance(dados, dict):
            dados = next((v for v in dados.values() if isinstance(v, list)), [dados] if "nome" in dados else None)
        if status != 200 or not isinstance(dados, list):
            self.log.warning("API: não consegui ler %s (HTTP %s): %s", caminho, status, _resumo(dados))
            return []
        return [d for d in dados if isinstance(d, dict)]

    def fornecedores(self) -> dict[str, dict]:
        """Código -> fornecedor (nome, nome_fantasia, cpf_cnpj), para a oficina de cada evento."""
        return {texto(f.get("codigo_fornecedor")).strip(): f for f in self._lista("listar/fornecedor/todos")}

    def vistoriadores(self) -> dict[str, str]:
        """Código -> nome do vistoriador (regulador)."""
        return {texto(v.get("codigo_vistoriador")).strip(): texto(v.get("nome")).strip() for v in self._lista("listar/vistoriador/todos")}

    def _pagina(self, corpo: dict) -> list[dict]:
        status, dados = self._requisicao("POST", "listar/evento", corpo)
        if status in (401, 403):
            raise SgaApiErro(
                f"Acesso negado a listar/evento (HTTP {status}): {_resumo(dados)}. Libere o endpoint "
                "'Evento - Listar' no token em Área Cliente > APIs > Gerenciar APIs.")
        if isinstance(dados, list):
            return [d for d in dados if isinstance(d, dict)]
        if isinstance(dados, dict):
            for valor in dados.values():
                if isinstance(valor, list) and valor and isinstance(valor[0], dict):
                    return valor
        if status in (200, 204, 400, 404, 406):
            # A API responde com uma mensagem (e não uma lista) quando o período não tem eventos.
            # 400 e 406 podem ser parâmetro recusado (o 406 já foi visto com página grande demais), então viram aviso.
            self._avisar(f"listar/evento sem lista de eventos (HTTP {status}): {_resumo(dados)}", aviso=status in (400, 406))
            return []
        raise SgaApiErro(f"listar/evento respondeu HTTP {status}: {_resumo(dados)}")

    def _avisar(self, mensagem: str, aviso: bool = True) -> None:
        """Registra cada mensagem diferente uma única vez por execução."""
        if mensagem not in self._avisos:
            self._avisos.add(mensagem)
            self.log.log(30 if aviso else 20, "API: %s", mensagem)

    def listar_eventos(self, inicio: datetime.date, fim: datetime.date, por_pagina: int = LIMITE_POR_PAGINA) -> list[dict]:
        """Todos os itens de evento cadastrados entre as duas datas."""
        if not self.token_usuario:
            self.autenticar()
        por_pagina = max(1, min(por_pagina, LIMITE_POR_PAGINA))
        itens: dict[str, dict] = {}
        dia = inicio
        while dia <= fim:
            ate = min(dia + datetime.timedelta(days=JANELA_DIAS - 1), fim)
            vistos: set[str] = set()
            posicao, por_deslocamento = 0, False
            for _ in range(MAX_PAGINAS):
                pagina = self._pagina({
                    "data_cadastro": dia.strftime("%d/%m/%Y"), "data_cadastro_final": ate.strftime("%d/%m/%Y"),
                    "inicio_paginacao": posicao, "quantidade_por_pagina": por_pagina,
                })
                novos = 0
                for item in pagina:
                    chave = texto(item.get("codigo")) or json.dumps(item, sort_keys=True, ensure_ascii=False)
                    if chave not in vistos:
                        vistos.add(chave)
                        itens[f"{dia}|{chave}"] = item
                        novos += 1
                if novos == 0:
                    if pagina and posicao:
                        self._avisar("uma página repetiu os mesmos eventos da anterior; se o total de itens parecer "
                                     "baixo, a paginação da API não está respondendo como documentado")
                    break
                if len(pagina) < por_pagina:  # página incompleta: era a última do período
                    break
                # A documentação não diz se inicio_paginacao é nº da página ou deslocamento.
                # Se a "página 1" repetir quase tudo da anterior, é deslocamento.
                if not por_deslocamento and posicao >= 1 and len(pagina) > 5 and novos < len(pagina) / 2:
                    por_deslocamento = True
                posicao = len(vistos) if por_deslocamento else posicao + 1
            self.log.info("API: %s a %s -> %d itens", dia.strftime("%d/%m/%Y"), ate.strftime("%d/%m/%Y"), len(vistos))
            dia = ate + datetime.timedelta(days=1)
        return list(itens.values())

    def sondar_eventos(self, inicio: datetime.date, fim: datetime.date, protocolo: str = "") -> list[tuple[str, int, int, str]]:
        """Tenta variações da chamada listar/evento, para descobrir qual formato a API aceita.

        Devolve (variação, HTTP, quantidade de itens, mensagem da API) para cada tentativa.
        """
        ini, ult = inicio.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")
        ontem = (fim - datetime.timedelta(days=1)).strftime("%d/%m/%Y")
        variacoes = [
            ("periodo, sem paginacao", {"data_cadastro": ini, "data_cadastro_final": ult}),
            ("periodo, 100 por pagina", {"data_cadastro": ini, "data_cadastro_final": ult, "inicio_paginacao": 0, "quantidade_por_pagina": 100}),
            ("periodo, paginacao em texto", {"data_cadastro": ini, "data_cadastro_final": ult, "inicio_paginacao": "0", "quantidade_por_pagina": "100"}),
            ("periodo de 7 dias", {"data_cadastro": (fim - datetime.timedelta(days=6)).strftime("%d/%m/%Y"), "data_cadastro_final": ult}),
            ("so o dia de ontem", {"data_cadastro": ontem}),
        ]
        if protocolo:
            variacoes.append((f"protocolo {protocolo}", {"protocolo": protocolo}))
        resultado = []
        for nome, corpo in variacoes:
            status, dados = self._requisicao("POST", "listar/evento", corpo)
            if isinstance(dados, list):
                lista = [d for d in dados if isinstance(d, dict)]
            elif isinstance(dados, dict):
                lista = next((v for v in dados.values() if isinstance(v, list)), [])
            else:
                lista = []
            resultado.append((nome, status, len(lista), "" if lista else _resumo(dados)))
        return resultado

    def sondar_paginacao(self, janelas: list[tuple[str, datetime.date, datetime.date, int]]) -> list[str]:
        """Mostra como listar/evento pagina: para cada (rótulo, início, fim, linhas esperadas), pede páginas
        por número e por deslocamento, com tamanhos diferentes, e em períodos menores. Só lê."""
        saida = []

        def pedir(ini, fim, inicio_paginacao, quantidade):
            status, dados = self._requisicao("POST", "listar/evento", {
                "data_cadastro": ini.strftime("%d/%m/%Y"), "data_cadastro_final": fim.strftime("%d/%m/%Y"),
                "inicio_paginacao": inicio_paginacao, "quantidade_por_pagina": quantidade})
            if isinstance(dados, list):
                lista = [d for d in dados if isinstance(d, dict)]
            elif isinstance(dados, dict):
                lista = next((v for v in dados.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
            else:
                lista = []
            return status, lista, "" if lista else _resumo(dados)

        def linha(rotulo, status, lista, msg, vistos):
            codigos = [texto(i.get("codigo")) for i in lista]
            novos = len(set(codigos) - vistos)
            repetidos_na_pagina = len(codigos) - len(set(codigos))
            datas = sorted(texto(i.get("data_cadastro"))[:10] for i in lista if i.get("data_cadastro"))
            faixa = f"cadastro {datas[0]} a {datas[-1]}" if datas else ""
            cods = sorted(int(c) for c in codigos if c.isdigit())
            faixa_cod = f"código {cods[0]} a {cods[-1]}" if cods else ""
            vistos |= set(codigos)
            saida.append(f"  {rotulo:<34} HTTP {status}  itens {len(lista):>3}  novos {novos:>3}  repetidos {repetidos_na_pagina:>2}  "
                         f"{faixa}  {faixa_cod}  {msg[:80]}".rstrip())

        for nome, ini, fim, esperado in janelas:
            saida.append(f"{nome}: {ini:%d/%m/%Y} a {fim:%d/%m/%Y} (a base tem {esperado} linhas comunicadas no período)")
            vistos: set[str] = set()
            for p in range(6):
                status, lista, msg = pedir(ini, fim, p, 100)
                linha(f"página nº {p} (100 por página)", status, lista, msg, vistos)
                if not lista:
                    break
            for desloc in (100, 200):
                status, lista, msg = pedir(ini, fim, desloc, 100)
                linha(f"deslocamento {desloc} (100 por página)", status, lista, msg, vistos)
            for p in range(3):
                status, lista, msg = pedir(ini, fim, p, 50)
                linha(f"página nº {p} (50 por página)", status, lista, msg, set())
            total_semanas = total_dias = 0
            semana = ini
            while semana <= fim:
                ate = min(semana + datetime.timedelta(days=6), fim)
                status, lista, msg = pedir(semana, ate, 0, 100)
                linha(f"semana {semana:%d/%m}-{ate:%d/%m}, página 0", status, lista, msg, set())
                total_semanas += len(lista)
                semana = ate + datetime.timedelta(days=1)
            for d in range(7):
                dia = ini + datetime.timedelta(days=d)
                if dia > fim:
                    break
                status, lista, msg = pedir(dia, dia, 0, 100)
                linha(f"dia {dia:%d/%m/%Y}, página 0", status, lista, msg, set())
                total_dias += len(lista)
            saida.append(f"  soma das semanas (só página 0): {total_semanas}; soma dos 7 primeiros dias: {total_dias}")
        return saida


def _resumo(dados) -> str:
    if isinstance(dados, dict):
        return texto(dados.get("mensagem") or dados.get("error") or dados.get("message") or json.dumps(dados, ensure_ascii=False))[:300]
    return texto(dados)[:300]
