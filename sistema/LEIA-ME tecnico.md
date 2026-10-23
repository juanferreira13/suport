# Rotina do sinistro (SGA x SIGA) — documentação técnica

Este arquivo é para quem instala e mantém o sistema. O guia do usuário é o `LEIA-ME.txt` da pasta
principal.

## Estrutura das pastas

```
<pasta do projeto>\
  Abrir painel.bat          abre RESULTADOS\CONFERENCIA FINALIZADOS.html
  Abrir acompanhamento.bat  abre RESULTADOS\ACOMPANHAMENTO ANALISTAS.html
  Atualizar agora.bat       roda a rotina completa
  LEIA-ME.txt               guia do usuário
  ENTRADA\                  arquivos exportados do SIGA e do SGA e os salvos pela página de acompanhamento
                            (lidos e movidos para processados\)
  RESULTADOS\               planilhas e páginas
  sistema\                  (oculta) tudo o que faz o sistema rodar
    app\                    código: pacote sinistro\ e os scripts
    python\                 Python 3.14 com openpyxl, para rodar sem instalar nada
    configuracao.env        credenciais do SGA e caminhos
    dados\                  bases guardadas entre as execuções, anotações das equipes (manuais.json)
                            e histórico do acompanhamento (acompanhamento.json)
    logs\                   um arquivo por mês
    backups\                versão anterior de cada planilha (as últimas 7 de cada)
    ferramentas\            configurar, testar o acesso ao SGA, agendar, mostrar/ocultar a pasta
    rodar.bat               roda um script de app\ com o Python da pasta
```

A pasta `sistema` tem o atributo "oculto". Para vê-la, digite `sistema` na barra de endereço do
Explorador de Arquivos, ative Exibir > Itens ocultos, ou rode `ferramentas\Mostrar pasta sistema.bat`.

## Instalar em outro computador

1. Copie a pasta do projeto inteira (com a `sistema`). Não precisa instalar Python: o da pasta
   `sistema\python` é usado. Requer Windows 10 ou 11 de 64 bits.
2. Em `sistema\ferramentas`, rode `Agendar atualizacao diaria.bat` para criar a tarefa das 8h. A
   tarefa aponta para o caminho da pasta: se a pasta mudar de lugar, rode de novo.
3. No computador antigo, rode `Remover agendamento.bat`.

Os caminhos em `configuracao.env` são relativos à pasta do projeto, então nada precisa ser ajustado.
As linhas `PLANILHA_BASE...` apontam para as planilhas originais do Google; só são lidas quando uma
planilha de RESULTADOS precisa ser criada do zero e podem ficar apontando para arquivos que não existem.

## Configurar o acesso ao SGA

1. `ferramentas\Configurar.bat` abre o `configuracao.env`. Preencha `SGA_TOKEN`, `SGA_USUARIO` e
   `SGA_SENHA`. O token é gerado no SGA em **Área Cliente > APIs > Gerenciar APIs > Novo**
   (Interveniente: Associação; Permitir Acesso: SIM; libere "Autenticar Usuário", "Evento - Listar"
   e "Evento - Listar Classificação").
2. `ferramentas\Testar acesso ao SGA.bat` mostra os campos que a API devolve e compara com o
   relatório já importado, sem gravar nada.

## SIGA (Arco Consultoria): sem API

Verificado em 14/10/2026: o SIGA não tem API pública. O site da Arco e a página do produto não citam
API, webservice nem documentação para desenvolvedores; o único acesso é a tela de login
(`siga.arcoconsultoria.com/SIGA/open.do?action=open&sys=SIG`). O sistema é feito na plataforma
Webrun (Softwell Maker), que só expõe dados por serviço se o fornecedor criar um. A integração
SIGA → SGA que a Arco anuncia é o SIGA lendo o SGA, não o contrário.

