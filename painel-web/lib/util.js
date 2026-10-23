// Funcoes compartilhadas pelas funcoes serverless (/api/*).
// Armazena e le os paineis no Vercel Blob e cuida da autenticacao.
import { put, list, get } from '@vercel/blob';
import crypto from 'node:crypto';

// Paineis aceitos. A chave e o nome usado na URL e no upload (?painel=...).
export const PAINEIS = {
  finalizados: { arquivo: 'finalizados.html', titulo: 'Conferência de finalizados' },
  acompanhamento: { arquivo: 'acompanhamento.html', titulo: 'Acompanhamento dos analistas' },
};

// Compara dois textos em tempo constante (nao vaza o tamanho/conteudo da senha).
function igual(a, b) {
  const x = Buffer.from(String(a ?? ''), 'utf8');
  const y = Buffer.from(String(b ?? ''), 'utf8');
  if (x.length !== y.length) return false;
  return crypto.timingSafeEqual(x, y);
}

// --------------------------------------------------------------- autenticacao

// Upload (ferramenta local -> site): header "Authorization: Bearer <UPLOAD_SECRET>".
export function uploadAutorizado(req) {
  const esperado = process.env.UPLOAD_SECRET;
  if (!esperado) return false; // sem segredo configurado, ninguem envia
  const cabecalho = req.headers['authorization'] || '';
  const [tipo, valor] = cabecalho.split(' ');
  if ((tipo || '').toLowerCase() !== 'bearer' || !valor) return false;
  return igual(valor, esperado);
}

// Visualizacao (navegador -> site): HTTP Basic Auth contra VIEW_USER/VIEW_PASSWORD.
// Devolve true se liberado; se nao, responde 401 e devolve false.
export function exigirLogin(req, res) {
  const usuario = process.env.VIEW_USER || 'support';
  const senha = process.env.VIEW_PASSWORD;
  // Sem senha configurada, bloqueia tudo (evita expor dados por engano).
  if (!senha) {
    res.statusCode = 503;
    res.setHeader('content-type', 'text/html; charset=utf-8');
    res.end(paginaAviso('Site ainda não configurado',
      'Defina a variável de ambiente VIEW_PASSWORD no projeto da Vercel para liberar o acesso.'));
    return false;
  }
  const cabecalho = req.headers['authorization'] || '';
  const [tipo, valor] = cabecalho.split(' ');
  if ((tipo || '').toLowerCase() === 'basic' && valor) {
    const [u, s] = Buffer.from(valor, 'base64').toString('utf8').split(':');
    if (igual(u, usuario) && igual(s, senha)) return true;
  }
  res.statusCode = 401;
  res.setHeader('WWW-Authenticate', 'Basic realm="Paineis Grupo Support", charset="UTF-8"');
  res.setHeader('content-type', 'text/html; charset=utf-8');
  res.end(paginaAviso('Acesso restrito', 'Informe o usuário e a senha para ver os painéis.'));
  return false;
}

// --------------------------------------------------------------- armazenamento

// Guarda o HTML de um painel (sobrescreve o anterior). Acesso PRIVADO: o
// conteudo (dados de associados) nunca fica disponivel por URL publica; so o
// servidor, com o token do Blob, consegue le-lo de volta.
export async function salvarPainel(nome, html) {
  const alvo = PAINEIS[nome];
  if (!alvo) throw new Error(`Painel desconhecido: ${nome}`);
  await put(alvo.arquivo, html, {
    access: 'private',
    contentType: 'text/html; charset=utf-8',
    addRandomSuffix: false,
    allowOverwrite: true,
  });
}

// Le o HTML de um painel guardado. Devolve { html, atualizadoEm } ou null.
export async function lerPainel(nome) {
  const alvo = PAINEIS[nome];
  if (!alvo) throw new Error(`Painel desconhecido: ${nome}`);
  const r = await get(alvo.arquivo, { access: 'private', useCache: false });
  if (!r || r.statusCode !== 200 || !r.stream) return null;
  const html = await new Response(r.stream).text();
  return { html, atualizadoEm: r.blob?.uploadedAt || null };
}

// So os metadados (sem baixar o HTML inteiro) - usado na pagina inicial.
export async function infoPaineis() {
  const { blobs } = await list({ limit: 100 });
  const porArquivo = new Map(blobs.map((b) => [b.pathname, b]));
  const saida = {};
  for (const [nome, alvo] of Object.entries(PAINEIS)) {
    const b = porArquivo.get(alvo.arquivo);
    saida[nome] = { titulo: alvo.titulo, atualizadoEm: b ? b.uploadedAt || null : null };
  }
  return saida;
}

// --------------------------------------------------------------- html auxiliar

export function escapar(texto) {
  return String(texto ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function dataBr(valor) {
  if (!valor) return null;
  const d = new Date(valor);
  if (isNaN(d)) return null;
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' });
}

// Pagina simples (avisos, 401, 503, 404) na identidade do Grupo Support.
export function paginaAviso(titulo, mensagem) {
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapar(titulo)} · Grupo Support</title>
<style>
  :root{--verde:#a9c927;--cinza:#4d4d4d;--tinta:#373435;--plano:#f6f6f3;}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:var(--plano);color:var(--tinta);
    font:400 15px/1.6 "Poppins","Segoe UI",system-ui,-apple-system,sans-serif;padding:24px}
  .caixa{background:#fff;border:1px solid #e7e7e4;border-radius:16px;max-width:460px;width:100%;
    padding:32px;box-shadow:0 10px 30px rgba(0,0,0,.06);text-align:center}
  .marca{display:inline-block;background:var(--verde);color:#fff;font-weight:600;font-size:13px;
    padding:4px 12px;border-radius:999px;margin-bottom:16px;letter-spacing:.3px}
  h1{font-size:20px;margin:0 0 10px;color:var(--cinza)}
  p{margin:0;color:#666364}
</style></head><body><div class="caixa">
  <span class="marca">Grupo Support</span>
  <h1>${escapar(titulo)}</h1>
  <p>${escapar(mensagem)}</p>
</div></body></html>`;
}
