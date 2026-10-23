"""Tela de atualização: login do SIGA, barra de progresso e status, sem mostrar o navegador.

Abre uma janela do Edge em modo aplicativo apontando para um servidor local (127.0.0.1).
A atualização em si continua sendo integrar_atualizacao.py, rodando escondida.
Execute pelo atalho 'Grupo Support - Atualizar SIGA' ou pelo 'Atualizar agora.bat'.
"""
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import winreg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
PY = ROOT / 'sistema' / 'python' / 'python.exe'
INTEGRAR = ROOT / 'integrar_atualizacao.py'
RESULTADOS = ROOT / 'RESULTADOS'
SISTEMA = ROOT / 'sistema'
LOGO = SISTEMA / 'logo.webp'            # logo oficial (supportgrupo.com.br)
ICONE = SISTEMA / 'grupo_support.ico'   # ícone oficial (favicon do site)
DESTINO_PADRAO = ROOT.parent            # pasta onde fica o atalho
PREVIA = SISTEMA / 'dados' / 'previa_navegador.jpg'  # quadro mais recente do Edge oculto (exportar_v3.Previa)
CONFIG_ENV = SISTEMA / 'configuracao.env'
GOOGLE_JSON = SISTEMA / 'dados' / 'google.json'      # planilhas do Google já usadas pelo sistema

# Painéis (HTML) gerados pelo sistema e planilhas do Google mostrados em "Resultados".
PAINEIS = {
    'finalizados': ('Conferência de finalizados', 'CONFERENCIA FINALIZADOS.html'),
    'acompanhamento': ('Acompanhamento dos analistas', 'ACOMPANHAMENTO ANALISTAS.html'),
}
PLANILHAS = {  # chave: (título, variável do configuracao.env)
    'sinistro': ('Gerencial Sinistro', 'GOOGLE_SINISTRO'),
    'analistas': ('Analistas', 'GOOGLE_ANALISTAS'),
    'consultores': ('Consultores Técnicos', 'GOOGLE_CONSULTORES'),
    'reguladores': ('Reguladores', 'GOOGLE_REGULADORES'),
}
RE_ID_PLANILHA = re.compile(r'^(?:https://docs\.google\.com/spreadsheets/d/)?([A-Za-z0-9_-]{25,})(?:[/?#].*)?$')
LOCK = ROOT / '.siga_v3_atualizacao.lock'
V2 = ROOT / 'siga_automacao-v2' / 'siga_automacao'
PREFS = V2 / 'preferencias_tela.json'
PERFIL_TELA = ROOT / 'sistema' / 'dados' / 'perfil_tela'
CODIGO_ERRO_LOGIN = 3  # mesmo código de exportar_v3.py / integrar_atualizacao.py
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW

sys.path.insert(0, str(V2))
import credenciais_portatil as credenciais  # noqa: E402

TOKEN = secrets.token_urlsafe(24)


# ------------------------------------------------------------------ estado

class Execucao:
    """Estado da atualização compartilhado com a página (lido por /estado)."""

    def __init__(self):
        self.trava = threading.Lock()
        self.proc = None
        self.rodando = False
        self.pct = 0
        self.status = 'Pronto para conectar'
        self.detalhe = ''        # sub-etapa atual (ex.: 'carregando pela API do SIGA: 250 de 4125')
        self.etapas = []         # [{'msg', 'detalhe', 'inicio', 'fim'}] mostradas em Detalhes
        self.linhas = []
        self.previa_final = None  # último quadro do navegador, guardado em memória ao terminar
        self.fim = None          # {'codigo': int, 'tipo': 'ok'|'login'|'erro'|'cancelado', 'msg': str}
        self.ultimo_erro = ''
        self.ultimo_contato = time.time()

    def log(self, linha):
        with self.trava:
            self.linhas.append(linha)
            del self.linhas[:-2000]


execucao = Execucao()


