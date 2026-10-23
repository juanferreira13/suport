"""Planilhas do Google Sheets, acessadas pela conta de serviço (chave JSON em GOOGLE_CREDENCIAIS).

Lê e grava como as planilhas .xlsx do sistema: `ler_abas` devolve listas de linhas e `substituir_aba` troca
só as colunas que o sistema gera, da linha 2 para baixo, sem mexer no cabeçalho, nas fórmulas das outras
colunas nem nas colunas digitadas pela equipe. As gravações ficam numa fila e vão de uma vez em `salvar`.

A planilha precisa estar compartilhada (como Editor) com o e-mail da conta de serviço.
"""
from __future__ import annotations

import datetime
import math
import re
import time
from pathlib import Path

ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
LINHAS_POR_FAIXA = 2500        # linhas por faixa gravada
LINHAS_POR_ENVIO = 10000       # linhas por chamada de gravação (o Google recomenda envios de poucos MB)
_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})")
_EPOCA = datetime.datetime(1899, 12, 30)
AZUL, VERDE = {"red": 0.12, "green": 0.31, "blue": 0.47}, {"red": 0.33, "green": 0.51, "blue": 0.21}


class GoogleErro(Exception):
    pass


def id_da_planilha(valor: str) -> str:
    """Aceita o link da planilha ou só o código dela."""
    m = _ID.search(valor or "")
    return m.group(1) if m else (valor or "").strip()


def letra(n: int) -> str:
    """1 -> A, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _celula(v):
    """Valor Python -> valor gravado (sem interpretação: texto continua texto). Datas viram o número de série."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, datetime.datetime):
        return (v - _EPOCA).total_seconds() / 86400
    if isinstance(v, datetime.date):
        return (v - _EPOCA.date()).days
    if isinstance(v, float):
        return "" if math.isnan(v) else (int(v) if v == int(v) else v)
    if isinstance(v, int):
        return v
    if type(v).__name__ in ("Formula", "SeVazia"):
        raise ValueError("fórmulas não são gravadas no Google pelo sistema; calcule o valor")
    return str(v)


def _padrao_data(formato_excel: str) -> dict:
    padrao = formato_excel.lower()
    return {"type": "DATE_TIME" if "h" in padrao else "DATE", "pattern": padrao}


class Cliente:
    """Sessão autenticada com a conta de serviço."""

    def __init__(self, credenciais: Path):
        if not credenciais or not Path(credenciais).exists():
            raise GoogleErro(f"chave da conta de serviço não encontrada ({credenciais}); confira GOOGLE_CREDENCIAIS")
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        cred = service_account.Credentials.from_service_account_file(str(credenciais), scopes=ESCOPOS)
        self.email = cred.service_account_email
        self.sessao = AuthorizedSession(cred)
        self.chamadas = 0

    def pedir(self, metodo: str, url: str, **kw) -> dict:
        """Chamada à API; repete em falha de rede, limite de uso (429) e erro do servidor (5xx)."""
        import requests
        from google.auth import exceptions as erros_google
        erro = ""
        for tentativa in range(6):
            if tentativa:
                time.sleep(min(60, 2 ** tentativa))
            self.chamadas += 1
            try:
                r = self.sessao.request(metodo, url, timeout=300, **kw)
            except (requests.RequestException, erros_google.TransportError) as e:   # sem internet, proxy, queda de rede
                erro = str(e)[:200]
                continue
            except erros_google.RefreshError as e:   # chave apagada ou desativada no Google Cloud
                raise GoogleErro(f"o Google recusou a chave da conta de serviço {self.email} ({e}); gere uma chave nova "
                                 "em Google Cloud > IAM > Contas de serviço > Chaves e troque o arquivo da pasta sistema") from None
            if r.status_code == 429 or r.status_code >= 500:
                erro = f"HTTP {r.status_code}"
                continue
            if r.status_code >= 400:
                raise GoogleErro(self._mensagem(r))
            return r.json() if r.content else {}
        raise GoogleErro(f"não foi possível falar com o Google depois de várias tentativas: confira a internet deste computador ({erro})")

    def _mensagem(self, r) -> str:
        try:
            texto = r.json().get("error", {}).get("message", "")
        except ValueError:
            texto = r.text[:200]
        if r.status_code == 403:
            return f"sem acesso (HTTP 403): compartilhe a planilha com {self.email} como Editor. {texto}"
        if r.status_code == 404:
            return f"planilha não encontrada (HTTP 404): confira o link na configuração. {texto}"
        return f"HTTP {r.status_code}: {texto}"


