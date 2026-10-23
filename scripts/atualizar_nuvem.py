"""Executa passos da API Vercel com checkpoint persistido na planilha (GitHub Actions)."""
import json, os, sys, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE=os.environ.get('INTEGRADOR_URL','https://grupo-suport.vercel.app').rstrip('/')
KEY=os.environ.get('INTEGRADOR_API_KEY','')
MAX_STEPS=int(os.environ.get('MAX_STEPS','100'))
if not KEY:sys.exit('Configure INTEGRADOR_API_KEY nos GitHub Actions Secrets.')

def post(path,obj):
    req=Request(BASE+path,method='POST',data=json.dumps(obj).encode(),headers={
        'X-API-Key':KEY, 'Content-Type':'application/json','Accept':'application/json'})
    with urlopen(req,timeout=65) as r:
        return json.loads(r.read().decode())

# Executa 100 lotes por rodada; se histórico estiver completo, reprocessa os últimos dias.
days=1
for step in range(MAX_STEPS):
    try:
        d=post('/api/sync/sga/etapa',{'dias':days})
    except HTTPError as e:
        if days>1:
            print('Janela longa falhou; tentando um dia:',e.code,flush=True);days=1;continue
        sys.exit('Etapa interrompida (HTTP %s). Cheque as variáveis e logs da Vercel; checkpoint preservado.'%e.code)
    except (URLError,TimeoutError) as e:
        if days>1:days=1;continue
        sys.exit('Timeout no lote diário; checkpoint preservado.')
    if d.get('concluido') and not d.get('inicio'):
        print('Histórico concluído. Reprocessando eventos recentes.',flush=True)
        r=post('/api/sync/sga/recentes',{'dias':1})
        print('Atualização diária:',r.get('eventos'), 'eventos.',flush=True)
        break
    print(step+1,d.get('inicio'),d.get('fim'), 'eventos:',d.get('eventos_consultados'),'gravados:',d.get('gravacao'),flush=True)
    if d.get('concluido'):
        print('Histórico finalizado.',flush=True)
        break
    if days==1 and d.get('eventos_consultados',0)<30:days=7
    elif d.get('eventos_consultados',0)>=95:days=1
    time.sleep(.3)
else:
    print('Limite de lotes por rodada atingido. Próxima execução continuará do checkpoint.',flush=True)
