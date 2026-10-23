"""API serverless Grupo Support. Sem sessão global ou dados sensíveis em logs."""
from __future__ import annotations
import datetime as dt
import hmac
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from core import ConfigError, SheetsError, GoogleSheets, sheet_public_url

SGA_BASE='https://api.hinova.com.br/api/sga/v2'
SIGA_ENDPOINT='https://siga.arcoconsultoria.com/SIGA/wsTotalEventosCadastrado.rule?sys=SIG'


def http_json(url,payload,headers,timeout=18):
    data=json.dumps(payload).encode('utf-8') if payload is not None else None
    req=urllib.request.Request(url,data=data,method='POST' if payload is not None else 'GET',headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            raw=response.read(8_000_000)
            return response.status, json.loads(raw.decode('utf-8')) if raw else {}
    except urllib.error.HTTPError as ex:
        return ex.code, {'erro':f'Origem respondeu HTTP {ex.code}'}


def auth_sga():
    for field in ['SGA_TOKEN','SGA_USUARIO','SGA_SENHA']:
        if not os.getenv(field):raise ConfigError('Credenciais SGA incompletas na Vercel.')
    base=os.getenv('SGA_API_URL',SGA_BASE).rstrip('/')
    if not base.startswith('https://api.hinova.com.br/'):
        raise ConfigError('URL do SGA não é da Hinova.')
    status,data=http_json(base+'/usuario/autenticar',{'usuario':os.environ['SGA_USUARIO'],'senha':os.environ['SGA_SENHA']},
       {'Authorization':'Bearer '+os.environ['SGA_TOKEN'],'Content-Type':'application/json'})
    token=data.get('token_usuario') if isinstance(data,dict) else None
    if status!=200 or not token:raise RuntimeError(f'Autenticação Hinova falhou (HTTP {status}).')
    return base,{'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json'}


def dates(from_str,to_str,cap=30):
    try:
        start,end=dt.date.fromisoformat(from_str),dt.date.fromisoformat(to_str)
    except (ValueError,TypeError):raise ValueError('Datas devem estar no formato AAAA-MM-DD.')
    if start<dt.date(2020,1,1) or start>end or (end-start).days>=cap or end>dt.date.today()+dt.timedelta(days=1):
        raise ValueError('Intervalo inválido (máximo de 30 dias a partir de 2020).')
    return start,end


def sga_page(base,headers,begin,end,offset=0,limit=100):
    # Usar exatamente os campos de paginação do cliente original do executável.
    body={'data_cadastro':begin.strftime('%d/%m/%Y'),'data_cadastro_final':end.strftime('%d/%m/%Y'),
          'inicio_paginacao':offset,'quantidade_por_pagina':limit}
    status,answer=http_json(base+'/listar/evento',body,headers)
    if status==204:return []
    if status!=200:raise RuntimeError(f'Hinova retornou HTTP {status} na consulta de eventos.')
    if isinstance(answer,dict):
        items=next((v for v in answer.values() if isinstance(v,list)),None)
        if items is not None:return items
        text=str(answer.get('mensagem') or answer.get('message') or answer.get('descricao') or '').lower()
        if answer.get('recordTotal') == 0 or any(phrase in text for phrase in ('nenhum evento','nenhum registro','não foram encontrados','nao foram encontrados')):
            return []
        raise RuntimeError('Formato inesperado da listagem SGA (resposta sem lista nem indicação de vazio).')
    if not isinstance(answer,list):raise RuntimeError('A Hinova não retornou uma lista de eventos; operação interrompida.')
    return answer


def siga_query(ano,mes,empresa,offset,limite):
    cookie=os.getenv('SIGA_SESSION_COOKIE','').strip()
    if not cookie:raise ConfigError('Cookie de sessão SIGA ausente ou expirado.')
    if not (2021<=ano<=dt.date.today().year and 1<=mes<=12 and re.fullmatch(r'\d{1,12}',empresa) and 0<=offset<=100000 and 1<=limite<=250):
        raise ValueError('Parâmetros SIGA inválidos.')
    payload={'emp_id':empresa,'ano':str(ano),'mes':str(mes),'relatorio':'relatorio','offset':offset,'limit':limite}
    status,data=http_json(SIGA_ENDPOINT,payload,{'Cookie':cookie,'Accept':'application/json','Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
    if status!=200 or not isinstance(data,dict) or not isinstance(data.get('tarefas'),list):
        raise RuntimeError('SIGA não retornou tarefas válidas. Verifique sessão e filtros.')
    return data


def collect_sga_range(start,end):
    base,headers=auth_sga()
    all_items=[]; codes=set(); offset=0; previous=None
    for page_no in range(10):
        events=sga_page(base,headers,start,end,offset,100)
        fingerprint=tuple(str(item.get('codigo','')) for item in events if isinstance(item,dict))
        if fingerprint and fingerprint==previous:
            raise RuntimeError('A paginação Hinova repetiu uma página; operação não será marcada como concluída.')
        previous=fingerprint
        for item in events:
            if isinstance(item,dict):
                code=str(item.get('codigo') or item.get('protocolo') or len(codes))
                if code not in codes:codes.add(code);all_items.append(item)
        if len(events)<100:break
        offset+=1
    else:
        raise RuntimeError('Muitas páginas para o intervalo; diminua dias ou execute o robô externo.')
    return all_items


def sync_one_step(days=1):
    if not (1<=days<=7):raise ValueError('dias deve ser de 1 a 7.')
    sheet=GoogleSheets()
    checkpoint=sheet.checkpoint()
    start=dt.date.fromisoformat(checkpoint)+dt.timedelta(days=1) if checkpoint else dt.date(2020,1,1)
    end=min(start+dt.timedelta(days=days-1),dt.date.today())
    if start>end:return {'ok':True,'concluido':True,'ate':dt.date.today().isoformat()}
    all_items=collect_sga_range(start,end)
    write=sheet.upsert_sga(all_items)
    sheet.save_checkpoint(end,len(all_items))
    return {'ok':True,'concluido':end>=dt.date.today(),'inicio':start.isoformat(),'fim':end.isoformat(),
        'eventos_consultados':len(all_items), 'gravacao':write,'proximo_inicio':(end+dt.timedelta(days=1)).isoformat(),
        'planilha':sheet_public_url()}


class handler(BaseHTTPRequestHandler):
    def send(self,code,body):
        content=json.dumps(body,ensure_ascii=False,default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Access-Control-Allow-Origin','none')
        self.send_header('Content-Length',str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def is_auth(self):
        secret=os.getenv('INTEGRADOR_API_KEY','')
        candidate=self.headers.get('X-API-Key','')
        return bool(secret) and hmac.compare_digest(secret,candidate)

    def action(self,method):
        path=urlsplit(self.path).path.rstrip('/')
        args=parse_qs(urlsplit(self.path).query)
        if path in ('/api','/api/health') and method=='GET':
            return self.send(200,{'ok':True,'servico':'Integrador SIGA x SGA','sga_configurado':all(os.getenv(k) for k in ('SGA_TOKEN','SGA_USUARIO','SGA_SENHA')),
              'siga_sessao_configurada':bool(os.getenv('SIGA_SESSION_COOKIE')), 'sheets_configurado':bool(os.getenv('GOOGLE_SINISTRO') and os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')),
              'modo_robo':'passos serverless; extração SIGA integral externa'})
        if not self.is_auth():return self.send(401,{'erro':'Chave de API inválida ou ausente.'})
        def arg(name,default=None):return args.get(name,[default])[0]
        try:
            if method=='GET' and path=='/api/config':
                return self.send(200,{'sheet_url':sheet_public_url(),'sheets_configurado':bool(os.getenv('GOOGLE_SINISTRO') and os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')),
                    'sga_inicio':'2020-01-01','siga_inicio':'2021-01-01','siga_consulta_aviso':'O SIGA retornou zero nas consultas anteriores; não tratamos isso como histórico vazio.'})
            if method=='GET' and path=='/api/sga/testar':
                auth_sga();return self.send(200,{'ok':True,'origem':'SGA','autenticado':True})
            if method=='GET' and path=='/api/sga/eventos':
                a,b=dates(arg('inicio'),arg('fim'));page=int(arg('pagina','1'));limit=int(arg('limite','100'))
                if not (1<=page<=100 and 1<=limit<=100):raise ValueError('pagina e limite inválidos.')
                base,headers=auth_sga()
                data=sga_page(base,headers,a,b,page-1,limit)
                return self.send(200,{'origem':'SGA','periodo':{'inicio':str(a),'fim':str(b)},'pagina':page,'resultado':data})
            if method=='GET' and path=='/api/siga/eventos':
                ano=int(arg('ano',dt.date.today().year));mes=int(arg('mes',dt.date.today().month));empresa=arg('empresa','141')
                offset=int(arg('offset','0'));limite=int(arg('limite','100'))
                data=siga_query(ano,mes,empresa,offset,limite)
                return self.send(200,{'origem':'SIGA','ano':ano,'mes':mes,'offset':offset,'resultado':data})
            if method=='GET' and path=='/api/sync/status':
                sheet=GoogleSheets();meta=sheet.metadata();checkpoint=sheet.checkpoint()
                return self.send(200,{'ok':True,'planilha':meta['properties']['title'],'sheet_url':sheet_public_url(),
                    'email_conta_servico':sheet.email,'ultimo_dia_processado':checkpoint,'primeiro_dia':'2020-01-01'})
            if method=='POST' and path=='/api/sync/sga/recentes':
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>4096:raise ValueError('Corpo da requisição muito grande.')
                data=json.loads(self.rfile.read(length) or b'{}')
                days=int(data.get('dias',1));
                if not (1<=days<=7):raise ValueError('dias deve ser de 1 a 7.')
                end=dt.date.today();start=end-dt.timedelta(days=days-1)
                items=collect_sga_range(start,end);sheet=GoogleSheets();saved=sheet.upsert_sga(items)
                return self.send(200,{'ok':True,'inicio':str(start),'fim':str(end),'eventos':len(items),'gravacao':saved})
            if method=='POST' and path=='/api/sync/sga/etapa':
                length=int(self.headers.get('Content-Length','0'))
                if length<0 or length>4096:raise ValueError('Corpo da requisição muito grande.')
                data=json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(data,dict):raise ValueError('Informe objeto JSON.')
                return self.send(200,sync_one_step(int(data.get('dias',1))))
            return self.send(404,{'erro':'Rota não encontrada.'})
        except (ConfigError,ValueError,TypeError,json.JSONDecodeError) as ex:
            return self.send(400,{'erro':str(ex)})
        except SheetsError as ex:
            return self.send(502,{'erro':str(ex)})
        except (TimeoutError,urllib.error.URLError):
            return self.send(504,{'erro':'Tempo excedido ou falha de conexão ao sistema de origem.'})
        except RuntimeError as ex:
            return self.send(502,{'erro':str(ex)})
        except Exception:
            return self.send(502,{'erro':'Falha na operação. Consulte os logs da Vercel sem expor credenciais.'})

    def do_GET(self):return self.action('GET')
    def do_POST(self):return self.action('POST')