class PlanilhaGoogle:
    def __init__(self, cliente: Cliente, ident: str):
        self.cliente, self.id = cliente, id_da_planilha(ident)
        self._valores: list[dict] = []      # faixas a gravar
        self._limpar: list[str] = []        # faixas a esvaziar
        self._grade: list[dict] = []        # linhas/colunas a acrescentar (vão antes de tudo)
        self._formatos: list[dict] = []     # formatos e cópias de fórmula (vão depois dos valores)
        self._alvos: list[tuple] = []       # (aba, linha inicial, linha final, coluna inicial, coluna final), base 0, fim aberto
        self.recarregar()

    # --------------------------------------------------------------------- estrutura
    def recarregar(self) -> None:
        d = self.cliente.pedir("GET", f"{API}/{self.id}", params={
            "fields": "properties(title),sheets(properties(sheetId,title,index,hidden,gridProperties(rowCount,columnCount)),"
                      "protectedRanges(range,requestingUserCanEdit,warningOnly))"})
        self.titulo = d["properties"]["title"]
        self.abas = {}
        for sh in d["sheets"]:
            p = sh["properties"]
            self.abas[p["title"]] = {"id": p["sheetId"], "indice": p["index"], "oculta": bool(p.get("hidden")),
                                     "linhas": p["gridProperties"].get("rowCount", 0), "colunas": p["gridProperties"].get("columnCount", 0),
                                     # áreas protegidas que a conta de serviço não pode editar
                                     "protegidas": [pr.get("range", {}) for pr in sh.get("protectedRanges", [])
                                                    if not pr.get("requestingUserCanEdit") and not pr.get("warningOnly")]}

    def aba(self, nome: str) -> str | None:
        """Nome real da aba (tolera espaços sobrando no nome)."""
        if nome in self.abas:
            return nome
        return next((t for t in self.abas if t.strip().upper() == nome.strip().upper()), None)

    def aba_por_padrao(self, padrao: re.Pattern) -> str | None:
        """Aba cujo nome casa com o padrão: a visível ou, entre as ocultas, a de data mais recente (dd/mm no nome)."""
        candidatas = [t for t in self.abas if padrao.fullmatch(t.strip())]
        visiveis = [t for t in candidatas if not self.abas[t]["oculta"]]
        if visiveis:
            return visiveis[0]

        def data(t):
            m = re.search(r"(\d{1,2})/(\d{1,2})", t)
            return (int(m.group(2)), int(m.group(1))) if m else (0, 0)
        return max(candidatas, key=data, default=None)

    @staticmethod
    def _faixa(aba: str, faixa: str = "") -> str:
        return "'" + aba.replace("'", "''") + "'" + (f"!{faixa}" if faixa else "")

    # --------------------------------------------------------------------- leitura
    def ler_abas(self, pedidos: dict[str, str | None]) -> dict[str, list[list] | None]:
        """{nome da aba: colunas ('A:AB') ou None para a aba inteira} -> {nome: linhas}. Aba inexistente = None.

        Datas vêm como texto formatado (dd/mm/aaaa, como a equipe vê); números e textos, sem formatação."""
        saida: dict[str, list[list] | None] = {}
        reais = []
        for nome, colunas in pedidos.items():
            real = self.aba(nome)
            saida[nome] = None
            if real:
                reais.append((nome, self._faixa(real, colunas or "")))
        for k in range(0, len(reais), 20):
            parte = reais[k:k + 20]
            d = self.cliente.pedir("GET", f"{API}/{self.id}/values:batchGet", params=[("ranges", f) for _, f in parte] + [
                ("valueRenderOption", "UNFORMATTED_VALUE"), ("dateTimeRenderOption", "FORMATTED_STRING")])
            for (nome, _), faixa in zip(parte, d.get("valueRanges", [])):
                saida[nome] = faixa.get("values", [])
        return saida

    def formulas(self, aba: str, faixa: str) -> list[list]:
        real = self.aba(aba)
        d = self.cliente.pedir("GET", f"{API}/{self.id}/values/{requests_quote(self._faixa(real, faixa))}",
                               params={"valueRenderOption": "FORMULA"})
        return d.get("values", [])

    # --------------------------------------------------------------------- gravação
    def criar_aba(self, nome: str, cabecalho: list[str], manuais: tuple = (), indice: int = 0) -> str:
        """Cria a aba (na hora) com o cabeçalho: azul nas colunas da equipe, verde nas do sistema."""
        colunas = max(26, len(cabecalho))
        r = self.cliente.pedir("POST", f"{API}/{self.id}:batchUpdate", json={"requests": [{"addSheet": {"properties": {
            "title": nome, "index": indice, "gridProperties": {"rowCount": 1000, "columnCount": colunas, "frozenRowCount": 1}}}}]})
        aba_id = r["replies"][0]["addSheet"]["properties"]["sheetId"]
        pedidos = [{"repeatCell": {
            "range": {"sheetId": aba_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": len(cabecalho)},
            "cell": {"userEnteredFormat": {"backgroundColor": VERDE, "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE",
                                           "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
            "fields": "userEnteredFormat(backgroundColor,wrapStrategy,verticalAlignment,textFormat)"}}]
        for c in manuais:
            pedidos.append({"repeatCell": {
                "range": {"sheetId": aba_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": c, "endColumnIndex": c + 1},
                "cell": {"userEnteredFormat": {"backgroundColor": AZUL}}, "fields": "userEnteredFormat.backgroundColor"}})
        pedidos.append({"setBasicFilter": {"filter": {"range": {"sheetId": aba_id, "startRowIndex": 0, "startColumnIndex": 0,
                                                                "endColumnIndex": len(cabecalho)}}}})
        self.cliente.pedir("POST", f"{API}/{self.id}:batchUpdate", json={"requests": pedidos})
        self.cliente.pedir("PUT", f"{API}/{self.id}/values/{requests_quote(self._faixa(nome, 'A1'))}",
                           params={"valueInputOption": "RAW"}, json={"values": [cabecalho]})
        self.recarregar()
        return nome

    def ocultar_aba(self, aba: str) -> bool:
        """Oculta a aba (na hora). Devolve False se ela não existe ou já estava oculta."""
        real = self.aba(aba)
        if real is None or self.abas[real]["oculta"]:
            return False
        self.cliente.pedir("POST", f"{API}/{self.id}:batchUpdate", json={"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": self.abas[real]["id"], "hidden": True}, "fields": "hidden"}}]})
        self.abas[real]["oculta"] = True
        return True

    def completar_cabecalho(self, aba: str, cabecalho: list[str]) -> None:
        """Escreve os títulos que faltam (células vazias da linha 1); os que existem ficam como estão."""
        real = self.aba(aba)
        atual = (self.ler_abas({real: "1:1"})[real] or [[]])
        atual = atual[0] if atual else []
        for c, titulo in enumerate(cabecalho):
            if c >= len(atual) or str(atual[c]).strip() == "":
                self._valores.append({"range": self._faixa(real, f"{letra(c + 1)}1"), "values": [[titulo]]})
                self._alvos.append((real, 0, 1, c, c + 1))

    def substituir_aba(self, aba: str, linhas: list[list], n_colunas: int, formatos: dict[int, str] | None = None,
                       primeira_coluna: int = 0) -> int:
        """Troca os dados (da linha 2 para baixo) das colunas [primeira_coluna, n_colunas) e esvazia o que sobrar
        abaixo. `formatos`: {coluna: formato de data do Excel, ex. 'DD/MM/YYYY'}. Devolve a última linha gravada."""
        real = self.aba(aba)
        if real is None:
            raise GoogleErro(f"a planilha {self.titulo} não tem a aba {aba}")
        info = self.abas[real]
        n = len(linhas)
        ultima = n + 1
        if info["linhas"] < ultima + 1:
            self._grade.append({"appendDimension": {"sheetId": info["id"], "dimension": "ROWS", "length": ultima + 200 - info["linhas"]}})
            info["linhas"] = ultima + 200
        if info["colunas"] < n_colunas:
            self._grade.append({"appendDimension": {"sheetId": info["id"], "dimension": "COLUMNS", "length": n_colunas - info["colunas"]}})
            info["colunas"] = n_colunas
        c1, c2 = letra(primeira_coluna + 1), letra(n_colunas)
        self._alvos.append((real, 1, max(ultima, info["linhas"]), primeira_coluna, n_colunas))
        for k in range(0, n, LINHAS_POR_FAIXA):
            bloco = [[_celula(v) for v in (list(l) + [None] * n_colunas)[primeira_coluna:n_colunas]] for l in linhas[k:k + LINHAS_POR_FAIXA]]
            self._valores.append({"range": self._faixa(real, f"{c1}{k + 2}:{c2}{k + 1 + len(bloco)}"), "values": bloco})
        if info["linhas"] > ultima:
            self._limpar.append(self._faixa(real, f"{c1}{ultima + 1}:{c2}{info['linhas']}"))
        colunas_data = {c: f for c, f in (formatos or {}).items() if n and primeira_coluna <= c < n_colunas}
        da_equipe = self._formatos_atuais(real, list(colunas_data)) if colunas_data else {}
        for coluna, formato in colunas_data.items():
            # Vale o formato que a equipe já usa na coluna (ex.: "agosto/26"); o do sistema só onde não há nenhum.
            # Vai célula a célula (updateCells): o repeatCell é ignorado pelo Google em células que já têm formato de data.
            celula = {"userEnteredFormat": {"numberFormat": da_equipe.get(coluna) or _padrao_data(formato)}}
            for k in range(1, ultima, LINHAS_POR_FAIXA):
                fim = min(k + LINHAS_POR_FAIXA, ultima)
                self._formatos.append({"updateCells": {
                    "range": {"sheetId": info["id"], "startRowIndex": k, "endRowIndex": fim, "startColumnIndex": coluna, "endColumnIndex": coluna + 1},
                    "rows": [{"values": [celula]}] * (fim - k), "fields": "userEnteredFormat.numberFormat"}})
        return ultima

    def _formatos_atuais(self, aba: str, colunas: list[int], amostra: int = 500) -> dict[int, dict]:
        """Formato de número mais usado em cada coluna (nas primeiras linhas de dados); só colunas que têm algum."""
        import collections
        import json
        d = self.cliente.pedir("GET", f"{API}/{self.id}", params={
            "ranges": [self._faixa(aba, f"{letra(c + 1)}2:{letra(c + 1)}{amostra + 1}") for c in colunas], "includeGridData": "true",
            "fields": "sheets(properties(title),data(rowData(values(userEnteredFormat(numberFormat)))))"})
        folha = next((sh for sh in d.get("sheets", []) if sh.get("data")), {"data": []})
        saida = {}
        for c, bloco in zip(colunas, folha["data"]):
            cont = collections.Counter(json.dumps(v["userEnteredFormat"]["numberFormat"], sort_keys=True)
                                       for l in bloco.get("rowData", []) for v in (l.get("values") or [])[:1]
                                       if v.get("userEnteredFormat", {}).get("numberFormat", {}).get("type") in ("DATE", "DATE_TIME"))
            if cont:
                saida[c] = json.loads(cont.most_common(1)[0][0])
        return saida

    def estender_formulas(self, aba: str, primeira_coluna: int, ultima_coluna: int, ate_linha: int) -> int:
        """Copia para baixo as fórmulas das colunas (1 = A) até `ate_linha`, a partir da última linha que as tem.
        Devolve quantas linhas ganharam fórmula."""
        real = self.aba(aba)
        coluna = self.formulas(real, f"{letra(primeira_coluna)}:{letra(primeira_coluna)}")
        ultima = max((i for i, l in enumerate(coluna, 1) if l and str(l[0]).startswith("=")), default=0)
        if ultima < 2 or ultima >= ate_linha:
            return 0
        info = self.abas[real]
        self._alvos.append((real, ultima, ate_linha, primeira_coluna - 1, ultima_coluna))
        self._formatos.append({"copyPaste": {
            "source": {"sheetId": info["id"], "startRowIndex": ultima - 1, "endRowIndex": ultima,
                       "startColumnIndex": primeira_coluna - 1, "endColumnIndex": ultima_coluna},
            "destination": {"sheetId": info["id"], "startRowIndex": ultima, "endRowIndex": ate_linha,
                            "startColumnIndex": primeira_coluna - 1, "endColumnIndex": ultima_coluna},
            "pasteType": "PASTE_FORMULA"}})
        return ate_linha - ultima

    def salvar(self) -> int:
        """Envia a fila: aumenta a grade, esvazia o que sobrou, grava os valores e aplica os formatos.
        Devolve quantas células foram gravadas."""
        url = f"{API}/{self.id}"
        bloqueios = self._bloqueios()
        if bloqueios:
            self._valores, self._limpar, self._grade, self._formatos, self._alvos = [], [], [], [], []
            raise GoogleErro(
                f"nada foi gravado em {self.titulo}: há áreas protegidas que a conta {self.cliente.email} não pode editar: "
                f"{'; '.join(bloqueios)}. Na planilha, abra Dados > Proteger páginas e intervalos, clique em cada uma, "
                f"Alterar permissões > Personalizado, e adicione {self.cliente.email}.")
        if self._grade:
            self.cliente.pedir("POST", f"{url}:batchUpdate", json={"requests": self._grade})
        if self._limpar:
            self.cliente.pedir("POST", f"{url}/values:batchClear", json={"ranges": self._limpar})
        celulas = 0
        lote, linhas_lote = [], 0
        for faixa in self._valores + [None]:
            if faixa is None or (lote and linhas_lote + len(faixa["values"]) > LINHAS_POR_ENVIO):
                if lote:
                    self.cliente.pedir("POST", f"{url}/values:batchUpdate", json={"valueInputOption": "RAW", "data": lote})
                lote, linhas_lote = [], 0
            if faixa is not None:
                lote.append(faixa)
                linhas_lote += len(faixa["values"])
                celulas += sum(len(l) for l in faixa["values"])
        lote, peso = [], 0   # formatos célula a célula pesam: no máximo ~LINHAS_POR_ENVIO linhas por chamada
        for pedido in self._formatos + [None]:
            tamanho = len(pedido["updateCells"]["rows"]) if pedido and "updateCells" in pedido else 1
            if pedido is None or (lote and peso + tamanho > LINHAS_POR_ENVIO):
                if lote:
                    self.cliente.pedir("POST", f"{url}:batchUpdate", json={"requests": lote})
                lote, peso = [], 0
            if pedido is not None:
                lote.append(pedido)
                peso += tamanho
        self._valores, self._limpar, self._grade, self._formatos, self._alvos = [], [], [], [], []
        self.recarregar()
        return celulas

    def _bloqueios(self) -> list[str]:
        """Áreas protegidas (que a conta de serviço não pode editar) que cruzam o que está na fila para gravar."""
        achados = []
        for aba, l0, l1, c0, c1 in self._alvos:
            for r in self.abas[aba]["protegidas"]:
                pl0, pl1 = r.get("startRowIndex", 0), r.get("endRowIndex", 10 ** 9)
                pc0, pc1 = r.get("startColumnIndex", 0), r.get("endColumnIndex", 10 ** 6)
                if pl0 < l1 and l0 < pl1 and pc0 < c1 and c0 < pc1:
                    inteira = not any(k in r for k in ("startRowIndex", "endRowIndex", "startColumnIndex", "endColumnIndex"))
                    faixa = "aba inteira" if inteira else (f"{letra(pc0 + 1)}{pl0 + 1}:{letra(min(pc1, 18278)) if 'endColumnIndex' in r else ''}"
                                                            f"{pl1 if 'endRowIndex' in r else ''}")
                    texto = f"{aba} ({faixa})"
                    if texto not in achados:
                        achados.append(texto)
        return achados

    @property
    def link(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.id}"


