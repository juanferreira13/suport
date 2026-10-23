"""Grava cliques e tira 'foto' do HTML da tela para ajustar a automação quando algo falha."""
import json
from datetime import datetime

from playwright.sync_api import BrowserContext

from siga import LOGS

JS_ESCUTA = """
(() => {
  if (window.__sigaEscuta) return; window.__sigaEscuta = true;
  const desc = el => ({
    tag: el.tagName.toLowerCase(), id: el.id || '',
    cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal) || ''),
    texto: (el.innerText || el.textContent || '').trim().slice(0, 80),
    title: el.getAttribute('title') || el.getAttribute('aria-label') || '',
    src: el.getAttribute('src') || '', href: (el.getAttribute('href') || '').slice(0, 200),
    onclick: (el.getAttribute('onclick') || '').slice(0, 300),
  });
  document.addEventListener('click', e => {
    const caminho = []; let el = e.target;
    for (let i = 0; i < 8 && el && el.tagName; i++) { caminho.push(desc(el)); el = el.parentElement; }
    try { window.__sigaLog({url: location.href, x: e.clientX, y: e.clientY,
                            html: (e.target.outerHTML || '').slice(0, 800), caminho}); } catch (_) {}
  }, true);
})();
"""


class Gravador:
    def __init__(self, ctx: BrowserContext):
        LOGS.mkdir(exist_ok=True)
        self.ctx = ctx
        self.arquivo = LOGS / f"cliques_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        ctx.expose_binding("__sigaLog", self._registrar)
        ctx.add_init_script(JS_ESCUTA)
        ctx.on("page", lambda p: self._registrar(None, {"evento": "nova_janela", "url": p.url}))
        for pg in ctx.pages:
            self._ligar_download(pg)
            for fr in pg.frames:
                try:
                    fr.evaluate(JS_ESCUTA)
                except Exception:
                    pass
        ctx.on("page", self._ligar_download)

    def _ligar_download(self, pg):
        pg.on("download", lambda d: self._registrar(
            None, {"evento": "download", "arquivo": d.suggested_filename, "url": d.url[:200]}))

    def _registrar(self, _source, dados):
        dados["hora"] = datetime.now().isoformat(timespec="seconds")
        with self.arquivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dados, ensure_ascii=False) + "\n")

    def fotografar(self, rotulo: str):
        """Salva screenshot + HTML de todos os frames em logs/<rotulo>_<hora>/."""
        pasta = LOGS / f"{rotulo}_{datetime.now():%Y%m%d_%H%M%S}"
        pasta.mkdir(parents=True, exist_ok=True)
        erros = [f"janelas abertas: {len(self.ctx.pages)}"]
        for pi, pg in enumerate(self.ctx.pages):
            for fi, fr in enumerate(pg.frames):
                try:
                    (pasta / f"janela{pi}_frame{fi}.html").write_text(
                        f"<!-- {fr.url} -->\n" + fr.content(), encoding="utf-8")
                except Exception as e:
                    erros.append(f"frame {pi}/{fi} {fr.url}: {e}")
            try:
                pg.screenshot(path=str(pasta / f"janela{pi}.png"), timeout=15000)
            except Exception as e:
                erros.append(f"screenshot {pi}: {e}")
        (pasta / "erros.txt").write_text("\n".join(erros), encoding="utf-8")
        return pasta
