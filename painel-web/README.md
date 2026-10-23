# Painéis do Grupo Support na Vercel

Site que recebe e mostra online os dois painéis do **Integrador SIGA × SGA**:

- **Conferência de finalizados** → `/finalizados`
- **Acompanhamento dos analistas** → `/acompanhamento`

A automação (login no SIGA, download, planilhas) **continua rodando no computador**,
no instalável de sempre. Este site só **recebe o HTML pronto** que a ferramenta
gera e o deixa acessível pela internet, protegido por senha.

```
   Ferramenta no PC  ──(upload do HTML)──►  Site na Vercel  ──(login)──►  Equipe
   (gera os painéis)                        (guarda e mostra)
```

> ⚠️ **Dados internos.** Os painéis contêm dados de associados. O site nasce
> protegido por usuário e senha (HTTP Basic Auth) e manda não guardar em cache.
> Não divulgue o endereço nem a senha.

---

## Como funciona

- As funções em `api/` rodam como *serverless functions* na Vercel (não há build).
- O HTML enviado é guardado no **Vercel Blob** com acesso **privado** (um arquivo
  por painel, sempre sobrescrito pelo mais recente). O conteúdo nunca fica numa
  URL pública: só o próprio site, com o token do Blob, consegue lê-lo de volta.
- `/`, `/finalizados` e `/acompanhamento` pedem login antes de mostrar qualquer coisa.
- `POST /api/upload?painel=...` recebe o HTML (usado só pela ferramenta local).

---

## Passo a passo para publicar

### 1. Enviar o projeto para a Vercel

Tem duas formas. Escolha **uma**.

**A) Pelo site da Vercel (sem instalar nada):** crie um repositório no GitHub só
com esta pasta `painel-web`, em <https://vercel.com/new> clique *Import* e selecione o repositório.

**B) Pela linha de comando** (dentro da pasta `painel-web`):

```bash
npm i -g vercel
vercel
```

Em *Framework Preset* deixe **Other**. Não há comando de build.

### 2. Criar o armazenamento (Blob)

No projeto, aba **Storage → Create Database → Blob → Create**. Isso cria
automaticamente a variável `BLOB_READ_WRITE_TOKEN` no projeto. Não precisa copiar nada.

### 3. Definir as variáveis de ambiente

Em **Settings → Environment Variables**, adicione (veja `.env.example`):

| Variável        | Para que serve                                                        |
|-----------------|-----------------------------------------------------------------------|
| `UPLOAD_SECRET` | senha que a ferramenta usa para **enviar** os painéis (invente um texto longo) |
| `VIEW_USER`     | usuário para **abrir** os painéis (ex.: `support`)                    |
| `VIEW_PASSWORD` | senha para **abrir** os painéis                                       |

`BLOB_READ_WRITE_TOKEN` já foi criada no passo 2.

### 4. Redeploy

Depois de criar o Blob e as variáveis, faça um **Redeploy** (aba Deployments → ⋯ →
Redeploy) para que o site passe a enxergá-las.

### 5. Ligar a ferramenta ao site

No computador, em `sistema\configuracao.env` do Integrador, preencha:

```
VERCEL_SITE_URL=https://SEU-PROJETO.vercel.app
VERCEL_UPLOAD_SECRET=<o mesmo UPLOAD_SECRET do passo 3>
```

### 6. Pronto — o envio é automático

Com `VERCEL_SITE_URL` e `VERCEL_UPLOAD_SECRET` preenchidos, **toda atualização**
passa a enviar os painéis para o site no final (a barra mostra "Enviando os
painéis para o site"). Abra o endereço do site, faça login e veja os painéis.

> Se o envio falhar (internet fora, por exemplo), a atualização local **não**
> é prejudicada: os arquivos continuam salvos normalmente e aparece só um aviso.

Para enviar **na hora**, sem rodar uma atualização, dê dois cliques em
**`Enviar paineis para o site.bat`** (na pasta `grupo support`). Para enviar só um:

```bash
Enviar paineis para o site.bat finalizados
Enviar paineis para o site.bat acompanhamento
```

---

## Testar na sua máquina (opcional)

```bash
npm install
cp .env.example .env    # preencha UPLOAD_SECRET, VIEW_USER, VIEW_PASSWORD e BLOB_READ_WRITE_TOKEN
vercel dev
```

Envie um painel de teste apontando `VERCEL_SITE_URL=http://localhost:3000`.

---

## Reforçar a privacidade (opcional)

- **Vercel Deployment Protection** (Settings → Deployment Protection): exige login
  da Vercel/SSO antes mesmo de chegar ao site. Ótima camada extra em planos pagos.
- Trocar `VIEW_PASSWORD` de tempos em tempos.
- Se um endereço vazar, apague o projeto/Blob e recrie — os dados ficam só no Blob.
