"""Funções reutilizáveis da versão web. Nunca usa disco do servidor para guardar dados."""
from __future__ import annotations
import datetime as dt
import json
import os
import re
from urllib.parse import quote

from sinistro.sga_api import normalizar_evento, completar_por_protocolo
from sinistro import sga_base as S

GSCOPE = ['https://www.googleapis.com/auth/spreadsheets']
GSAPI = 'https://sheets.googleapis.com/v4/spreadsheets'
CABECALHO_SGA = [name for name, _ in S.COLUNAS]
TAB_CONTROLE = '_SUPPORT_SYNC'


class ConfigError(Exception):
    pass


class SheetsError(Exception):
    pass


def column_name(index: int) -> str:
    result=''
    while index:
        index, digit=divmod(index-1,26)
        result=chr(65+digit)+result
    return result


def sheet_id(value: str):
    match = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]{20,})', value or '')
    raw = match.group(1) if match else (value or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,}', raw):
        raise ConfigError('Configure GOOGLE_SINISTRO com o link ou ID da planilha.')
    return raw


def sheet_public_url():
    value = os.getenv('GOOGLE_SINISTRO', '').strip()
    if not value: return ''
    try: return f'https://docs.google.com/spreadsheets/d/{sheet_id(value)}/edit'
    except ConfigError: return ''