def requests_quote(faixa: str) -> str:
    from urllib.parse import quote
    return quote(faixa, safe="")


GRAVANDO = "gravando"   # marca de uma gravação que não terminou


def impressao(linhas) -> str:
    """Resumo (hash) do conteúdo de uma aba, para saber depois se alguém mexeu nela."""
    import hashlib
    import json
    return hashlib.sha1(json.dumps(linhas, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


class Marcas:
    """Impressão digital do que o sistema gravou por último em cada aba do Google (dados/google.json).
    Aba diferente da impressão = a equipe colou ou editou algo nela depois da última gravação."""

    def __init__(self, pasta_dados: Path):
        self.arquivo = Path(pasta_dados) / "google.json"
        self.dados: dict[str, dict[str, str]] = {}

    def carregar(self) -> None:
        import json
        if self.arquivo.exists():
            self.dados = json.loads(self.arquivo.read_text(encoding="utf-8"))

    def salvar(self) -> None:
        import json
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.arquivo)

    def obter(self, planilha_id: str, aba: str) -> str:
        return self.dados.get(planilha_id, {}).get(aba, "")

    def definir(self, planilha_id: str, aba: str, valor: str) -> None:
        self.dados.setdefault(planilha_id, {})[aba] = valor
        self.salvar()


class ContaGoogle:
    """As planilhas do Google configuradas, abertas uma vez por execução."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._cliente: Cliente | None = None
        self._abertas: dict[str, PlanilhaGoogle] = {}

    @property
    def cliente(self) -> Cliente:
        if self._cliente is None:
            self._cliente = Cliente(self.cfg.google_credenciais)
        return self._cliente

    def planilha(self, ident: str) -> PlanilhaGoogle:
        chave = id_da_planilha(ident)
        if chave not in self._abertas:
            self._abertas[chave] = PlanilhaGoogle(self.cliente, chave)
        return self._abertas[chave]
