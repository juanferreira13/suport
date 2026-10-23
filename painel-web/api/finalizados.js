// GET /finalizados -> painel "Conferência de finalizados"
import servirPainel from '../lib/servir.js';

export default function handler(req, res) {
  return servirPainel(req, res, 'finalizados');
}
