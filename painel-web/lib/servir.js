// Entrega um painel guardado (HTML) ja protegido por login.
import { PAINEIS, lerPainel, exigirLogin, paginaAviso, dataBr } from './util.js';

export default async function servirPainel(req, res, nome) {
  if (!exigirLogin(req, res)) return; // ja respondeu 401/503
  const alvo = PAINEIS[nome];
  let dado = null;
  try {
    dado = await lerPainel(nome);
  } catch (e) {
    res.statusCode = 500;
    res.setHeader('content-type', 'text/html; charset=utf-8');
    res.end(paginaAviso('Erro ao abrir o painel', String(e)));
    return;
  }
  if (!dado) {
    res.statusCode = 200;
    res.setHeader('content-type', 'text/html; charset=utf-8');
    res.end(paginaAviso(
      alvo.titulo,
      'Nenhuma atualização foi enviada ainda. Rode a atualização na ferramenta e envie os painéis para o site.'
    ));
    return;
  }
  res.statusCode = 200;
  res.setHeader('content-type', 'text/html; charset=utf-8');
  // Nao deixa o navegador/CDN guardar dados internos de associados.
  res.setHeader('cache-control', 'private, no-store, max-age=0');
  if (dado.atualizadoEm) res.setHeader('x-atualizado-em', dataBr(dado.atualizadoEm) || '');
  res.end(dado.html);
}
