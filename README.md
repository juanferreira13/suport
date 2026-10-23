# Grupo Support | Integrador SIGA × SGA — web (Vercel)

**Versão:** 2.0 · **Objetivo:** reproduzir o visual da tela instalada e alimentar a planilha *Gerencial Sinistro* no Google Sheets sem usar uma pasta Windows.

## O que esta versão efetivamente faz

- Usa o HTML/CSS **original da tela de atualização** (`atualizar_tela.py`) e a **logo original** do pacote enviado.
- Preserva as rotas existentes `GET /api/health`, `/api/sga/testar`, `/api/sga/eventos`, `/api/siga/eventos`.
- O botão **Conectar e atualizar** autentica no SGA, confirma acesso ao Google Sheets, consulta eventos **a partir de 01/01/2020 em etapas de 1–7 dias**, acrescenta/atualiza dados na aba `SGA` e registra o último dia consolidado na aba `_SUPPORT_SYNC`. O progresso é visível na tela; a execução pode ser pausada e retomada.
- Se a planilha já contém a aba `SGA` original, valida parte do cabeçalho antes de gravar; grava **somente A:AB** para **preservar AÇÕES (AC) e fórmulas (AD:AH)**. Em registros antigos, preserva campos de identidade e atualiza outros campos disponíveis pela API. Não remove registros nem abas.
- A tela Resultados permite **verificar meses do SIGA a partir de 2021**. Seus HTMLs originais são exibidos como modelos estáticos, não como BI atualizado.
- O script `scripts/atualizar_nuvem.py` pode ser executado em **GitHub Actions** para continuar o histórico e depois reprocessar eventos recentes **sem deixar seu computador ligado**.

## LIMITE IMPORTANTE — SIGA

A API do SIGA respondeu `recordTotal: 0` para setembro e outubro de 2026, mesmo com uma sessão configurada. O código original usa **Playwright, navegador autenticado e contexto do Dashboard** para extrair os relatórios anuais do SIGA, além de um relatório especial por tela.

**Não é seguro afirmar que o histórico SIGA de 2021 até hoje foi importado** nem atualizar automaticamente as abas `INTEGRAÇÃO`, `SIGA`, `TAREFAS`, setores ou os HTMLs do BI a partir de respostas vazias. Esta versão **não** executa o navegador Playwright dentro da Vercel e **não** realiza essa parte do fluxo completo do instalável. Ela fornece consulta para diagnosticar o SIGA, mas não promete a integração integral ainda. A gravação efetiva implementada é da aba `SGA`.

## Subir como atualização do seu `grupo-suport` existente

1. Abra o ZIP e envie **seu conteúdo** para a **raiz** do repositório GitHub já conectado à Vercel. Na raiz devem ficar `vercel.json`, `requirements.txt`, `core.py`, `api/`, `public/` e `sinistro/`.
2. Vercel → Project `grupo-suport` → Settings → **Environment Variables**. Mantenha as variáveis antigas que já funcionaram:
   - `INTEGRADOR_API_KEY`
   - `SGA_TOKEN`
   - `SGA_USUARIO`
   - `SGA_SENHA`
   - `SGA_API_URL` (opcional, mantenha o endpoint Hinova)
   - `SIGA_SESSION_COOKIE` (opcional; pode expirar)
3. **Adicione estas duas variáveis novas em Production:**
   - **`GOOGLE_SINISTRO`**: URL **da planilha real Gerencial Sinistro**, do tipo `https://docs.google.com/spreadsheets/d/XXXX/edit`.
   - **`GOOGLE_SERVICE_ACCOUNT_JSON`**: conteúdo integral do arquivo JSON de uma **conta de serviço** Google Cloud com Sheets API habilitada, não apenas um e-mail.
