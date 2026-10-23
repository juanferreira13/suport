import datetime as dt
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from core import GoogleSheets,SheetsError,sheet_id
import api.index as api

class FakeGoogle(GoogleSheets):
    def __init__(self):
        self.writes=[];self.expansion=[];self.meta={}
        self.existing=[]
        self.prior={}
    def ensure_tab(self,name,n):return {'title':name}
    def values(self,r):
        if r=="'SGA'!A1:AB1":return [['PROTOCOLO','TIPO EVENTO','MOTIVO EVENTO','NOME ASSOCIADO','PLACA','ASSOCIADO CIDADE']]
        if r=="'SGA'!A2:I":return self.existing
        if r.startswith("'SGA'!A") and ':AB' in r:return self.prior.get(r,[])
        return []
    def ensure_rows(self,name,row):self.expansion.append(row)
    def batch_values(self,data):self.writes+=data

class Tests(unittest.TestCase):
    def test_id(self):
        u='https://docs.google.com/spreadsheets/d/'+'a'*36+'/edit'
        self.assertEqual(sheet_id(u),'a'*36)
    def test_dates(self):
        self.assertEqual(api.dates('2020-01-01','2020-01-01')[0],dt.date(2020,1,1))
        with self.assertRaises(ValueError):api.dates('2019-12-31','2020-01-01')
        with self.assertRaises(ValueError):api.dates('2020-01-01','2020-02-01')
    def test_write_preserves_column_ac_and_updates_known(self):
        fake=FakeGoogle()
        fake.existing=[['202622219','ASSOCIADO','VIDROS','Fulano','AAA1234','BRASILIA','','','']]
        fake.prior={"'SGA'!A2:AB2":[['202622219','ASSOCIADO','VIDROS','Fulano','AAA1234','BRASILIA']+['']*12+['DOC. PENDENTE']]}
        event={'protocolo':'202622219','evento_tipo':'ASSOCIADO','motivo':'VIDROS','associado':{'nome':'Outro nome','cidade':'BRASILIA'},'veiculo':{'placa':'AAA1234'},'situacao_evento':'AUTORIZADO'}
        result=fake.upsert_sga([event])
        self.assertEqual(result['atualizados'],1)
        self.assertEqual(result['novos'],0)
        self.assertTrue(any(w['range']=="'SGA'!S2:S2" and w['values'][0][0]=='AUTORIZADO' for w in fake.writes))
        self.assertFalse(any(w['range']=="'SGA'!D2:D2" for w in fake.writes))
        self.assertFalse(any(':AC' in x['range'] for x in fake.writes))
    def test_new_event_starts_line_two(self):
        fake=FakeGoogle()
        event={'protocolo':'202622219','evento_tipo':'ASSOCIADO','motivo':'VIDROS','associado':{'nome':'Fulano'},'veiculo':{'placa':'AAA1234'}}
        result=fake.upsert_sga([event])
        self.assertEqual(result['novos'],1)
        self.assertEqual(fake.writes[0]['range'],"'SGA'!A2:AB2")

if __name__=='__main__': unittest.main()
