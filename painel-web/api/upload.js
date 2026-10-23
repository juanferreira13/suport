// POST /api/upload?painel=finalizados|acompanhamento
// Recebe o HTML de um painel gerado pela ferramenta local e o guarda.
// Autenticacao: header "Authorization: Bearer <UPLOAD_SECRET>".
// Corpo (application/json): { "html_base64": "<html em base64 utf-8>" }
import { PAINEIS, salvarPainel, uploadAutorizado } from '../lib/util.js';
import { extrairHtml } from '../lib/corpo.js';

function responder(res, status, obj) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(obj));
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return responder(res, 405, { erro: 'Use POST.' });
  if (!uploadAutorizado(req)) return responder(res, 401, { erro: 'Segredo de envio invalido ou ausente.' });

  const nome = (req.query?.painel || '').toString();
  if (!PAINEIS[nome]) {
    return responder(res, 400, { erro: `painel invalido. Use: ${Object.keys(PAINEIS).join(', ')}.` });
  }

  // Extrai o HTML: aceita { html_base64 }, { html } ou o HTML direto no corpo.
  let html;
  try {
    html = await extrairHtml(req);
  } catch (e) {
    return responder(res, 400, { erro: 'Nao consegui ler o corpo do pedido.', detalhe: String(e) });
  }

  if (!html || typeof html !== 'string' || html.length < 100) {
    return responder(res, 400, { erro: 'HTML ausente ou muito pequeno.' });
  }
  if (!/<html[\s>]/i.test(html)) {
    return responder(res, 400, { erro: 'O conteudo enviado nao parece um documento HTML.' });
  }

  try {
    await salvarPainel(nome, html);
  } catch (e) {
    return responder(res, 500, { erro: 'Falha ao guardar o painel.', detalhe: String(e) });
  }

  return responder(res, 200, { ok: true, painel: nome, tamanho: html.length });
}