4. Compartilhe a planilha Google com o e-mail `client_email` do JSON da conta de serviço com acesso **Editor**. Nunca publique esse JSON ou uma cópia no GitHub.
5. Faça **Redeploy** na Vercel para aplicar variáveis novas. Abra `https://grupo-suport.vercel.app/`.
6. Cole a `INTEGRADOR_API_KEY` no campo **Chave do integrador** (campo visual que substitui a senha do SIGA). O login e a senha verdadeiros da Hinova ficam **somente no backend**, não entram na interface pública. Clique **Conectar e atualizar**.
7. Confirme na planilha que a aba `SGA` recebeu registros. Se houver dados anteriores, faça **uma cópia de segurança da planilha antes do primeiro teste** e valide 2 ou 3 linhas.

### Criar a conta de serviço (caso ainda não tenha)

No [Google Cloud Console](https://console.cloud.google.com/), habilite a **Google Sheets API**, crie uma conta de serviço em IAM → Contas de serviço, gere uma chave do tipo **JSON** e configure o valor do JSON em `GOOGLE_SERVICE_ACCOUNT_JSON` **apenas na Vercel**. Em seguida, compartilhe a planilha com `client_email`.

**Não existe como o sistema adivinhar a planilha ou obter permissão de gravação apenas pelo token da Hinova.** Estas credenciais Google são independentes das credenciais SGA/SIGA.

### Automação agendada (opcional)

A pasta `.github/workflows/atualizar-sga.yml` habilita uma tarefa diária GitHub Actions às **06h15 de Brasília**. Abra GitHub → repositório → **Settings → Secrets and variables → Actions → New repository secret**, e cadastre **`INTEGRADOR_API_KEY`** com o valor atual. Em Actions, execute o workflow manualmente uma vez ou aguarde o horário programado. O histórico progride de onde parou, até um máximo de 100 lotes por execução; caso chegue ao dia atual, o processo reconsulta registros recentes. Para executar manualmente, também é possível usar:

```powershell
$env:INTEGRADOR_API_KEY = Read-Host 'Chave'
$env:INTEGRADOR_URL = 'https://grupo-suport.vercel.app'
python scripts/atualizar_nuvem.py
```

Isso **não** ativa robô SIGA, apenas a atualização incremental do SGA → Google Sheets.

## Endpoints principais

- `GET /api/health`: disponível sem chave, mostra configuração (sem credenciais).
- `GET /api/sga/testar`: autenticação Hinova (com `X-API-Key`).
- `GET /api/sga/eventos?inicio=2026-10-22&fim=2026-10-22&pagina=1&limite=10`: eventos SGA.
- `GET /api/siga/eventos?ano=2026&mes=10&empresa=141`: resposta SIGA, a qual pode ser zero indevidamente.
- `GET /api/sync/status`: valida acesso à planilha e retorna último dia concluído.
- `POST /api/sync/sga/etapa` JSON `{"dias":1}`: processa e grava a próxima janela de um dia e avança checkpoint.
- `POST /api/sync/sga/recentes` JSON `{"dias":1}`: reconsulta registros do dia atual sem alterar o checkpoint histórico.

Todos os endpoints operacionais exigem cabeçalho `X-API-Key`.

## Segurança e limitações

- Não exponha credenciais SIGA/SGA, chave JSON do Google ou sua API Key no front-end/GitHub. O usuário digita a API Key ao conectar; a opção “Manter chave” usa **apenas sessionStorage** (descartada ao fechar a aba), jamais grava senha do SIGA.
- Recomendamos trocar `INTEGRADOR_API_KEY` já compartilhada na conversa antes de uso produtivo.
- A cada atualização, o backend **não** sobrepõe AÇÕES ou fórmulas existentes. Entretanto, mudanças feitas simultaneamente diretamente na mesma linha da aba SGA podem conflitar; execute só uma sincronização por vez.
- **Histórico desde 2020 não é instantâneo.** A Hinova já apresentou timeout em intervalos extensos, portanto a importação progride em lotes. Fechar a página pausa o processo web; o checkpoint no Sheets permite retomar.
- A permissão do Google Sheets e a escrita real não puderam ser verificadas sem as credenciais reais. Os testes locais cobrem formatação de datas e preservação de colunas.
- A versão web não produz automaticamente os relatórios históricos SIGA, HTMLs preenchidos ou as abas integradas que dependem do navegador Playwright do aplicativo Windows. É necessária uma migração adicional do worker SIGA para um ambiente de navegador autenticado.