class GoogleSheets:
    def __init__(self):
        import google.auth.transport.requests
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        value = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()
        if not value:
            raise ConfigError('Configure GOOGLE_SERVICE_ACCOUNT_JSON na Vercel (JSON da conta de serviço).')
        try:
            info = json.loads(value)
            creds = service_account.Credentials.from_service_account_info(info, scopes=GSCOPE)
        except Exception as exc:
            raise ConfigError('GOOGLE_SERVICE_ACCOUNT_JSON inválido. Insira o JSON inteiro em uma linha ou múltiplas linhas.') from exc
        self.email = creds.service_account_email
        self.session = AuthorizedSession(creds)
        self.id = sheet_id(os.getenv('GOOGLE_SINISTRO',''))
        self.url = f'{GSAPI}/{self.id}'

    def req(self, method: str, path: str = '', **kwargs):
        try:
            response = self.session.request(method, self.url + path, timeout=18, **kwargs)
        except Exception as exc:
            raise SheetsError('Não foi possível conectar ao Google Sheets.') from exc
        if response.status_code >= 400:
            try: problem = response.json().get('error', {}).get('message', '')
            except Exception: problem = ''
            if response.status_code == 403:
                raise SheetsError('Permissão negada pelo Google: compartilhe a planilha como Editor com a conta de serviço.')
            if response.status_code == 404:
                raise SheetsError('Planilha Google não encontrada; confira GOOGLE_SINISTRO e o acesso da conta de serviço.')
            raise SheetsError(f'Google Sheets HTTP {response.status_code}: {problem[:120]}')
        try: return response.json()
        except ValueError: return {}

    def metadata(self):
        return self.req('GET', params={'fields':'properties(title),sheets(properties(title,sheetId,gridProperties(rowCount,columnCount)))'})

    def values(self, range_name: str):
        p='/values/'+quote(range_name,safe='')
        return self.req('GET',p,params={'valueRenderOption':'FORMATTED_VALUE'}).get('values',[])

    def batch_values(self, data):
        if data:
            self.req('POST','/values:batchUpdate',json={'valueInputOption':'RAW','data':data})

    def ensure_tab(self,title,columns):
        metadata=self.metadata()
        tabs={sh['properties']['title']:sh['properties'] for sh in metadata['sheets']}
        if title not in tabs:
            self.req('POST', ':batchUpdate', json={'requests':[{'addSheet':{'properties':{'title':title,'gridProperties':{'rowCount':2000,'columnCount':max(40,columns)}}}}]})
            metadata=self.metadata();tabs={sh['properties']['title']:sh['properties'] for sh in metadata['sheets']}
        return tabs[title]

    def ensure_rows(self,title,required_rows):
        meta=self.metadata()
        sh=next((s['properties'] for s in meta['sheets'] if s['properties']['title']==title),None)
        if not sh: raise SheetsError(f'Aba {title} não encontrada')
        current=sh['gridProperties'].get('rowCount',1000)
        if required_rows > current:
            self.req('POST',':batchUpdate',json={'requests':[{'appendDimension':{'sheetId':sh['sheetId'],'dimension':'ROWS','length':required_rows-current+100}}]})

    def checkpoint(self):
        names={x['properties']['title'] for x in self.metadata()['sheets']}
        if TAB_CONTROLE not in names:return None
        rows=self.values(f"'{TAB_CONTROLE}'!A1:D2")
        if len(rows)>=2 and len(rows[1])>=2 and rows[1][0]=='SGA':
            return rows[1][1]
        return None

    def save_checkpoint(self,last_processed:dt.date,added:int):
        self.ensure_tab(TAB_CONTROLE,4)
        self.batch_values([{'range':f"'{TAB_CONTROLE}'!A1:D2",'values':[
            ['ORIGEM','ULTIMO_DIA_PROCESSADO','ULTIMO_LOTE','ATUALIZADO_EM'],
            ['SGA',last_processed.isoformat(),added,dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')]
        ]}])

    @staticmethod
    def _key(row):
        row=(list(row)+['']*9)[:9]
        proto=str(row[S.PROTOCOLO]).strip()
        tipo=str(row[S.TIPO]).strip().upper()
        placa=str(row[S.PLACA_TERCEIRO] or row[S.PLACA]).strip().upper().replace('-','')
        return (proto,tipo,placa) if proto else None

    def upsert_sga(self, items:list[dict]):
        """Altera apenas A:AB; preserva AÇÕES (AC), fórmulas e outras abas.
        Recusa cabeçalho desconhecido para não corromper planilha da equipe.
        """
        self.ensure_tab('SGA',34)
        headings=self.values("'SGA'!A1:AB1")
        if not headings or not headings[0]:
            self.batch_values([{'range':"'SGA'!A1:AC1",'values':[CABECALHO_SGA]}])
        else:
            actual=[str(s).strip().upper() for s in headings[0]][:6]
            target=[s.strip().upper() for s in CABECALHO_SGA][:6]
            if actual!=target:
                raise SheetsError('A aba SGA não corresponde ao layout original. Escrita bloqueada para não sobrescrever dados.')
        existing=self.values("'SGA'!A2:I")
        row_of={}
        for n,row in enumerate(existing,2):
            key=self._key(row)
            if key and key not in row_of:row_of[key]=n
        highest=len(existing)+1
        normalized=completar_por_protocolo([normalizar_evento(item,{}) for item in items if isinstance(item,dict)])
        if not normalized:return {'novos':0,'atualizados':0,'ignorados':0}
        updates=[]; inserted=modified=ignored=0
        known_rows={}
        for row in normalized:
            key=self._key(row)
            if not key: ignored+=1;continue
            if key in known_rows: ignored+=1;continue
            known_rows[key]=row
        for key,row in known_rows.items():
            if key in row_of:
                number=row_of[key]
                # A lógica antiga evita substituir dados de identidade na planilha original.
                # Leitura da linha completa somente para os poucos registros atualizados.
                prior=self.values(f"'SGA'!A{number}:AB{number}")
                previous=(prior[0] if prior else [])+['']*S.N_COLUNAS
                row_changed=False
                for col in S.CAMPOS_API:
                    if col in S.CAMPOS_IDENTIDADE or col>=28 or not row[col]:
                        continue
                    # Não regravar a linha inteira: isso converteria datas e fórmulas já existentes em texto.
                    if str(row[col]).strip()!=str(previous[col]).strip():
                        letter=column_name(col+1)
                        updates.append({'range':f"'SGA'!{letter}{number}:{letter}{number}",'values':[[row[col]]]})
                        row_changed=True
                if row_changed:modified+=1
            else:
                highest+=1
                row_of[key]=highest
                updates.append({'range':f"'SGA'!A{highest}:AB{highest}",'values':[row[:28]]})
                inserted+=1
        self.ensure_rows('SGA',highest)
        # Google limits per request; split to avoid multi-MB batches.
        for offset in range(0,len(updates),100):self.batch_values(updates[offset:offset+100])
        return {'novos':inserted,'atualizados':modified,'ignorados':ignored}
