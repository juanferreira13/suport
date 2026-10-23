/* Interface derivada do atualizar_tela.py enviado: somente lógica local foi trocada. */
'use strict';
const $ = id => document.getElementById(id);
let key = sessionStorage.getItem('support_api_key') || '';
let stop = false, running = false, sheetUrl = '', rows = 0;
let logs = [];
$('favicon').href='/favicon.ico';
$('senha').value=key;
$('lembrar').checked=!!key;
$('destino').textContent='Verificando a planilha configurada na Vercel…';
$('destino').title='A Vercel salva diretamente no Google Sheets, não no disco do computador.';
$('cancelar').textContent='Parar atualização';
$('status').textContent='Pronto para conectar';
$('previa').hidden=true;
$('arcos-status').style.visibility='hidden';
$('visor-vazio').hidden=false;
$('visor-vazio').textContent='Estes HTMLs são os modelos originais; os resultados atualizados ficam no Google Sheets.';
$('visor').hidden=true;
$('selo-novo').hidden=true;
const PANEL=[{title:'Conferência de finalizados',href:'/conferencia.html'}, {title:'Acompanhamento dos analistas',href:'/acompanhamento.html'}];
let panelUrl=PANEL[0].href;
$('seletor-paineis').replaceChildren();
PANEL.forEach((p,i)=>{
  const btn=document.createElement('button');btn.type='button';btn.textContent=p.title;
  btn.className='btn-verde';btn.style.marginRight='8px';
  btn.onclick=()=>{panelUrl=p.href;$('painel-atualizado').textContent='Prévia do modelo sem dados do robô Windows.';
    $('visor').hidden=false;$('visor-vazio').hidden=true;$('visor').src=p.href;};
  $('seletor-paineis').appendChild(btn);
});
$('abrir-painel').onclick=()=>window.open(panelUrl,'_blank','noopener,noreferrer');
$('painel-atualizado').textContent='Modelos estáticos da instalação Windows.';
$('ver-resultados').hidden=true;
$('resultados').hidden=true;
$('escolher').onclick=()=>{if(sheetUrl)window.open(sheetUrl,'_blank','noopener,noreferrer');else notice('Configure GOOGLE_SINISTRO na Vercel para abrir a planilha.',true);};
$('resultados').onclick=()=>{if(sheetUrl)window.open(sheetUrl,'_blank','noopener,noreferrer');};

