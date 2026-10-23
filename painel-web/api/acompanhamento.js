// GET /acompanhamento -> painel "Acompanhamento dos analistas"
import servirPainel from '../lib/servir.js';

export default function handler(req, res) {
  return servirPainel(req, res, 'acompanhamento');
}
