// Teste local do que NAO depende da Vercel: autenticacao e leitura do corpo.
// Rode com:  node test/local.mjs
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import { extrairHtml } from '../lib/corpo.js';
import { uploadAutorizado, exigirLogin } from '../lib/util.js';

let passou = 0;
async function t(nome, fn) {
  try { await fn(); passou++; console.log('  ok  ' + nome); }
  catch (e) { console.error('FALHOU ' + nome + '\n       ' + e.message); process.exitCode = 1; }
}

function reqBody(body, headers = {}) { return { body, headers }; }
function reqStream(texto, headers = {}) {
  const r = Readable.from([Buffer.from(texto, 'utf8')]);
  r.headers = headers;
  return r;
}
function fakeRes() {
  return {
    statusCode: 200, headers: {}, corpo: '',
    setHeader(k, v) { this.headers[k.toLowerCase()] = v; },
    end(c) { this.corpo = c || ''; },
  };
}

const HTML = '<!doctype html><html><body>oi associados</body></html>';
const B64 = Buffer.from(HTML, 'utf8').toString('base64');

console.log('extrairHtml:');
await t('json com html_base64', async () => {
  const r = reqBody(JSON.stringify({ html_base64: B64 }), { 'content-type': 'application/json' });
  assert.equal(await extrairHtml(r), HTML);
});
await t('json com html em texto', async () => {
  const r = reqBody(JSON.stringify({ html: HTML }), { 'content-type': 'application/json' });
  assert.equal(await extrairHtml(r), HTML);
});
await t('body ja como objeto (Vercel parseou)', async () => {
  const r = reqBody({ html_base64: B64 }, { 'content-type': 'application/json' });
  assert.equal(await extrairHtml(r), HTML);
});
await t('html cru no corpo (text/html)', async () => {
  const r = reqBody(HTML, { 'content-type': 'text/html' });
  assert.equal(await extrairHtml(r), HTML);
});
await t('corpo vazio -> le o stream', async () => {
  const r = reqStream(JSON.stringify({ html_base64: B64 }), { 'content-type': 'application/json' });
  assert.equal(await extrairHtml(r), HTML);
});

console.log('uploadAutorizado:');
process.env.UPLOAD_SECRET = 'segredo-forte-123';
await t('bearer correto', () => assert.equal(uploadAutorizado(reqBody(null, { authorization: 'Bearer segredo-forte-123' })), true));
await t('bearer errado', () => assert.equal(uploadAutorizado(reqBody(null, { authorization: 'Bearer outro' })), false));
await t('sem header', () => assert.equal(uploadAutorizado(reqBody(null, {})), false));

console.log('exigirLogin:');
await t('sem VIEW_PASSWORD -> 503', () => {
  delete process.env.VIEW_PASSWORD;
  const res = fakeRes();
  assert.equal(exigirLogin(reqBody(null, {}), res), false);
  assert.equal(res.statusCode, 503);
});
await t('sem credenciais -> 401 + WWW-Authenticate', () => {
  process.env.VIEW_USER = 'support'; process.env.VIEW_PASSWORD = 'senha-xyz';
  const res = fakeRes();
  assert.equal(exigirLogin(reqBody(null, {}), res), false);
  assert.equal(res.statusCode, 401);
  assert.match(res.headers['www-authenticate'], /Basic/);
});
await t('credenciais corretas -> true', () => {
  const cred = Buffer.from('support:senha-xyz', 'utf8').toString('base64');
  const res = fakeRes();
  assert.equal(exigirLogin(reqBody(null, { authorization: 'Basic ' + cred }), res), true);
});
await t('senha errada -> 401', () => {
  const cred = Buffer.from('support:errada', 'utf8').toString('base64');
  const res = fakeRes();
  assert.equal(exigirLogin(reqBody(null, { authorization: 'Basic ' + cred }), res), false);
  assert.equal(res.statusCode, 401);
});

console.log(`\n${passou} testes ok.`);