function notice(text,error=false){
  $('msg').textContent=text;$('msg').className=error?'msg erro-visivel':'msg ok-visivel';
}
function trace(text){
  logs.push(new Date().toLocaleTimeString('pt-BR')+' · '+text); if(logs.length>250)logs.shift();
  $('log').textContent=logs.join('\n');
  const li=document.createElement('li');li.textContent=text;li.style.margin='5px 0';
  $('etapas').appendChild(li);$('sem-etapas').hidden=true;
}
function progress(percent,text,detail=''){
  $('pct').textContent=Math.round(percent)+'%';$('barra').style.width=Math.max(0,Math.min(100,percent))+'%';
  $('status').textContent=text;$('detalhe').textContent=detail;
}
async function request(path,{method='GET',body=null}={}){
  const supplied=$('senha').value.trim();
  if(supplied)key=supplied;
  if(!key)throw new Error('Digite sua chave de API no campo acima.');
  const controller=new AbortController();const abort=setTimeout(()=>controller.abort(),58000);
  try{
    const res=await fetch(path,{method,headers:{'X-API-Key':key,...(body?{'Content-Type':'application/json'}:{})},
      ...(body?{body:JSON.stringify(body)}:{}), signal:controller.signal,cache:'no-store',credentials:'omit'});
    let response;try{response=await res.json();}catch{throw new Error('Servidor respondeu sem JSON válido.');}
    if(!res.ok)throw new Error(response.erro||'Erro HTTP '+res.status);
    return response;
  }catch(e){if(e.name==='AbortError')throw new Error('Tempo excedido na API; nenhuma etapa incompleta será marcada como concluída.');throw e;}
  finally{clearTimeout(abort);}
}
function setSheet(url,title){
  sheetUrl=url||'';
  $('destino').textContent=sheetUrl?`Google Sheets · ${title||'Gerencial Sinistro'}`:'Google Sheets não configurado';
  $('destino').title=sheetUrl||'Configure GOOGLE_SINISTRO na Vercel';
  $('planilhas').replaceChildren();
  if(sheetUrl){const a=document.createElement('a');a.href=sheetUrl;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Abrir Gerencial Sinistro no Google Sheets ↗';$('planilhas').appendChild(a);}
}
function showTab(name){
  const results=name==='resultados';
  $('form').hidden=results;$('aba-resultados').hidden=!results;
  document.querySelectorAll('button[data-aba]').forEach(btn=>{
     const active=btn.dataset.aba===name;btn.classList.toggle('ativa',active);btn.setAttribute('aria-selected',active?'true':'false');
  });
}
document.querySelectorAll('button[data-aba]').forEach(btn=>btn.onclick=()=>showTab(btn.dataset.aba));
$('ver-resultados').onclick=()=>showTab('resultados');
$('lembrar').onchange=()=>{
  if($('lembrar').checked&&key)sessionStorage.setItem('support_api_key',key);
  else sessionStorage.removeItem('support_api_key');
};
async function connect(){
  const a=await request('/api/sga/testar');
  if(!a.autenticado)throw new Error('Autenticação Hinova não confirmada.');
  trace('SGA Hinova: autenticação confirmada.');
  const cfg=await request('/api/config');
  setSheet(cfg.sheet_url);
  if(!cfg.sheets_configurado)throw new Error('Faltam GOOGLE_SINISTRO e GOOGLE_SERVICE_ACCOUNT_JSON na Vercel.');
  const status=await request('/api/sync/status');
  trace('Google Sheets: acesso confirmado à planilha '+status.planilha+'.');
  if(status.ultimo_dia_processado)trace('Último dia consolidado: '+status.ultimo_dia_processado+'.');
  else trace('Iniciando histórico SGA em 01/01/2020.');
  trace('Histórico SIGA previsto desde 2021; a consulta atual retorna zero e ainda exige correção do extrator para importação completa.');
  notice('Conexões SGA e Google validadas. Atualização histórica iniciada.');
}
function enable(locked){
  running=locked;
  $('conectar').disabled=locked;
  $('conectar').textContent=locked?'Atualizando…':'Conectar e atualizar';
  $('cancelar').hidden=!locked;
  $('escolher').disabled=locked;
}
$('cancelar').onclick=()=>{stop=true;notice('Parada solicitada. A etapa em andamento será concluída antes da interrupção.');};
$('form').onsubmit=async e=>{
  e.preventDefault();if(running)return;
  logs=[];$('etapas').replaceChildren();$('log').textContent='';$('sem-etapas').hidden=false;rows=0;
  key=$('senha').value.trim();if(!key){notice('Informe a chave do integrador.',true);return;}
  if($('lembrar').checked)sessionStorage.setItem('support_api_key',key);
  else sessionStorage.removeItem('support_api_key');
  stop=false; enable(true);
  try{
    progress(0,'Validando conexões…');await connect();
    let days=1, fail7=0;
    while(!stop){
      let step;
      try{step=await request('/api/sync/sga/etapa',{method:'POST',body:{dias:days}});}
      catch(err){
        if(days>1){trace('Consulta de '+days+' dias falhou; reduzindo para 1 dia: '+err.message);days=1;fail7++;continue;}
        throw err;
      }
      if(step.concluido && !step.inicio){progress(100,'Histórico SGA concluído','Até a data atual.');break;}
      const written=step.gravacao||{};rows+=(written.novos||0)+(written.atualizados||0);
      const first=new Date('2020-01-01T00:00:00Z').getTime(), now=Date.now();
      const end=new Date(step.fim+'T00:00:00Z').getTime();
      const pct=100*(end-first)/Math.max(1,now-first);
      progress(pct,'Alimentando sinistros no Google Sheets',step.inicio+' a '+step.fim+' — '+step.eventos_consultados+' eventos; '+(written.novos||0)+' novos, '+(written.atualizados||0)+' atualizados.');
      trace(step.inicio+' → '+step.fim+': '+step.eventos_consultados+' eventos; '+(written.novos||0)+' adicionados, '+(written.atualizados||0)+' atualizados.');
      if(step.concluido){progress(100,'Histórico SGA concluído','Sinistros enviados ao Google Sheets. SIGA aguarda validação da consulta original.');break;}
      if(days===1&&step.eventos_consultados<30&&fail7===0)days=7;
      if(step.eventos_consultados>=95)days=1;
      await new Promise(resolve=>setTimeout(resolve,160));
    }
    if(stop){trace('Atualização interrompida pelo usuário. O cursor salvo permite continuar de onde parou.');progress(Number.parseInt($('pct').textContent)||0,'Atualização pausada.');}
    else {trace('Sinistros processados nesta sessão: '+rows+' registros (novos + atualizados).');notice('Atualização SGA finalizada. Consulte o Google Sheets para conferir os registros.');}
    $('resultados').hidden=!sheetUrl;$('ver-resultados').hidden=false;
  }catch(error){
    progress(Number.parseInt($('pct').textContent)||0,'Falha na atualização.');
    trace('ERRO: '+error.message);notice(error.message,true);
  }finally{enable(false);}
};
// A página pública não recebe a chave automaticamente; o operador fornece a chave somente em memória.
fetch('/api/health',{cache:'no-store'}).then(r=>r.json()).then(v=>{
  if(v.sheets_configurado){$('destino').textContent='Google Sheets configurado (validar acesso ao conectar)';}
  else{$('destino').textContent='Configure GOOGLE_SINISTRO e GOOGLE_SERVICE_ACCOUNT_JSON na Vercel';}
}).catch(()=>{$('destino').textContent='Sem resposta da API';});

$('siga-testar').onclick=async()=>{
  const a=Number($('siga-ano').value),m=Number($('siga-mes').value),e=$('siga-empresa').value.trim();
  const field=$('siga-resposta');field.textContent='Consultando sessão SIGA…';
  if(a<2021||a>new Date().getFullYear()||m<1||m>12||!/^\d{1,12}$/.test(e)){
    field.textContent='Confira ano, mês e empresa.';return;
  }
  try{
    const r=await request(`/api/siga/eventos?ano=${a}&mes=${m}&empresa=${e}&limite=10`);
    const total=Number(r.resultado?.recordTotal||0);
    field.textContent=total>0?`SIGA respondeu com ${total} registro(s) para ${m}/${a}. Integração SIGA completa ainda depende da validação do robô de origem.`:
      `SIGA retornou zero para ${m}/${a}. Verifique emp_id e contexto do Dashboard; isso não prova ausência de eventos.`;
  }catch(err){field.textContent='Erro na consulta SIGA: '+err.message;}
};
