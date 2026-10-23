// GET / -> pagina inicial com os dois paineis (protegida por login).
import { infoPaineis, exigirLogin, escapar, dataBr, paginaAviso } from '../lib/util.js';

export default async function handler(req, res) {
  if (!exigirLogin(req, res)) return;

  let info;
  try {
    info = await infoPaineis();
  } catch (e) {
    res.statusCode = 500;
    res.setHeader('content-type', 'text/html; charset=utf-8');
    res.end(paginaAviso('Erro ao carregar', String(e)));
    return;
  }

  const cartao = (href, nome) => {
    const p = info[nome];
    const quando = p.atualizadoEm ? `Atualizado em ${dataBr(p.atualizadoEm)}` : 'Nenhuma atualização enviada ainda';
    const vazio = p.atualizadoEm ? '' : ' vazio';
    return `<a class="cartao${vazio}" href="${href}">
      <span class="titulo">${escapar(p.titulo)}</span>
      <span class="quando">${escapar(quando)}</span>
      <span class="seta">Abrir painel →</span>
    </a>`;
  };

  const html = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painéis · Grupo Support</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{--verde:#a9c927;--verde-600:#748c05;--cinza:#4d4d4d;--tinta:#373435;--mudo:#8c898a;
    --linha:#e7e7e4;--plano:#f6f6f3;--superficie:#fff;}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;background:var(--plano);color:var(--tinta);
    font:400 15px/1.6 "Poppins","Segoe UI",system-ui,-apple-system,sans-serif}
  .topo{background:var(--cinza);color:#fff;font-size:12.5px;padding:9px 0}
  .largura{max-width:960px;margin:0 auto;padding:0 24px}
  header.marca{background:var(--superficie);box-shadow:0 1px 0 var(--linha)}
  header.marca .largura{display:flex;align-items:center;gap:12px;padding:16px 24px}
  .logo{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:9px;
    background:var(--verde);color:#fff;font-weight:700}
  header h1{font-size:17px;margin:0;color:var(--cinza);font-weight:600}
  main{padding:32px 0 48px}
  main h2{font-size:14px;color:var(--mudo);font-weight:500;text-transform:uppercase;
    letter-spacing:.6px;margin:0 0 16px}
  .grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px}
  .cartao{display:flex;flex-direction:column;gap:6px;text-decoration:none;color:inherit;
    background:var(--superficie);border:1px solid var(--linha);border-radius:16px;padding:22px;
    box-shadow:0 8px 24px rgba(0,0,0,.04);transition:transform .15s,box-shadow .15s,border-color .15s}
  .cartao:hover{transform:translateY(-2px);box-shadow:0 14px 32px rgba(0,0,0,.09);border-color:var(--verde)}
  .cartao .titulo{font-size:18px;font-weight:600;color:var(--tinta)}
  .cartao .quando{font-size:13px;color:var(--mudo)}
  .cartao.vazio .quando{color:#c08a1a}
  .cartao .seta{margin-top:8px;font-size:13.5px;font-weight:600;color:var(--verde-600)}
  footer{color:var(--mudo);font-size:12.5px;padding:0 0 32px}
</style></head><body>
  <div class="topo"><div class="largura">Integrador SIGA × SGA — uso interno</div></div>
  <header class="marca"><div class="largura">
    <span class="logo">GS</span><h1>Painéis · Grupo Support</h1>
  </div></header>
  <main><div class="largura">
    <h2>Escolha um painel</h2>
    <div class="grade">
      ${cartao('/finalizados', 'finalizados')}
      ${cartao('/acompanhamento', 'acompanhamento')}
    </div>
  </div></main>
  <footer><div class="largura">Dados de associados — não compartilhe o endereço nem a senha.</div></footer>
</body></html>`;

  res.statusCode = 200;
  res.setHeader('content-type', 'text/html; charset=utf-8');
  res.setHeader('cache-control', 'private, no-store, max-age=0');
  res.end(html);
}