Por isso os eventos do SIGA entram pela exportação do DashBoard, salva em `ENTRADA\`:
RELATÓRIOS > Dashboard Arco > Gerencial > (GRUPO SUPPORT, ano, mês) > gráfico "Total Eventos
Cadastrados" > barra Total > Excel. Um arquivo por ano; vários podem ser salvos de uma vez.

`SIGA_ANO_INICIAL` (padrão 2021) define desde quando os anos devem vir. A cada execução o log
lista os anos já trazidos (com a data) e avisa os que faltam. O registro fica em `anos` dentro de
`dados\integracao.json`.

Se a Arco disponibilizar uma API ou uma exportação agendada, a leitura entra em
`app\sinistro\siga.py` (`linhas_de_tabela` já converte as colunas do DashBoard).

## Registro de exportações

`RESULTADOS\REGISTRO DE EXPORTACOES.txt` (caminho em `REGISTRO_EXPORTACOES`) ganha uma linha para
cada dado que entra: data e hora, forma, sistema, conteúdo, quantidade de eventos, situação e arquivo.

| Forma | Origem |
|---|---|
| MANUAL | arquivo salvo por uma pessoa na pasta `ENTRADA\` (DashBoard SIGA, relatório do SGA) |
| AUTOMÁTICO | consulta feita pela rotina (API do SGA), inclusive quando falha |

Arquivos que não são nem DashBoard nem relatório do SGA vão para `ENTRADA\nao reconhecidos\` e
aparecem no registro como IGNORADO.

## O que a rotina faz

`Atualizar agora.bat` (e a tarefa agendada) roda `app\executar.py`:

0. **Pastas extras** — antes de ler a `ENTRADA`, se `PASTAS_ENTRADA_EXTRA` estiver preenchida, copia para a
   `ENTRADA` os relatórios do SIGA/SGA (`.xls`/`.xlsx`) que aparecerem nessas pastas (ex.: a pasta de saída de
   uma exportação automática). Os originais não são tocados; cada arquivo é copiado uma só vez, controlado por
   `dados\pastas_extra.json` (impressão digital = caminho + tamanho + data de modificação). Assim a equipe só
   exporta, sem precisar mover o arquivo para a `ENTRADA`.
1. **SGA** — lê o relatório de eventos que estiver em `ENTRADA\` e consulta a API do SGA.
2. **INTEGRAÇÃO** — incorpora o DashBoard SIGA que estiver em `ENTRADA\` (atualiza pelo número do
   evento, acrescenta os novos, mantém o histórico).
3. **Cruzamentos** — calcula o que as fórmulas da planilha do Google faziam e grava
   `GERENCIAL SINISTRO.xlsx` (abas SGA e INTEGRAÇÃO inteiras; colunas verdes da aba SIGA).
4. **Setores** — incorpora os arquivos salvos pela página de acompanhamento, regrava ANALISTAS,
   CONSULTORES TECNICOS e REGULADORES a partir da aba SIGA e refaz `ACOMPANHAMENTO ANALISTAS.html`.
5. **Painel** — regrava `CONFERENCIA FINALIZADOS.html`.

Para rodar uma etapa só, pelo Prompt de Comando na pasta `sistema`:

| Comando | O que faz |
|---|---|
| `rodar.bat executar.py` | rotina completa |
| `rodar.bat executar.py --sem-api` | rotina completa sem consultar a API do SGA |
| `rodar.bat atualizar_sga.py` | só a aba SGA |
| `rodar.bat gerar_integracao.py` | só a integração |
| `rodar.bat gerar_setores.py` | só as planilhas dos setores |
| `rodar.bat gerar_painel.py` | só o painel |
| `rodar.bat atualizar_sga.py --diagnostico` | testa a API sem gravar nada |

## Planilha GERENCIAL SINISTRO

| Aba | Quem preenche | O que tem |
|---|---|---|
| SGA | script | eventos do SGA + NOME, PLACA, COMPETENCIA, STATUS SIGA e chave |
| INTEGRAÇÃO | script | histórico do DashBoard SIGA + PROTOCOLO, PLACA 2, COMPETENCIA e chave |
| SIGA | equipe (colunas B a W) | o script preenche as colunas verdes (A e X em diante) |
| TAREFAS | equipe | tabela tarefa → setor (define SETOR e POR TAREFA) |

Os cruzamentos são gravados como **valores**. As fórmulas da planilha do Google (PROCX sobre
colunas inteiras) levam cerca de 1,5 s por célula no Excel. Ficam como fórmula apenas DIAS UTEIS
COMUNICADO, DIAS UTEIS AUTORIZADO, SETOR e POR TAREFA; um valor digitado por cima de uma delas não
é desfeito.

O script reescreve somente as abas SGA e INTEGRAÇÃO e as colunas verdes da aba SIGA. Tudo o mais
fica como está: o que foi digitado, cores, filtros da aba SIGA, abas novas, tabelas dinâmicas e
gráficos. Dois cuidados: não digitar nas abas SGA e INTEGRAÇÃO, e não transformá-las em "Tabela"
do Excel (Ctrl+T), porque o intervalo da tabela não acompanha o número de linhas.

## Limitação da API do SGA

A API oficial (`listar/evento`) devolve 14 das 28 colunas do relatório: protocolo, tipo, motivo,
nome do associado, placa, cidade, estado, data do comunicado, situação, voluntário, cooperativa,
classificação, data do evento e participação.

**Não vêm pela API:** nome e placa do terceiro, analista responsável, vistoriador, fornecedor,
contato (oficina), CNPJ e as sete datas de processo.

Por isso a rotina combina as duas fontes: o relatório exportado (11.9.1 por Eventos, layout
RELATORIO SINISTRO, Data Comunicado desde 01/01/2020) é a base completa, e a API acrescenta os
eventos novos e atualiza as colunas que ela fornece. Nos eventos que entraram só pela API, as
colunas acima ficam em branco até o próximo relatório ser colocado em `ENTRADA\`.

## Planilhas dos setores

| Planilha | Aba | Quais linhas da aba SIGA | Colunas próprias |
|---|---|---|---|
| ANALISTAS | ANALISTAS | POR TAREFA = ANALISTAS, exceto VIDROS | PARTICIPAÇÃO, **OBSERVAÇÃO** |
| | VIDROS | Evento = VIDROS e SETOR diferente de FINANCEIRO | PARTICIPAÇÃO, **OBSERVAÇÃO** |
| | OFICINAS | cópia da tabela Oficinas dos consultores | |
| CONSULTORES TECNICOS | CONSULTORES TEC. | POR TAREFA = CONSULTORES, exceto VIDROS | CONSULTOR TECNICO, **OBSERVAÇÃO** |
| | Oficinas | tabela digitada pela equipe | CNPJ LIMPO, QUANTIDADE e VAGAS DISPONIVEIS são calculadas |
| | Oficinas por Consultor | oficinas com veículos, por consultor | |
| REGULADORES | REGULADORES | SETOR = REGULADORES, exceto VIDROS | **REGULARIZADO POR** |
| | VISTORIA INICIAL | todas, exceto VIDROS | DATA DA REGULAGEM, MES REFERENCIA |
| | NEGADOS EM ABERTO | STATUS SGA = NEGADO e STATUS SIGA diferente de NEGADO | |
| | NEGADOS FINALIZADOS | eventos do SIGA liberados no ano, com a situação no SGA | |
| | BASE VISTORIA INICIAL | digitada pela equipe (número, regulador, data da análise) | |
| | HISTÓRICO REGULARIZAÇÕES | uma linha para cada REGULARIZADO POR preenchido | |

### Página de acompanhamento dos analistas

`RESULTADOS\ACOMPANHAMENTO ANALISTAS.html` (chave `PAGINA_ACOMPANHAMENTO`) lista os processos das
abas ANALISTAS e VIDROS, com indicadores (a preencher, atrasados, em dia, concluídos), tabelas por
situação e por analista, as últimas alterações e, para cada processo, os campos ANALISTA (em branco =
responsável no SIGA), SITUAÇÃO, PRÓXIMA AÇÃO, PRAZO e OBSERVAÇÃO. É um arquivo, sem servidor:

1. O que o analista muda fica no navegador (localStorage), marcado "não salvo".
2. "Salvar alterações" grava `ACOMPANHAMENTO ANALISTAS - <nome> - <data>.json` (no Edge/Chrome, na pasta
   escolhida, lembrada para a próxima vez; nos outros navegadores, em Downloads). O arquivo tem
   `"tipo": "acompanhamento-analistas"`, um `id` e cada alteração com protocolo, campo, valor e hora.
3. Na atualização seguinte, `acompanhamento.aplicar` lê esses arquivos da `ENTRADA` e da pasta
   Downloads do usuário (`PASTA_DOWNLOADS`; padrão: a Downloads do Windows; em branco: não olha),
   aplica as alterações em ordem de hora (a mais recente prevalece), ignora valores inválidos
   (situação fora da lista, prazo que não é data), registra cada arquivo no REGISTRO DE EXPORTAÇÕES
   (MANUAL, PÁGINA) e o move para `ENTRADA\processados`. Um arquivo já incorporado (mesmo `id`) não é
   aplicado de novo.
4. A página é refeita com tudo. O que o navegador tinha como "salvo" some quando o `id` do arquivo
   aparece na página nova; se a página foi refeita depois do salvamento e o arquivo não entrou, as
   alterações voltam para "não salvo" com um aviso.

Os valores ficam em `dados\manuais.json` (grupos `ACOMPANHAMENTO/...`, por PROTOCOLO SIGA), com
ATUALIZADO EM / ATUALIZADO POR. O histórico de alterações e os `id` já incorporados ficam em
`dados\acompanhamento.json`. A OBSERVAÇÃO é a mesma da coluna OBSERVAÇÃO das abas ANALISTAS e VIDROS:
editar na planilha também vale (aparece no histórico como "planilha ANALISTAS"). Para saber o que foi
editado na planilha, o sistema compara com o que ele mesmo gravou nela da última vez
(`dados\manuais_gravados.json`), e não com o valor guardado, que pode ter mudado pela página.

As situações são fixas em `acompanhamento.py` (`SITUACOES`); "Concluído" encerra o processo no painel.

As colunas em negrito (título azul) são da equipe. O que for digitado nelas é guardado por processo
em `dados\manuais.json` e volta para a linha certa a cada atualização. Em REGULADORES a anotação
vale para o processo naquela tarefa; quando a tarefa muda, a coluna volta a ficar em branco e o
registro permanece no HISTÓRICO, com a data e hora da execução que encontrou a anotação.

As abas de título verde são regravadas inteiras: ordenações e filtros aplicados nelas são desfeitos
a cada execução. Não são criadas abas com a data do dia; a versão anterior fica em `backups\`.

## Painel da conferência de finalizados

`RESULTADOS\CONFERENCIA FINALIZADOS.html` mostra os eventos do SIGA liberados desde
`PAINEL_FINALIZADOS_DESDE` (padrão 01/01/2025), com o status de cada um no SGA, e calcula as
anotações da conferência:

| Anotação | Quando aparece |
|---|---|
| Verificar arquivamento | status no SIGA = ARQUIVADO ou ARQUIVADO POR COTA |
| Por que excluir? | status no SIGA = EXCLUIR |
| Incluir motivo | negado no SIGA ou no SGA, sem classificação negativa |

O filtro e a coluna **Setor** mostram o último setor em que o processo apareceu na aba SIGA (tarefa ->
SETOR pela aba TAREFAS). Como a aba SIGA só tem processos com tarefa aberta, a cada execução o sistema
anota o setor de cada processo dela em `dados\setores_vistos.json`; o evento finalizado mantém o último
setor anotado. Eventos que saíram da aba SIGA antes desse registro existir (começou em 15/10/2026, com
as versões da aba SIGA que havia nos backups) aparecem como "sem setor registrado".

A página busca a fonte Poppins e a logo na internet. Para funcionar sem conexão, salve a logo como
`logo.png` (ou `.webp`, `.svg`, `.jpg`) na pasta `sistema`; ela passa a ir embutida no arquivo.

## Google Sheets (modo híbrido)

Com as chaves `GOOGLE_*` preenchidas em `configuracao.env`, cada planilha configurada passa a ser a de
trabalho: o sistema lê e grava nela pela API do Google Sheets, com a conta de serviço cuja chave JSON está
em `GOOGLE_CREDENCIAIS` (fica na pasta `sistema`; é uma senha, não compartilhe). O .xlsx correspondente de
RESULTADOS deixa de ser atualizado; as páginas HTML continuam sendo geradas.

Para cada planilha: compartilhe com o e-mail da conta de serviço (`...iam.gserviceaccount.com`) como
**Editor** e, nas áreas protegidas que o sistema grava (Dados > Proteger páginas e intervalos), adicione o
mesmo e-mail em Alterar permissões > Personalizado. Se faltar permissão, o log diz qual aba e área, e
nada é gravado naquela planilha.

| Planilha | O sistema grava | Fica com a equipe / com as fórmulas do Google |
|---|---|---|
| GERENCIAL SINISTRO | SGA (A:AB) e INTEGRAÇÃO (A:S) | aba SIGA (colada pela equipe), TAREFAS, colunas de fórmula (SGA AD:AH, INTEGRAÇÃO T:W), AÇÕES, demais abas |
| ANALISTAS | abas fixas ANALISTAS e VIDROS (criadas na 1ª vez) | OFICINAS, VISTORIA PRESENCIAL, cópias diárias antigas |
| CONSULTORES TECNICOS | CONSULTORES TEC. | Oficinas, Oficinas por Consultor |
| REGULADORES | REGULADORES, VISTORIA INICIAL, NEGADOS EM ABERTO, NEGADOS FINALIZADOS | REGULADORES ANALISTA, HISTÓRICO REGULARIZAÇÕES (rotina da própria planilha), gráficos |

- **Aba SIGA:** é lida do Google a cada execução. Com o **relatório de tarefas do SIGA** ("Exported data":
  1, #, Número, Data abertura, ..., Associação) salvo na pasta ENTRADA, o sistema substitui as colunas B a W
  da aba (no Google ou no .xlsx) pelo relatório mais recente, estende para baixo as fórmulas da equipe
  (A e X:AS) e usa essas tarefas nos setores. Se a gravação no Google falhar, o arquivo fica na ENTRADA para
  a próxima execução. Tarefa que não está na aba TAREFAS fica sem setor (o log lista quais).
- **Uma instalação por conjunto de planilhas:** cada cópia do sistema guarda as próprias anotações em
  `dados\`. Duas cópias gravando nas mesmas planilhas funcionam (uma vê a gravação da outra como colagem da
  equipe), mas as anotações da página de acompanhamento ficam divididas. Ao mudar de computador, rode
  `ferramentas\Remover agendamento.bat` no anterior.
- **SGA e INTEGRAÇÃO:** a cada gravação o sistema guarda uma impressão digital (hash) do que gravou
  (`dados\google.json`). Se na execução seguinte a aba estiver diferente, a equipe colou um relatório/DashBoard
  e ele vira o ponto de partida (SGA substituída; INTEGRAÇÃO atualizada evento a evento). Na primeira vez,
  ou depois de uma gravação interrompida, vale a base do sistema e do Google entra só o que falta nela.
  Depois vêm os arquivos da pasta ENTRADA e a API do SGA.
- **Fórmulas do Google:** o sistema grava valores (datas como data, textos como texto) e só estende para baixo
  as fórmulas por linha quando há mais linhas do que fórmulas. A fórmula de `INTEGRAÇÃO!W2` vai até a linha
  20000; o log avisa quando os eventos chegarem perto disso.
- **Colunas da equipe:** OBSERVAÇÃO (ANALISTAS, VIDROS, CONSULTORES TEC.) e REGULARIZADO POR são lidas antes de
  cada gravação e voltam para o processo certo, como no Excel. Na criação das abas ANALISTAS e VIDROS, as
  observações vêm da cópia diária mais recente ("16/10 ANALISTAS", "VIDROS 16/10"), que é ocultada em seguida
  (deixa de ser atualizada; para ver de novo, botão direito na barra de abas > Mostrar).
- **Dias úteis** (colunas Z e AB das abas de setor) vão como número calculado no dia da atualização.

Para voltar ao Excel, apague os links `GOOGLE_*` da configuração.

## Cuidados

- As planilhas e as páginas têm nomes e placas de associados: uso interno, não publicar.
- `dados\manuais.json` guarda as anotações das equipes. Sem ele, as observações só voltam para as
  linhas que ainda estiverem nas planilhas.
- A planilha precisa estar fechada na hora da gravação. Se estiver aberta, a rotina registra o
  erro no log, não grava aquela planilha e segue com as outras.
- Para desenvolver com outro Python, `app\requirements.txt` lista as dependências (openpyxl; google-auth e
  requests para o Google Sheets).
