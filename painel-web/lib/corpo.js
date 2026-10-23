// Leitura do corpo do upload, isolada (sem depender de armazenamento) para ser testavel.
// Aceita { html_base64 }, { html } ou o HTML direto no corpo do pedido.

async function corpoBruto(req) {
  const partes = [];
  for await (const p of req) partes.push(p);
  return Buffer.concat(partes);
}

export async function extrairHtml(req) {
  let corpo = req.body;
  if (corpo === undefined || corpo === null || corpo === '') {
    corpo = (await corpoBruto(req)).toString('utf8');
  }
  if (Buffer.isBuffer(corpo)) corpo = corpo.toString('utf8');

  let html;
  if (typeof corpo === 'string') {
    const tipo = (req.headers?.['content-type'] || '').toLowerCase();
    if (tipo.includes('application/json')) {
      const j = JSON.parse(corpo);
      html = j.html_base64 ? Buffer.from(j.html_base64, 'base64').toString('utf8') : j.html;
    } else {
      html = corpo;
    }
  } else if (corpo && typeof corpo === 'object') {
    html = corpo.html_base64 ? Buffer.from(corpo.html_base64, 'base64').toString('utf8') : corpo.html;
  }
  return html;
}