def ler_prefs():
    try:
        return json.loads(PREFS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def gravar_prefs(**valores):
    prefs = ler_prefs()
    prefs.update(valores)
    PREFS.write_text(json.dumps(prefs, ensure_ascii=False), encoding='utf-8')


def credencial_salva():
    try:
        return credenciais.carregar()
    except Exception:  # arquivo de outro usuário do Windows ou corrompido
        return None


def destino_atual():
    return ler_prefs().get('destino') or str(DESTINO_PADRAO)


def ler_config_env():
    valores = {}
    try:
        for linha in CONFIG_ENV.read_text(encoding='utf-8-sig').splitlines():
            if '=' in linha and not linha.lstrip().startswith('#'):
                chave, valor = linha.split('=', 1)
                valores[chave.strip()] = valor.strip()
    except OSError:
        pass
    return valores


def id_planilha(texto):
    m = RE_ID_PLANILHA.match((texto or '').strip())
    return m.group(1) if m else None


def link_planilha(chave):
    """Link salvo na tela > configuracao.env > planilha já usada pelo sistema (só a do Sinistro)."""
    ident = id_planilha(ler_prefs().get('links', {}).get(chave, ''))
    ident = ident or id_planilha(ler_config_env().get(PLANILHAS[chave][1], ''))
    if not ident and chave == 'sinistro':
        try:
            ident = next(iter(json.loads(GOOGLE_JSON.read_text(encoding='utf-8'))), None)
        except (OSError, ValueError):
            ident = None
    return f'https://docs.google.com/spreadsheets/d/{ident}/edit' if ident else None


def arquivo_painel(chave):
    """A cópia na pasta escolhida; sem ela, a de RESULTADOS."""
    nome = PAINEIS[chave][1]
    for pasta in (Path(destino_atual()), RESULTADOS):
        if (pasta / nome).is_file():
            return pasta / nome
    return None


def info_resultados():
    paineis = []
    for chave, (titulo, _) in PAINEIS.items():
        arq = arquivo_painel(chave)
        paineis.append({'chave': chave, 'titulo': titulo, 'existe': bool(arq),
                        'atualizado': time.strftime('%d/%m/%Y %H:%M', time.localtime(arq.stat().st_mtime)) if arq else '',
                        'versao': int(arq.stat().st_mtime) if arq else 0,
                        'pasta': str(arq.parent) if arq else ''})
    planilhas = [{'chave': c, 'titulo': titulo, 'link': link_planilha(c)} for c, (titulo, _) in PLANILHAS.items()]
    return {'paineis': paineis, 'planilhas': planilhas, 'chrome': bool(achar_chrome())}


def achar_chrome():
    for chave in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(chave, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as k:
                caminho = winreg.QueryValue(k, None)
                if caminho and Path(caminho).is_file():
                    return caminho
        except OSError:
            pass
    for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LOCALAPPDATA')):
        caminho = Path(base or '') / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'
        if caminho.is_file():
            return str(caminho)
    return None


def abrir_no_chrome(alvo):
    """Painéis e planilhas abrem no Google Chrome; sem Chrome, no navegador padrão."""
    chrome = achar_chrome()
    if chrome:
        subprocess.Popen([chrome, str(alvo)], creationflags=SEM_JANELA)
    else:
        os.startfile(str(alvo))


def escolher_pasta(inicial):
    """Janela 'Procurar Pasta' do Windows (a página não tem acesso a caminhos do disco)."""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$dono = New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description = 'Escolha onde salvar as planilhas Excel e os painéis HTML';"
        "$d.ShowNewFolderButton = $true;"
        "if (Test-Path -LiteralPath $env:PASTA_INICIAL) { $d.SelectedPath = $env:PASTA_INICIAL };"
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
        "if ($d.ShowDialog($dono) -eq 'OK') { $d.SelectedPath }")
    env = dict(os.environ, PASTA_INICIAL=inicial)
    saida = subprocess.run(['powershell', '-NoProfile', '-STA', '-Command', script], env=env,
                           capture_output=True, creationflags=SEM_JANELA).stdout
    escolhida = saida.decode('utf-8', errors='replace').strip()
    return escolhida or None


def iniciar(usuario, senha, lembrar, destino):
    salvo = credencial_salva()
    if not senha and salvo and salvo[0] == usuario:
        senha = salvo[1]  # campo vazio = usar a senha guardada
    if not usuario or not senha:
        return 'Informe login e senha.'
    try:
        Path(destino).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f'Não consegui usar a pasta de destino: {e}'
    with execucao.trava:
        if execucao.rodando:
            return 'Já existe uma atualização em andamento.'
        execucao.rodando = True
        execucao.pct, execucao.status, execucao.fim, execucao.ultimo_erro = 0, 'Iniciando', None, ''
        execucao.detalhe, execucao.etapas, execucao.linhas = '', [], []
        execucao.previa_final = None
    PREVIA.unlink(missing_ok=True)
    gravar_prefs(lembrar=lembrar, usuario=usuario if lembrar else '', destino=destino)
    threading.Thread(target=rodar, args=(usuario, senha, lembrar, destino), daemon=True).start()
    return None


def rodar(usuario, senha, lembrar, destino):
    env = os.environ.copy()
    env.update(SIGA_V3_USUARIO=usuario, SIGA_V3_SENHA=senha, SIGA_V3_OCULTO='1', SIGA_V3_DESTINO=destino,
               SIGA_V3_PREVIA=str(PREVIA),
               PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    codigo = -1
    erro_login = ''
    try:
        proc = subprocess.Popen([str(PY), '-u', str(INTEGRAR)], cwd=str(ROOT), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=SEM_JANELA)
        execucao.proc = proc
        for bruta in proc.stdout:
            linha = bruta.decode('utf-8', errors='replace').rstrip()
            if linha.startswith('@@PROGRESSO '):
                _, pct, *msg = linha.split(' ', 2)
                with execucao.trava:
                    execucao.pct = max(execucao.pct, int(pct))
                    if msg and msg[0] != execucao.status:
                        execucao.status, execucao.detalhe = msg[0], ''
                        agora = time.time()
                        if execucao.etapas:
                            execucao.etapas[-1]['fim'] = agora
                        execucao.etapas.append({'msg': msg[0], 'detalhe': '', 'inicio': agora, 'fim': None})
                continue
            if linha.startswith('@@DETALHE '):
                with execucao.trava:
                    execucao.detalhe = linha[len('@@DETALHE '):]
                    if execucao.etapas:
                        execucao.etapas[-1]['detalhe'] = execucao.detalhe
                continue
            if linha == '@@LOGIN_OK':
                # Só guarda a senha depois que o SIGA aceitou.
                if lembrar:
                    credenciais.salvar(usuario, senha)
                else:
                    credenciais.apagar()
                execucao.log('Login aceito pelo SIGA.')
                continue
            if linha.startswith('@@ERRO_LOGIN'):
                erro_login = linha[len('@@ERRO_LOGIN'):].strip()
                continue
            if linha.strip():
                execucao.log(linha)
                if linha.startswith(('ERRO', 'FALHA')):
                    execucao.ultimo_erro = linha
        codigo = proc.wait()
    except Exception as e:  # noqa: BLE001 - qualquer falha precisa aparecer na tela
        execucao.log(f'ERRO ao iniciar a atualização: {e}')
        execucao.ultimo_erro = str(e)
    finally:
        execucao.proc = None
        # A imagem mostra dados de associados: não fica no disco depois da atualização.
        try:
            execucao.previa_final = PREVIA.read_bytes()
            PREVIA.unlink()
        except OSError:
            pass

    with execucao.trava:
        if execucao.etapas and execucao.etapas[-1]['fim'] is None:
            execucao.etapas[-1]['fim'] = time.time()
        if execucao.fim is not None:  # cancelado pelo usuário
            pass
        elif codigo == 0:
            execucao.fim = {'codigo': 0, 'tipo': 'ok',
                            'msg': f'Atualização concluída. Planilhas e painéis salvos em {destino}'}
            execucao.pct, execucao.status = 100, 'Atualização concluída'
        elif codigo == CODIGO_ERRO_LOGIN:
            # Senha guardada errada não deve voltar a ser usada.
            salvo = credencial_salva()
            if salvo and salvo[0] == usuario:
                credenciais.apagar()
            execucao.fim = {'codigo': codigo, 'tipo': 'login',
                            'msg': 'Login ou senha recusados pelo SIGA. Corrija e conecte de novo.'
                                   + (f' ({erro_login})' if erro_login else '')}
            execucao.status = 'Login recusado'
        else:
            execucao.fim = {'codigo': codigo, 'tipo': 'erro',
                            'msg': execucao.ultimo_erro or f'A atualização parou (código {codigo}).'}
            execucao.status = 'A atualização parou'
        execucao.rodando = False


def cancelar():
    proc = execucao.proc
    with execucao.trava:
        if not execucao.rodando:
            return
        execucao.fim = {'codigo': -1, 'tipo': 'cancelado', 'msg': 'Atualização cancelada.'}
        execucao.status = 'Cancelado'
    if proc:
        # /T derruba também o exportador e o Edge oculto.
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                       capture_output=True, creationflags=SEM_JANELA)
    time.sleep(1)
    LOCK.unlink(missing_ok=True)


# ------------------------------------------------------------------ servidor

class Servidor(ThreadingHTTPServer):
    """Porta exclusiva: no Windows o padrão (SO_REUSEADDR) deixa duas telas abertas na mesma porta,
    e uma passa a receber os pedidos da outra."""
    allow_reuse_address = False

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _autorizado(self):
        q = parse_qs(urlparse(self.path).query)
        return secrets.compare_digest(q.get('t', [''])[0], TOKEN)

    def _responder(self, codigo, corpo, tipo='application/json; charset=utf-8'):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        if not self._autorizado():
            return self._responder(403, {'erro': 'acesso negado'})
        rota = urlparse(self.path).path
        execucao.ultimo_contato = time.time()
        if rota == '/':
            return self._responder(200, PAGINA.encode('utf-8'), 'text/html; charset=utf-8')
        if rota == '/resultados_info':
            return self._responder(200, info_resultados())
        if rota == '/painel':
            chave = parse_qs(urlparse(self.path).query).get('n', [''])[0]
            arq = arquivo_painel(chave) if chave in PAINEIS else None
            if not arq:
                return self._responder(404, {'erro': 'painel não encontrado'})
            return self._responder(200, arq.read_bytes(), 'text/html; charset=utf-8')
        if rota == '/previa':
            try:
                dados = PREVIA.read_bytes()
            except OSError:
                dados = execucao.previa_final
            if not dados:
                return self._responder(404, {'erro': 'sem imagem'})
            return self._responder(200, dados, 'image/jpeg')
        if rota in ('/logo', '/icone'):
            arquivo, tipo = (LOGO, 'image/webp') if rota == '/logo' else (ICONE, 'image/x-icon')
            if not arquivo.is_file():
                return self._responder(404, {'erro': 'sem arquivo'})
            return self._responder(200, arquivo.read_bytes(), tipo)
        if rota == '/estado':
            desde = int(parse_qs(urlparse(self.path).query).get('desde', ['0'])[0])
            prefs = ler_prefs()
            salvo = credencial_salva()
            with execucao.trava:
                return self._responder(200, {
                    'rodando': execucao.rodando, 'pct': execucao.pct, 'status': execucao.status,
                    'detalhe': execucao.detalhe, 'etapas': execucao.etapas, 'agora': time.time(),
                    'previa': PREVIA.is_file() or bool(execucao.previa_final),
                    'fim': execucao.fim, 'linhas': execucao.linhas[desde:], 'total_linhas': len(execucao.linhas),
                    'lembrar': prefs.get('lembrar', True),
                    'usuario': prefs.get('usuario', '') if prefs.get('lembrar', True) else '',
                    'senha_salva': bool(salvo and salvo[0] == prefs.get('usuario')),
                    'destino': destino_atual(),
                })
        return self._responder(404, {'erro': 'rota'})

    def do_POST(self):
        if not self._autorizado():
            return self._responder(403, {'erro': 'acesso negado'})
        rota = urlparse(self.path).path
        tamanho = int(self.headers.get('Content-Length') or 0)
        corpo = json.loads(self.rfile.read(tamanho) or b'{}')
        if rota == '/conectar':
            erro = iniciar(str(corpo.get('usuario', '')).strip(), str(corpo.get('senha', '')),
                           bool(corpo.get('lembrar')), str(corpo.get('destino') or destino_atual()))
            return self._responder(400 if erro else 200, {'erro': erro})
        if rota == '/lembrar':
            lembrar = bool(corpo.get('lembrar'))
            gravar_prefs(lembrar=lembrar, **({} if lembrar else {'usuario': ''}))
            if not lembrar:
                credenciais.apagar()
            return self._responder(200, {})
        if rota == '/cancelar':
            cancelar()
            return self._responder(200, {})
        if rota == '/escolher_pasta':
            pasta = escolher_pasta(destino_atual())
            if pasta:
                gravar_prefs(destino=pasta)
            return self._responder(200, {'destino': pasta})
        if rota == '/resultados':
            os.startfile(destino_atual())
            return self._responder(200, {})
        if rota == '/abrir':
            chave = str(corpo.get('chave', ''))
            if corpo.get('tipo') == 'painel' and chave in PAINEIS:
                alvo = arquivo_painel(chave)
            elif corpo.get('tipo') == 'planilha' and chave in PLANILHAS:
                alvo = link_planilha(chave)
            else:
                alvo = None
            if not alvo:
                return self._responder(404, {'erro': 'não encontrado'})
            abrir_no_chrome(alvo)
            return self._responder(200, {})
        if rota == '/link':
            chave, texto = str(corpo.get('chave', '')), str(corpo.get('link', '')).strip()
            if chave not in PLANILHAS:
                return self._responder(400, {'erro': 'planilha desconhecida'})
            if texto and not id_planilha(texto):
                return self._responder(400, {'erro': 'Cole o link da planilha do Google Sheets '
                                                     '(https://docs.google.com/spreadsheets/d/...).'})
            links = ler_prefs().get('links', {})
            links[chave] = texto
            gravar_prefs(links=links)
            return self._responder(200, info_resultados())
        return self._responder(404, {'erro': 'rota'})


def achar_edge():
    for chave in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(chave, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe') as k:
                caminho = winreg.QueryValue(k, None)
                if caminho and Path(caminho).is_file():
                    return caminho
        except OSError:
            pass
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
        caminho = Path(base or '') / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'
        if caminho.is_file():
            return str(caminho)
    return None


def main():
    # Porta fixa quando possível: a página de acompanhamento guarda rascunhos no navegador por
    # endereço, e com porta sorteada eles se perderiam a cada vez que a tela é aberta.
    servidor = None
    for porta in (47321, 47322, 47323, 0):
        try:
            servidor = Servidor(('127.0.0.1', porta), Handler)
            break
        except OSError:
            continue
    url = f'http://127.0.0.1:{servidor.server_address[1]}/?t={TOKEN}'
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    edge = achar_edge()
    janela = None
    if edge:
        PERFIL_TELA.mkdir(parents=True, exist_ok=True)
        janela = subprocess.Popen([edge, f'--app={url}', f'--user-data-dir={PERFIL_TELA}',
                                   '--window-size=660,940', '--no-first-run', '--no-default-browser-check'])
        time.sleep(3)
        if janela.poll() is not None:
            janela = None  # Edge entregou a janela a uma instância já aberta: não dá para acompanhar o processo
    else:
        import webbrowser
        webbrowser.open(url)

    # Encerra quando a janela do Edge fecha. Sem o processo para acompanhar, encerra quando a
    # página some por 2 min e nada está rodando (o Edge reduz o ritmo de páginas minimizadas).
    while True:
        time.sleep(1)
        if janela is not None:
            if janela.poll() is not None:
                break
        elif not execucao.rodando and time.time() - execucao.ultimo_contato > 120:
            break
    cancelar()
    servidor.shutdown()


# ------------------------------------------------------------------ página

PAGINA = r"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Grupo Support · Integração SIGA x SGA</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" id="favicon">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* Identidade Grupo Support: mesmas cores e fonte do painel (sistema/app/sinistro/painel_modelo.html) */
  :root { --verde:#a9c927; --verde-600:#748c05; --verde-700:#5c7007;
          --cinza:#4d4d4d; --tinta:#373435; --tinta-2:#666364; --mudo:#8c898a; --linha:#e7e7e4;
          --plano:#f6f6f3; --superficie:#fff; --critico:#d03b3b;
          --fonte:"Poppins","Segoe UI",system-ui,sans-serif; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--plano); color:var(--tinta); font:400 14px/1.5 var(--fonte); }
  .faixa { background:var(--cinza); color:#fff; font-size:12px; padding:7px 22px; display:flex;
           justify-content:space-between; letter-spacing:.3px; }
  .faixa strong { font-weight:600; }
  header { background:var(--superficie); border-bottom:3px solid var(--verde); padding:14px 22px;
           display:flex; align-items:center; justify-content:space-between; gap:16px; }
  header img { height:46px; display:block; }
  .logo-texto { font-weight:700; font-size:24px; color:var(--cinza); line-height:1; }
  .logo-texto small { display:block; font-weight:500; font-size:10px; letter-spacing:7px; }
  header .titulo { text-align:right; font-size:11px; letter-spacing:1.5px; text-transform:uppercase; color:var(--tinta-2); }
  header .titulo b { display:block; font-size:15px; letter-spacing:.5px; color:var(--tinta); text-transform:none; font-weight:600; }
  main { padding:18px 22px 22px; }
  .cartao { background:var(--superficie); border:1px solid var(--linha); border-radius:10px; padding:18px 20px; }
  .cartao + .cartao { margin-top:14px; }
  h2 { margin:0 0 4px; font-size:12px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:var(--verde-600); }
  label.campo { display:block; font-size:12.5px; font-weight:600; margin:12px 0 4px; }
  input[type=text], input[type=password] { width:100%; padding:9px 11px; font:inherit; font-size:14.5px;
         color:var(--tinta); border:1px solid #d5d4cf; border-radius:6px; outline:none; background:#fff; }
  input:focus { border-color:var(--verde); box-shadow:0 0 0 3px rgba(169,201,39,.25); }
  input:disabled { background:var(--plano); color:var(--mudo); }
  .lembrar { display:flex; gap:8px; align-items:center; margin:12px 0 0; font-size:13.5px; cursor:pointer; }
  .lembrar input { accent-color:var(--verde-600); width:16px; height:16px; }
  .pasta { display:flex; gap:8px; align-items:stretch; margin-top:6px; }
  .pasta .caminho { flex:1; min-width:0; padding:8px 11px; border:1px solid #d5d4cf; border-radius:6px; background:var(--plano);
         font-size:12.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; direction:rtl; text-align:left; }
  .dica { font-size:12px; color:var(--tinta-2); margin:4px 0 0; }
  button { font:inherit; font-size:14px; padding:9px 16px; border-radius:6px; border:1px solid #d5d4cf;
           background:#fff; color:var(--tinta); cursor:pointer; white-space:nowrap; }
  button:hover:not(:disabled) { border-color:var(--verde-600); }
  button.prim { background:var(--verde-600); border-color:var(--verde-600); color:#fff; font-weight:600;
           letter-spacing:.3px; flex:1; padding:11px 16px; }
  button.prim:hover:not(:disabled) { background:var(--verde-700); border-color:var(--verde-700); }
  button:disabled { opacity:.5; cursor:default; }
  .botoes { display:flex; gap:10px; margin-top:16px; }
  .msg { margin-top:10px; font-size:13px; min-height:19px; }
  .msg.erro { color:var(--critico); } .msg.ok { color:var(--verde-700); font-weight:500; }
  .linha-status { display:flex; justify-content:space-between; gap:10px; margin:6px 0 8px; font-size:13.5px; }
  #status { font-weight:600; } #pct { font-weight:600; color:var(--verde-600); font-variant-numeric:tabular-nums; }
  .trilho { height:12px; background:#ebeae5; border-radius:6px; overflow:hidden; }
  .barra { height:100%; width:0; background:var(--verde); border-radius:6px; transition:width .5s; }
  .barra.ativa { background-image:linear-gradient(45deg,rgba(255,255,255,.3) 25%,transparent 25%,transparent 50%,
        rgba(255,255,255,.3) 50%,rgba(255,255,255,.3) 75%,transparent 75%); background-size:20px 20px;
        animation:listras 1s linear infinite; }
  .barra.ok { background:var(--verde-600); } .barra.erro { background:var(--critico); }
  @keyframes listras { to { background-position:20px 0; } }
  .tempo { font-size:12px; color:var(--mudo); margin-top:6px; min-height:18px; }
  details { margin-top:8px; font-size:12.5px; } summary { cursor:pointer; color:var(--tinta-2); }
  pre { background:var(--plano); color:var(--tinta-2); border:1px solid var(--linha); border-radius:6px; padding:10px;
        height:170px; overflow:auto; font:11.5px/1.45 Consolas,"Cascadia Mono",monospace;
        white-space:pre-wrap; word-break:break-word; margin:8px 0 0; }

  /* símbolo (dois arcos) montado em camadas: gira enquanto atualiza */
  .marca { position:relative; aspect-ratio:1804/460; }
  .marca > * { position:absolute; left:0; top:0; height:100%; }
  .marca .texto-logo { width:100%; clip-path:inset(0 0 0 29.1%); }
  .marca canvas { width:29.1%; transform-origin:45.5% 49.3%; }
  header .marca { height:46px; }
  .arcos { position:relative; width:30px; height:26px; flex:none; }  /* proporção do símbolo 525x460 */
  .arcos canvas { position:absolute; inset:0; width:100%; height:100%; transform-origin:45.5% 49.3%; }
  .girando .arco-a { animation:giro 1.1s linear infinite; }
  .girando .arco-b { animation:giro 1.7s linear infinite; }
  @keyframes giro { from { transform:rotate(0); } to { transform:rotate(360deg); } }
  .status-esq { display:flex; align-items:center; gap:10px; min-width:0; }
  .status-esq .arcos { display:none; }
  .rodando .status-esq .arcos { display:block; }
  #detalhe { font-size:12.5px; color:var(--tinta-2); margin:-4px 0 8px; min-height:19px; }
  .pontos::after { content:''; animation:pontos 1.4s steps(4) infinite; }
  @keyframes pontos { 0% { content:''; } 25% { content:'.'; } 50% { content:'..'; } 75% { content:'...'; } }

  /* abas do topo: Atualização | Resultados (mesmo estilo do menu do site) */
  nav.abas { display:flex; gap:26px; padding:0 22px; background:var(--superficie); border-bottom:1px solid var(--linha); }
  .aba { border:0; border-bottom:3px solid transparent; border-radius:0; background:none; padding:11px 2px 9px;
         font-size:12.5px; font-weight:600; letter-spacing:1.2px; text-transform:uppercase; color:var(--tinta-2); }
  .aba:hover:not(:disabled) { color:var(--tinta); border-color:var(--linha); }
  .aba.ativa { color:var(--verde-700); border-bottom-color:var(--verde); }
  .selo { margin-left:4px; padding:1px 6px; border-radius:9px; background:var(--verde); color:#fff; font-size:10px;
          letter-spacing:.5px; vertical-align:1px; }

  /* aba Resultados: painel aberto dentro da tela + botão para o navegador */
  .seletor { display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }
  .seletor button { font-size:13px; padding:7px 12px; }
  .seletor button.ativo { background:var(--verde-600); border-color:var(--verde-600); color:#fff; font-weight:600; }
  .barra-painel { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:10px 0 8px;
                  font-size:12px; color:var(--mudo); }
  .visor { position:relative; border:1px solid var(--linha); border-radius:8px; overflow:hidden; background:var(--plano); }
  .visor iframe { display:block; width:100%; height:max(440px, calc(100vh - 330px)); border:0; background:#fff; }
  .visor-vazio { margin:0; padding:60px 20px; text-align:center; color:var(--mudo); }
  h3.sub-h { margin:16px 0 8px; font-size:12px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:var(--tinta-2); }
  .planilhas { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .planilha { display:flex; gap:6px; }
  .planilha .abrir { flex:1; display:flex; align-items:center; gap:8px; text-align:left; padding:9px 12px;
                     overflow:hidden; text-overflow:ellipsis; }
  .planilha .abrir svg { flex:none; }
  .planilha .abrir.sem-link { border-style:dashed; color:var(--tinta-2); }
  .planilha .editar { padding:9px 10px; color:var(--tinta-2); }
  .btn-verde { background:#fff; border-color:var(--verde-600); color:var(--verde-700); font-weight:600; }
  .btn-verde:hover:not(:disabled) { background:var(--verde-600); color:#fff; }

  /* visão ao vivo do navegador oculto */
  .previa { margin:10px 0 4px; border:1px solid var(--linha); border-radius:8px; overflow:hidden; background:var(--plano); }
  .previa figcaption { display:flex; align-items:center; gap:8px; padding:6px 10px; font-size:12px; color:var(--tinta-2);
                       background:#fff; border-bottom:1px solid var(--linha); }
  .previa img { display:block; width:100%; max-height:240px; object-fit:contain; background:#fff; }
  .ao-vivo { display:inline-flex; align-items:center; gap:5px; font-size:10.5px; font-weight:600; letter-spacing:1px;
             text-transform:uppercase; color:var(--critico); }
  .ao-vivo::before { content:''; width:7px; height:7px; border-radius:50%; background:currentColor;
                     animation:pulso 1.2s ease-in-out infinite; }
  .ao-vivo.parado { color:var(--mudo); } .ao-vivo.parado::before { animation:none; }
  @keyframes pulso { 50% { opacity:.25; } }

  /* Detalhes: etapas em lista clara */
  ol.etapas { list-style:none; margin:10px 0 0; padding:0; }
  ol.etapas li { display:grid; grid-template-columns:22px 1fr auto; gap:2px 8px; padding:7px 2px;
                 border-bottom:1px solid var(--linha); align-items:start; }
  ol.etapas li:last-child { border-bottom:0; }
  ol.etapas .ic { width:18px; height:18px; border-radius:50%; display:grid; place-items:center; margin-top:1px;
                  font-size:11px; font-weight:700; color:#fff; background:var(--verde-600); }
  ol.etapas .ic.erro { background:var(--critico); }
  ol.etapas .ic .arcos { width:21px; height:18px; }
  ol.etapas li.atual .ic { background:none; }
  ol.etapas .msg-etapa { font-weight:500; color:var(--tinta); }
  ol.etapas li.atual .msg-etapa { color:var(--verde-700); font-weight:600; }
  ol.etapas .sub { grid-column:2 / 4; font-size:12px; color:var(--tinta-2); }
  ol.etapas .dur { font-size:11.5px; color:var(--mudo); font-variant-numeric:tabular-nums; }
  .vazio { color:var(--mudo); font-size:12.5px; margin:10px 0 0; }
  details.tecnico { margin-top:10px; }

  /* ---------- abertura: fumaça -> dois arcos girando como rodas -> logo -> tela ---------- */
  .app { opacity:0; transform:translateY(10px); transition:opacity .7s ease, transform .7s ease; }
  body.pronto .app { opacity:1; transform:none; }
  #abertura { position:fixed; inset:0; z-index:10; background:#fff; display:flex; flex-direction:column;
              align-items:center; justify-content:center; overflow:hidden; cursor:pointer;
              transition:opacity .8s ease, filter .8s ease, transform .8s ease; }
  #abertura.saindo { opacity:0; filter:blur(10px); transform:scale(1.04); pointer-events:none; }
  .fumaca { position:absolute; left:50%; top:46%; width:260px; height:260px; margin:-130px 0 0 -130px;
            border-radius:50%; opacity:0; filter:blur(26px); animation:fumaca 2.6s ease-out forwards; }
  @keyframes fumaca {
    0%   { opacity:0;   transform:translate(0,0) scale(.3); }
    25%  { opacity:.85; }
    100% { opacity:0;   transform:translate(var(--dx),var(--dy)) scale(2.4); }
  }
  .marca-abertura { position:relative; width:min(78vw,430px); aspect-ratio:1804/460; }
  .marca-abertura > * { position:absolute; left:0; top:0; height:100%; }
  .marca-abertura .texto-logo { width:100%; clip-path:inset(0 0 0 29.1%); opacity:0; filter:blur(16px);
            transform:translateX(-14px); animation:surgir 1s ease-out 1.65s forwards; }
  .marca-abertura canvas { width:29.1%; opacity:0; transform-origin:45.5% 49.3%; }
  .marca-abertura .arco-a { animation:arcoA 2s cubic-bezier(.15,.75,.25,1) .35s forwards; }
  .marca-abertura .arco-b { animation:arcoB 2s cubic-bezier(.2,.7,.25,1) .35s forwards; }
  /* As duas rodas giram em velocidades diferentes e se encaixam (múltiplos de 360°: terminam na posição da logo). */
  @keyframes arcoA {
    0%   { opacity:0; filter:blur(12px); transform:rotate(-1080deg) scale(.55); }
    20%  { opacity:1; filter:blur(3px); }
    88%  { filter:blur(0); transform:rotate(10deg) scale(1.02); }
    100% { opacity:1; filter:blur(0); transform:rotate(0) scale(1); }
  }
  @keyframes arcoB {
    0%   { opacity:0; filter:blur(12px); transform:rotate(-720deg) scale(.55); }
    20%  { opacity:1; filter:blur(3px); }
    88%  { filter:blur(0); transform:rotate(-8deg) scale(1.02); }
    100% { opacity:1; filter:blur(0); transform:rotate(0) scale(1); }
  }
  @keyframes surgir { to { opacity:1; filter:blur(0); transform:none; } }
  .legenda-abertura { margin-top:22px; font-size:12px; letter-spacing:4px; text-transform:uppercase; color:var(--tinta-2);
            opacity:0; filter:blur(6px); animation:surgir .8s ease-out 2.2s forwards; }
  .credito { position:absolute; bottom:18px; left:0; right:0; text-align:center; font-size:11px; letter-spacing:.6px;
             color:var(--mudo); opacity:0; animation:surgir .9s ease-out 2.4s forwards; }
  .credito b { font-weight:600; color:var(--tinta-2); }
  @media (prefers-reduced-motion: reduce) {
    .fumaca { display:none; }
    .marca-abertura canvas, .marca-abertura .texto-logo, .legenda-abertura, .credito { animation:surgir .4s ease-out forwards; transform:none; }
  }
</style></head>
<body>
<div id="abertura" title="Clique para pular">
  <div class="marca-abertura" id="marca-abertura"></div>
  <div class="legenda-abertura">Integração SIGA x SGA</div>
  <div class="credito">Desenvolvido por <b>WS Consultoria</b></div>
</div>
<div class="app">
<div class="faixa"><span>Central de atualização · <strong>SIGA x SGA</strong></span><span>Grupo Support</span></div>
<header>
  <div id="logo"></div>
  <div class="titulo"><b>Integração SIGA x SGA</b></div>
</header>
<nav class="abas" role="tablist">
  <button type="button" role="tab" class="aba ativa" data-aba="atualizacao" aria-selected="true">Atualização</button>
  <button type="button" role="tab" class="aba" data-aba="resultados" aria-selected="false">Resultados <span class="selo" id="selo-novo" hidden>novo</span></button>
</nav>
<main>
  <form id="form" autocomplete="off">
    <section class="cartao">
      <h2>Conexão com o SIGA</h2>
      <label class="campo" for="usuario">Login</label>
      <input type="text" id="usuario" spellcheck="false">
      <label class="campo" for="senha">Senha</label>
      <input type="password" id="senha">
      <label class="lembrar"><input type="checkbox" id="lembrar"> Lembrar login e senha neste computador</label>
    </section>
    <section class="cartao">
      <h2>Salvar resultados em</h2>
      <div class="pasta"><div class="caminho" id="destino" title=""></div>
        <button type="button" id="escolher">Escolher pasta…</button></div>
      <p class="dica">As planilhas Excel e os painéis HTML (BI) são gravados nesta pasta ao final.</p>
      <div class="botoes">
        <button type="submit" class="prim" id="conectar">Conectar e atualizar</button>
        <button type="button" id="cancelar" hidden>Cancelar</button>
        <button type="button" class="btn-verde" id="ver-resultados" hidden>Ver resultados</button>
        <button type="button" id="resultados" hidden>Abrir pasta</button>
      </div>
      <div class="msg" id="msg"></div>
    </section>
    <section class="cartao" id="andamento">
      <h2>Andamento</h2>
      <div class="linha-status">
        <span class="status-esq"><span class="arcos girando" id="arcos-status"></span><span id="status">Pronto para conectar</span></span>
        <span id="pct">0%</span>
      </div>
      <div id="detalhe"></div>
      <div class="trilho"><div class="barra" id="barra"></div></div>
      <div class="tempo" id="tempo"></div>
      <figure class="previa" id="previa" hidden>
        <figcaption><span class="ao-vivo" id="previa-rotulo">Ao vivo</span>
          <span>Navegador do robô (oculto)</span></figcaption>
        <img id="previa-img" alt="O que o navegador oculto está mostrando agora">
      </figure>
      <details id="det"><summary>Detalhes</summary>
        <ol class="etapas" id="etapas"></ol>
        <p class="vazio" id="sem-etapas">As etapas aparecem aqui quando a atualização começar.</p>
        <details class="tecnico"><summary>Registro técnico</summary><pre id="log"></pre></details>
      </details>
    </section>
  </form>

  <div id="aba-resultados" hidden>
    <section class="cartao">
      <h2>Painéis</h2>
      <div class="seletor" id="seletor-paineis" role="tablist"></div>
      <div class="barra-painel">
        <span id="painel-atualizado"></span>
        <button type="button" class="btn-verde" id="abrir-painel">Abrir no navegador</button>
      </div>
      <div class="visor">
        <iframe id="visor" title="Painel" sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-forms"></iframe>
        <p class="visor-vazio" id="visor-vazio" hidden>Os painéis aparecem aqui depois da primeira atualização.</p>
      </div>
    </section>
    <section class="cartao">
      <h2>Planilhas no Google</h2>
      <div class="planilhas" id="planilhas"></div>
      <p class="dica" id="dica-chrome">Painéis e planilhas abrem no Google Chrome.</p>
    </section>
  </div>
</main>
</div>
<script>
const T = new URLSearchParams(location.search).get('t');
const $ = id => document.getElementById(id);
let linhas = 0, inicio = null, senhaSalva = false, primeiro = true, rodandoAntes = false;

$('favicon').href = '/icone?t=' + T;

// Abertura. O símbolo da logo são dois arcos (x < 525 px na logo de 1804 px); cada arco é recortado
// da própria logo oficial e gira como uma roda em volta do centro do símbolo (239, 227).
const CORTE_SIMBOLO = 525;
function separarArcos(img) {
  const W = CORTE_SIMBOLO, H = img.naturalHeight;
  const base = document.createElement('canvas'); base.width = W; base.height = H;
  const ctx = base.getContext('2d'); ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, W, H), d = px.data;
  // Rotula as partes sólidas (alfa >= 100); as duas maiores são os arcos.
  const rot = new Int32Array(W * H), tam = [0];
  for (let p = 0; p < W * H; p++) {
    if (rot[p] || d[p * 4 + 3] < 100) continue;
    const id = tam.length; let n = 0; const pilha = [p]; rot[p] = id;
    while (pilha.length) {
      const q = pilha.pop(); n++; const x = q % W, y = (q / W) | 0;
      for (const r of [x > 0 ? q - 1 : -1, x < W - 1 ? q + 1 : -1, y > 0 ? q - W : -1, y < H - 1 ? q + W : -1])
        if (r >= 0 && !rot[r] && d[r * 4 + 3] >= 100) { rot[r] = id; pilha.push(r); }
    }
    tam.push(n);
  }
  const [a, b] = tam.map((n, id) => [n, id]).slice(1).sort((x, y) => y[0] - x[0]).slice(0, 2).map(v => v[1]);
  if (!b) return null;
  // Bordas suavizadas (alfa baixo) ficam com o arco mais próximo: expansão em largura.
  let fila = []; for (let p = 0; p < W * H; p++) if (rot[p] === a || rot[p] === b) fila.push(p); else rot[p] = 0;
  while (fila.length) {
    const prox = [];
    for (const q of fila) {
      const x = q % W, y = (q / W) | 0;
      for (const r of [x > 0 ? q - 1 : -1, x < W - 1 ? q + 1 : -1, y > 0 ? q - W : -1, y < H - 1 ? q + W : -1])
        if (r >= 0 && !rot[r] && d[r * 4 + 3] > 0) { rot[r] = rot[q]; prox.push(r); }
    }
    fila = prox;
  }
  return [a, b].map((id, i) => {
    const c = document.createElement('canvas'); c.width = W; c.height = H; c.className = i ? 'arco-b' : 'arco-a';
    const img2 = c.getContext('2d').createImageData(W, H);
    for (let p = 0; p < W * H; p++) if (rot[p] === id) for (let k = 0; k < 4; k++) img2.data[p * 4 + k] = d[p * 4 + k];
    c.getContext('2d').putImageData(img2, 0, 0);
    return c;
  });
}
function fumaca() {
  const cores = ['rgba(169,201,39,.35)', 'rgba(77,77,77,.18)', 'rgba(25,192,6,.25)', 'rgba(140,137,138,.22)'];
  for (let i = 0; i < 9; i++) {
    const f = document.createElement('div'); f.className = 'fumaca';
    const ang = Math.random() * Math.PI * 2, dist = 90 + Math.random() * 160;
    f.style.setProperty('--dx', Math.cos(ang) * dist + 'px'); f.style.setProperty('--dy', Math.sin(ang) * dist * .7 - 40 + 'px');
    f.style.background = `radial-gradient(circle, ${cores[i % cores.length]} 0%, transparent 70%)`;
    f.style.animationDelay = (i * .12) + 's';
    $('abertura').prepend(f);
  }
}
let aberturaFeita = false;
function terminarAbertura() {
  if (aberturaFeita) return; aberturaFeita = true;
  document.body.classList.add('pronto');
  $('abertura').classList.add('saindo');
  setTimeout(() => $('abertura').remove(), 900);
  setTimeout(() => (($('usuario').value ? $('senha') : $('usuario'))).focus(), 50);
}
$('abertura').addEventListener('click', terminarAbertura);

// Os mesmos dois arcos giram no topo e ao lado do status enquanto a atualização roda.
let ARCOS = [];
function clonarArco(c) {
  const n = document.createElement('canvas'); n.width = c.width; n.height = c.height; n.className = c.className;
  n.getContext('2d').drawImage(c, 0, 0); return n;
}
function miniArcos() {
  const s = document.createElement('span'); s.className = 'arcos girando';
  s.append(...ARCOS.map(clonarArco)); return s;
}
function girar(cont, sim) {
  if (!cont || cont.classList.contains('girando') === sim) return;
  if (sim) { cont.classList.add('girando'); return; }
  // Para devagar, como roda: do ângulo atual até completar a volta (posição da logo).
  for (const c of cont.querySelectorAll('canvas')) {
    let ang = 0;
    try { const m = new DOMMatrix(getComputedStyle(c).transform); ang = (Math.atan2(m.b, m.a) * 180 / Math.PI + 360) % 360; } catch {}
    c.style.animation = 'none'; c.style.transform = `rotate(${ang}deg)`;
    c.getBoundingClientRect();
    c.style.transition = 'transform 1.3s cubic-bezier(.15,.75,.25,1)'; c.style.transform = 'rotate(360deg)';
    setTimeout(() => { c.style.transition = 'none'; c.style.transform = ''; c.style.animation = ''; }, 1350);
  }
  cont.classList.remove('girando');
}

(() => {  // logo oficial; sem o arquivo, o nome em texto (como no painel)
  const img = new Image(); img.alt = 'Grupo Support';
  img.onload = () => {
    let arcos = null; try { arcos = separarArcos(img); } catch { /* sem recorte: gira o símbolo inteiro */ }
    if (!arcos) { const c = document.createElement('canvas'); c.width = CORTE_SIMBOLO; c.height = img.naturalHeight;
                  c.getContext('2d').drawImage(img, 0, 0); c.className = 'arco-a'; arcos = [c]; }
    ARCOS = arcos;
    const texto = () => { const t = img.cloneNode(); t.className = 'texto-logo'; return t; };
    const topo = document.createElement('div'); topo.className = 'marca'; topo.id = 'marca-topo';
    topo.append(texto(), ...arcos.map(clonarArco));
    $('logo').replaceChildren(topo);
    $('arcos-status').replaceChildren(...arcos.map(clonarArco));
    $('marca-abertura').append(texto(), ...arcos);
    fumaca();
    setTimeout(terminarAbertura, 3300);
  };
  img.onerror = () => { $('logo').innerHTML = '<div class="logo-texto"><small>GRUPO</small>SUPPORT</div>'; terminarAbertura(); };
  img.src = '/logo?t=' + T;
})();

// Resultados (aba própria): o painel abre dentro da tela e também no navegador (Chrome).
const ICONE_PLANILHA = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="1.5" width="13" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M1.5 6h13M1.5 10.5h13M6 6v8.5" stroke="currentColor" stroke-width="1.4"/></svg>';
function el(tag, attrs, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
  n.append(...filhos); return n;
}
const abrir = (tipo, chave) => api('/abrir', {tipo, chave});
let painelAtual = null, RESULTADOS = null;

function mostrarPainel(chave) {
  const p = RESULTADOS && RESULTADOS.paineis.find(x => x.chave === chave && x.existe);
  painelAtual = p ? p.chave : null;
  for (const b of $('seletor-paineis').children) b.classList.toggle('ativo', b.dataset.chave === painelAtual);
  $('visor').hidden = !p; $('visor-vazio').hidden = !!p; $('abrir-painel').disabled = !p;
  $('painel-atualizado').textContent = p ? 'Arquivo em ' + p.pasta : '';  // a data dos dados aparece no próprio painel
  if (!p) return;
  const src = `/painel?t=${T}&n=${p.chave}&v=${p.versao}`;
  if ($('visor').getAttribute('src') !== src) $('visor').setAttribute('src', src);
}
$('abrir-painel').addEventListener('click', () => painelAtual && abrir('painel', painelAtual));

function mostrarResultados(r) {
  RESULTADOS = r;
  $('dica-chrome').textContent = r.chrome ? 'Painéis e planilhas abrem no Google Chrome.'
                                          : 'Chrome não encontrado: abrem no navegador padrão.';
  $('seletor-paineis').replaceChildren(...r.paineis.map(p =>
    el('button', {type:'button', 'data-chave':p.chave, ...(p.existe ? {} : {disabled:'', title:'Ainda não gerado'}),
                  onclick:() => mostrarPainel(p.chave)}, p.titulo)));
  const primeiro = r.paineis.find(p => p.existe);
  mostrarPainel(r.paineis.some(p => p.chave === painelAtual && p.existe) ? painelAtual : primeiro && primeiro.chave);
  $('planilhas').replaceChildren(...r.planilhas.map(p => {
    const editar = async () => {
      const link = prompt(`Cole o link da planilha "${p.titulo}" no Google Sheets:`, p.link || '');
      if (link === null) return;
      const resp = await api('/link', {chave:p.chave, link});
      if (resp.erro) alert(resp.erro); else mostrarResultados(resp);
    };
    const botao = el('button', {type:'button', class:'abrir' + (p.link ? ' btn-verde' : ' sem-link'),
                                title: p.link || 'Sem link: clique para adicionar',
                                onclick: p.link ? () => abrir('planilha', p.chave) : editar});
    botao.innerHTML = ICONE_PLANILHA; botao.append(p.link ? p.titulo : '+ Link: ' + p.titulo);
    return el('div', {class:'planilha'}, botao,
              el('button', {type:'button', class:'editar', title:'Alterar link', onclick:editar}, '✎'));
  }));
}
async function carregarResultados() {
  try { mostrarResultados(await api('/resultados_info')); } catch { /* tenta de novo ao abrir a aba */ }
}

// Abas. Em Resultados a janela alarga (os painéis são largos); ao voltar, retoma o tamanho anterior.
let tamanhoAntes = null;
function mostrarAba(nome) {
  for (const b of document.querySelectorAll('.aba')) {
    const ativa = b.dataset.aba === nome;
    b.classList.toggle('ativa', ativa); b.setAttribute('aria-selected', ativa);
  }
  $('form').hidden = nome !== 'atualizacao';
  $('aba-resultados').hidden = nome !== 'resultados';
  try {
    if (nome === 'resultados' && window.outerWidth < 1100) {
      tamanhoAntes = [window.outerWidth, window.outerHeight];
      const w = Math.min(1360, screen.availWidth), h = Math.min(960, screen.availHeight);
      window.resizeTo(w, h); window.moveTo(Math.max(0, (screen.availWidth - w) / 2), Math.max(0, (screen.availHeight - h) / 2));
    } else if (nome === 'atualizacao' && tamanhoAntes) {
      window.resizeTo(...tamanhoAntes); tamanhoAntes = null;
    }
  } catch { /* janela comum do navegador não deixa redimensionar */ }
  if (nome === 'resultados') { $('selo-novo').hidden = true; carregarResultados(); }
  scrollTo(0, 0);
}
for (const b of document.querySelectorAll('.aba')) b.addEventListener('click', () => mostrarAba(b.dataset.aba));
$('ver-resultados').addEventListener('click', () => mostrarAba('resultados'));
carregarResultados();

// Visão ao vivo: pede um quadro novo por vez (só quando o anterior terminou de carregar).
let previaCarregando = false, previaFinal = false;
$('previa-img').addEventListener('load', () => { previaCarregando = false; });
$('previa-img').addEventListener('error', () => { previaCarregando = false; });
function mostrarPrevia(e) {
  $('previa').hidden = !e.previa;
  if (!e.previa) { previaFinal = false; return; }
  const rotulo = $('previa-rotulo');
  rotulo.textContent = e.rodando ? 'Ao vivo' : 'Última imagem';
  rotulo.classList.toggle('parado', !e.rodando);
  if (e.rodando) previaFinal = false;
  if (previaCarregando || previaFinal) return;
  previaCarregando = true;
  if (!e.rodando) previaFinal = true;  // depois de terminar, busca só a última imagem
  $('previa-img').src = '/previa?t=' + T + '&n=' + Date.now();
}

function duracao(s) {
  s = Math.max(0, Math.round(s));
  return s < 60 ? s + ' s' : Math.floor(s / 60) + ' min ' + String(s % 60).padStart(2, '0') + ' s';
}
// Atualiza a lista de etapas no lugar (sem recriar), para os arcos da etapa atual não reiniciarem.
function mostrarEtapas(e) {
  const ol = $('etapas');
  $('sem-etapas').hidden = e.etapas.length > 0;
  while (ol.children.length > e.etapas.length) ol.lastChild.remove();
  e.etapas.forEach((et, i) => {
    let li = ol.children[i];
    if (!li) {
      li = document.createElement('li');
      li.innerHTML = '<span class="ic"></span><span class="msg-etapa"></span><span class="dur"></span><span class="sub"></span>';
      ol.append(li);
    }
    const ultima = i === e.etapas.length - 1;
    const estado = ultima && e.rodando ? 'atual' : ultima && e.fim && e.fim.tipo !== 'ok' ? 'erro' : 'feita';
    if (li.dataset.estado !== estado) {
      li.dataset.estado = estado; li.className = estado === 'atual' ? 'atual' : '';
      const ic = li.querySelector('.ic'); ic.className = 'ic' + (estado === 'erro' ? ' erro' : '');
      if (estado === 'atual') ic.replaceChildren(miniArcos()); else ic.textContent = estado === 'erro' ? '✕' : '✓';
      const msg = li.querySelector('.msg-etapa');
      msg.classList.toggle('pontos', estado === 'atual');
    }
    li.querySelector('.msg-etapa').textContent = et.msg + (estado === 'atual' ? ' — carregando' : '');
    li.querySelector('.sub').textContent = et.detalhe || '';
    li.querySelector('.dur').textContent = duracao((et.fim || e.agora) - et.inicio);
  });
}

async function api(rota, corpo) {
  const r = await fetch(rota + '?t=' + T + (corpo === undefined ? '&desde=' + linhas : ''),
    corpo === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(corpo)});
  return r.json();
}
function bloquear(sim) {
  for (const id of ['usuario','senha','lembrar','conectar','escolher']) $(id).disabled = sim;
  $('cancelar').hidden = !sim;
}
function mensagem(texto, tipo) { $('msg').textContent = texto || ''; $('msg').className = 'msg ' + (tipo || ''); }
function mostrarDestino(p) { $('destino').textContent = p; $('destino').title = p; }

$('form').addEventListener('submit', async ev => {
  ev.preventDefault();
  const usuario = $('usuario').value.trim(), senha = $('senha').value;
  if (!usuario) { mensagem('Informe o login.', 'erro'); $('usuario').focus(); return; }
  if (!senha && !senhaSalva) { mensagem('Informe a senha.', 'erro'); $('senha').focus(); return; }
  mensagem(''); $('resultados').hidden = true; $('ver-resultados').hidden = true; $('log').textContent = ''; linhas = 0;
  const r = await api('/conectar', {usuario, senha, lembrar:$('lembrar').checked, destino:$('destino').title});
  if (r.erro) { mensagem(r.erro, 'erro'); return; }
  inicio = Date.now(); bloquear(true);
});
$('escolher').addEventListener('click', async () => {
  $('escolher').disabled = true;
  try { const r = await api('/escolher_pasta', {}); if (r.destino) mostrarDestino(r.destino); }
  finally { $('escolher').disabled = false; }
});
$('lembrar').addEventListener('change', () => api('/lembrar', {lembrar:$('lembrar').checked}));
$('cancelar').addEventListener('click', () => { if (confirm('Cancelar a atualização em andamento?')) api('/cancelar', {}); });
$('resultados').addEventListener('click', () => api('/resultados', {}));

async function atualizar() {
  let e;
  try { e = await api('/estado'); } catch { setTimeout(atualizar, 1500); return; }
  if (primeiro) {
    primeiro = false;
    $('lembrar').checked = e.lembrar;
    $('usuario').value = e.usuario;
    senhaSalva = e.senha_salva;
    $('senha').placeholder = senhaSalva ? '•••••••• (senha salva)' : '';
    mostrarDestino(e.destino);
    (e.usuario ? $('senha') : $('usuario')).focus();
  }
  if (e.linhas.length) {
    const pre = $('log'), noFim = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 5;
    pre.textContent += e.linhas.join('\n') + '\n'; linhas = e.total_linhas;
    if (noFim) pre.scrollTop = pre.scrollHeight;
  }
  $('status').textContent = e.status;
  $('pct').textContent = e.pct + '%';
  $('andamento').classList.toggle('rodando', e.rodando);
  girar($('marca-topo'), e.rodando);
  $('detalhe').textContent = e.rodando ? (e.detalhe || 'carregando') : '';
  $('detalhe').classList.toggle('pontos', e.rodando);
  mostrarEtapas(e);
  mostrarPrevia(e);
  const barra = $('barra');
  barra.style.width = e.pct + '%';
  barra.className = 'barra' + (e.rodando ? ' ativa' : e.fim ? (e.fim.tipo === 'ok' ? ' ok' : ' erro') : '');
  if (e.rodando) {
    bloquear(true);
    if (!inicio) inicio = Date.now();
    const s = Math.round((Date.now() - inicio) / 1000);
    $('tempo').textContent = 'Tempo: ' + Math.floor(s / 60) + ' min ' + String(s % 60).padStart(2, '0') + ' s';
  } else if (rodandoAntes && e.fim) {
    bloquear(false); inicio = null;
    mensagem(e.fim.msg, e.fim.tipo === 'ok' ? 'ok' : 'erro');
    if (e.fim.tipo === 'ok') {
      $('resultados').hidden = false; $('ver-resultados').hidden = false;
      $('selo-novo').hidden = false; carregarResultados();
    }
    if (e.fim.tipo === 'login') {
      senhaSalva = false; $('senha').placeholder = ''; $('senha').value = ''; $('senha').focus();
    }
    if (e.fim.tipo === 'erro') $('det').open = true;
  }
  rodandoAntes = e.rodando;
  setTimeout(atualizar, 700);
}
// Fechar a janela no meio cancela a atualização: pede confirmação.
window.addEventListener('beforeunload', ev => { if (rodandoAntes) { ev.preventDefault(); ev.returnValue = ''; } });
atualizar();
</script></body></html>"""


if __name__ == '__main__':
    main()
