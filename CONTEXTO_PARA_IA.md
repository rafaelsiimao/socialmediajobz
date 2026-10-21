# Jobz Social Media — contexto e passagem de trabalho

Atualizado em 21/10/2026, com base no código local e nas confirmações do usuário.

## Atualização posterior — consultar antes do histórico

LinkedIn Company Page (21/10/2026): usuário relata janela do LinkedIn com
"Bummer, something went wrong" antes de retornar ao site. Esse texto genérico
não confirma a causa; falta conferir Products/Community Management API, Auth,
redirect URI e permissões aprovadas no aplicativo real. Solicitar captura de
Products sem expor Client Secret. Callback esperado:
`https://socialmedia-web.hqzarv.easypanel.host/social-accounts/callback/linkedin_company/`.

Falhas de código reproduzidas e corrigidas em testes isolados: callback de
Company dependia de `/v2/me`; removida essa dependência e os scopes pessoais
`r_basicprofile`/`w_member_social` desse provider. Mantém
`w_organization_social`, `r_organization_social`, `rw_organization_admin`.
Busca agora `/rest/organizationAcls` (campo `organization`, com tolerância ao
campo antigo) e `/rest/organizations/{id}`. Erros de API não viram mais lista
vazia; 401/403 no callback exibem orientação específica sobre acesso.
Header compartilhado `LinkedIn-Version` atualizado de 202401 para 202601,
versão ativa conferida na documentação oficial; reavaliar antes de 15/01/2027.
Não houve teste com token real, publicação ou confirmação de implantação.
Validação local: 141 testes de providers/contas sociais/OAuth passaram e lint passou.
Referências: https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access
e https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-access-control-by-role
e https://learn.microsoft.com/en-us/linkedin/marketing/integrations/migrations?view=li-lms-2026-01

Correção da prévia após colaboração: o `hx-vals` do painel usava
`js:getPreviewVals()`. O HTMX 2.0.4 envolve expressões sem chaves em um objeto,
produzindo JavaScript inválido (`Unexpected token '}'`) antes da requisição.
Corrigido para `js:{...getPreviewVals()}`. Reproduzido com HTMX real e Edge
isolado; teste `tests/browser/preview-request.cjs` verifica requisição com
imagem sem legenda e atualização posterior da legenda, sem chamadas externas.
Executar com Node e `playwright` disponível via `node_modules` ou `NODE_PATH`.
Há também teste Django de prévia com imagem sem legenda no módulo de slides.
Validação: teste de navegador passou e 34 testes de Composer/colaboração passaram.
Esta correção de template exige implantar web e atualizar o navegador.

O histórico abaixo foi escrito antes de novas alterações no projeto. A base
atual passou a ser `02cbee8`, com seleção de aprovador (`e7e96ba`), identidade
Jobz (`529dcb6`), prévia 4:5 (`0115a47`) e ordenação de slides (`02cbee8`).
Portanto, o texto histórico de que não existe seletor de aprovador não descreve
mais o código atual.

O usuário pediu primeiro a viabilidade de colaboração, música e Stories no
Instagram e depois autorizou começar SOMENTE pela colaboração.

Implementação de colaboração:

- Campo opcional "Colaboradores" no Composer, por conta `instagram` selecionada
  (conexão via Facebook Login; não confundir com `instagram_personal`).
- Até três nomes de usuário, com ou sem `@`, separados por vírgula. Normaliza
  caixa, remove duplicados e rejeita links/nomes inválidos/mais de três nomes.
- Salva no `PlatformPost.platform_extra['collaborators']`, também no autosave,
  nas versões e ao enviar para aprovação. Limpar o campo remove os convidados;
  uma requisição antiga sem esse campo preserva o valor anterior.
- O motor já encaminha `platform_extra` ao provider. O provider envia a lista
  ao criar o contêiner da foto/Reel ou o contêiner PAI do carrossel.
- Stories e outros formatos não aceitam colaboração: o provider rejeita antes
  de chamar a API. O aceite do convite continua dependendo do outro perfil.
- Sem alteração de modelo ou migração. Testes em
  `tests/test_instagram_collaborators.py`; integrações externas bloqueadas no
  módulo de teste. Nenhuma publicação real feita para validar a funcionalidade.
- Vídeos únicos do Instagram com colaboradores são encaminhados como Reels,
  evitando o fallback genérico de vídeo que não monta o payload REELS.
- 132 testes de colaboração, aprovação, Composer, OAuth e providers passaram.
  Build Tailwind passou. Campo conferido no navegador em 1240 px e 390 px,
  usando banco temporário, sem alterar dados locais de usuários.
- O lint do código novo passou. `User` dentro de `save_post` já tinha um aviso
  N806 antes desta alteração; não foi renomeado por ser alheio à funcionalidade.

Ao implantar esta funcionalidade, atualizar tanto web quanto worker no EasyPanel
e recarregar a interface. Não confundir código publicado com teste real na Meta
ou implantação confirmada pelo usuário.

Os outros pedidos permanecem pendentes. A documentação oficial consultada indica
colaboração em fotos/carrosséis/Reels e API de áudio para REELS via Facebook
Login (catálogo limitado). Há código inicial de Stories, mas automatizar uma nova
publicação em Story é diferente de compartilhar o post do feed com cartão
clicável: não prometer esse compartilhamento nativo sem validar a API.

Referências oficiais consultadas:

- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/
- https://developers.facebook.com/docs/instagram-platform/content-publishing/audio-api/

## Histórico da implantação e das primeiras correções

## Objetivo e comunicação

Rafael está adaptando o BrightBean Studio para gerenciar publicações de redes
sociais da Jobz, com equipe e aprovação de conteúdo. A função prioritária é
enviar publicações para aprovação e avisar os revisores por e-mail.

O usuário prefere respostas curtas em português e instruções operacionais
simples, uma etapa por vez. Ele envia capturas do EasyPanel e da Meta.
Não suponha familiaridade com SSH, Docker ou administração de servidores.

## Localização e Git

- Pasta do projeto: `C:\Users\rafae\OneDrive\Documentos\ChatGPT\app socialmedia\brightbean-socialmediastudio`.
- Repositório atual/origin: https://github.com/rafaelsiimao/socialmediajobz
- Repositório original/upstream: https://github.com/imcabal/brightbean-socialmediastudio.git
- Branch de trabalho e implantação: `main`.
- Último commit de código verificado ao escrever este documento: `df0e1a9`.
- Licença original: AGPL-3.0; preservar licença e créditos.
- Antes deste documento, a árvore estava limpa e sincronizada com origin/main.
- Esta documentação foi criada localmente; não pressupor commit ou push dela.

## Arquitetura

- Python/Django 5.1; templates Django, HTMX, Alpine.js e Tailwind.
- Produção: Gunicorn + PostgreSQL; Dockerfile instala também Node e FFmpeg.
- Tarefas: django-background-tasks, comando `python manage.py process_tasks`.
  Não é Celery; Redis não é requisito para a instalação atual.
- CSS: `theme/static_src`; compilação com `npm.cmd run build` no Windows.
- `config/settings/base.py`: banco, storage, e-mail, credenciais e CSP.
- `config/settings/production.py`: HTTPS, CSP e storage local com URL assinada.
- `providers/`: clientes das APIs sociais.
- `apps/social_accounts/`: OAuth, seleção de Páginas e persistência das contas.
- `apps/composer/`: editor, rascunhos, upload e prévias.
- `apps/approvals/`: revisão, decisões e histórico.
- `apps/members/`: convites, participação e permissões.
- `apps/notifications/`: preferências e envio das notificações.

## Ambiente local

O Docker não estava instalado no computador. Foi preparado um ambiente
Python 3.13 em `.venv`, SQLite em `db.sqlite3`, `.env` local e CSS compilado.
O ambiente local é apenas de teste, separado do PostgreSQL de produção.

- `start-local.ps1`: migrações, servidor em 127.0.0.1:8000 e worker ocultos.
- `stop-local.ps1`: encerra somente os processos correspondentes deste projeto.
- Logs/PIDs em `media/.local/`; consulte `LOCAL.md`.
- E-mail no desenvolvimento vai para o console. Credenciais sociais locais
  não foram configuradas. Não reproduzir senhas da conta de teste neste guia.
- Não presumir que os processos locais ainda estejam ativos.

## VPS / EasyPanel — estado confirmado pelo usuário

Endereço público: https://socialmedia-web.hqzarv.easypanel.host

Serviços no projeto do EasyPanel:

| Serviço | Tipo | Função |
| --- | --- | --- |
| `socialmedia` | PostgreSQL | Banco compartilhado |
| `web` | App | Aplicação HTTP, porta interna 8000 |
| `worker` | App | Tarefas em segundo plano |

Web e worker usam o repositório `rafaelsiimao/socialmediajobz`, branch `main`,
caminho de build `/` e o `Dockerfile` da raiz.

Comando de inicialização do web configurado durante a instalação:

```sh
sh -c 'python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2'
```

Comando do worker:

```sh
python manage.py process_tasks
```

O domínio do web usa HTTPS público e destino HTTP interno na porta 8000.
O worker não precisa de domínio. O administrador foi criado na VPS com
`python manage.py createsuperuser`; suas credenciais não estão neste guia.

Variáveis configuradas nos dois serviços (somente nomes, nunca valores secretos):

- `DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG=false`.
- `SECRET_KEY` e `ENCRYPTION_KEY_SALT`: iguais no web e worker e estáveis.
- `DATABASE_URL`: URL interna do PostgreSQL do EasyPanel.
- `ALLOWED_HOSTS` e `APP_URL`: domínio público acima.
- `PLATFORM_FACEBOOK_APP_ID` e `PLATFORM_FACEBOOK_APP_SECRET`.
- SMTP Gmail: `EMAIL_BACKEND_TYPE=smtp`, `EMAIL_HOST=smtp.gmail.com`,
  `EMAIL_PORT=587`, `EMAIL_USE_TLS=true`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD` (senha de app Google), `DEFAULT_FROM_EMAIL`.

O usuário confirmou recebimento de convite após configurar o Gmail.

### Armazenamento persistente

Após várias implantações, `/app/media` não existia nos containers antigos:
as tentativas de backup com `docker cp` falharam por pasta ausente. Não foi
possível recuperar os uploads dessas instâncias; não afirmar que há backup.

O usuário criou na VPS `/opt/socialmediajobz/media` e configurou montagem
Bind IGUAL no web e worker:

| Campo EasyPanel | Valor |
| --- | --- |
| Caminho do Host | `/opt/socialmediajobz/media` |
| Caminho de Montagem | `/app/media` |

Depois disso, o usuário confirmou que estava funcionando. Storage é `local`.
Não usar IDs de containers das capturas antigas: mudam a cada implantação.
Pasta persistente não substitui backup; não há confirmação de backup agendado.

## Facebook / Instagram — estado confirmado

Ambos conectados com sucesso pelo usuário. Instagram profissional vinculado
a uma Página do Facebook, usando o fluxo com Facebook Login.

Aplicativo Meta criado pelo usuário: **Jobz Social Media**.
Não presumir que esteja publicado, aprovado para terceiros ou com empresa
verificada; a conexão das próprias contas foi confirmada.

Casos de uso configurados: gerenciamento de Páginas, Instagram e Messenger.
O Messenger foi necessário porque o conector Facebook solicita `pages_messaging`.

Callbacks cadastrados no Facebook Login para Empresas:

```text
https://socialmedia-web.hqzarv.easypanel.host/social-accounts/callback/facebook/
https://socialmedia-web.hqzarv.easypanel.host/social-accounts/callback/instagram/
```

As variáveis Meta usam ID e segredo do aplicativo PRINCIPAL; não confundir
com as credenciais específicas do fluxo Instagram Login.
Para confirmar os scopes atuais, ler `required_scopes` nos providers.

## Correções já publicadas

| Commit | Correção |
| --- | --- |
| `17bafca` | Storage local default ausente; rascunhos sem canal invisíveis; erros de login não exibidos; scripts locais |
| `737a6e3` | CSP para o avaliador do Alpine padrão (`unsafe-eval`) |
| `4a30827` | Flatpickr CSS/JS locais; entrega assinada de arquivos em produção; prévia genérica sem canal |
| `56aa804` | CSP form-action permite redirecionamento OAuth para www.facebook.com |
| `bd5f5c5` | Instagram solicita pages_show_list, pages_read_engagement e business_management |
| `df0e1a9` | avatar_url de SocialAccount ampliado de 500 para 4096 e migração 0004 |

Detalhes que evitam regressões:

- O arquivo `static/js/alpine.min.js` é o build PADRÃO do Alpine, apesar dos
  comentários antigos dizerem CSP build. As expressões usam avaliação dinâmica.
- A política de produção permite inline/eval para a interface existente.
  Endurecer exige refatoração e testes de navegador; não remover às cegas.
- Flatpickr está em `static/vendor/flatpickr/`, com licença MIT preservada.
  O comentário no production.py sobre o CDN é histórico; o template já usa local.
- `SignedMediaStorage` gera links válidos por uma hora para `/media-file/...`.
  `apps/common/media_views.py` valida assinatura, expiração e caminho antes de
  servir arquivos locais. Não transformar isso em diretório público sem validação.
- Prévia genérica permite ver conteúdo sem canal, mas aprovação ainda exige
  `PlatformPost`, que corresponde a uma conta social selecionada.
- O erro PostgreSQL `value too long for type character varying(500)` após
  selecionar Página foi tratado na migração de avatar_url, sem truncar URL.

## Aprovação — implementação da seleção de destinatário

Implementado em 21/10/2026 a pedido do usuário:

1. **Campo no modelo:** `Post.assigned_reviewer` adicionado (ForeignKey para User, nullable), com migração `apps/composer/migrations/0016_post_assigned_reviewer.py`.
2. **Serviços de aprovação (`apps/approvals/services.py`):**
   - `submit_for_review` e `resubmit_post` aceitam parâmetro `reviewer=None`.
   - Se um revisor específico for selecionado, apenas ele é notificado e recebe o e-mail de aprovação.
   - Se nenhum for selecionado (fallback "Qualquer revisor"), todos os membros com `approve_posts=True` continuam sendo notificados.
   - Adicionada `action_url` (`/workspace/<id>/approvals/`) ao payload da notificação para alimentar o botão "View Details" nos e-mails.
3. **Composer View & Template (`apps/composer/views.py` e `templates/composer/compose.html`):**
   - Contexto fornece `available_reviewers` (membros com `approve_posts=True`).
   - Seletor de revisores exibido ao lado do botão "Submit for Approval" / "Resubmit", permitindo escolher "Qualquer revisor" ou um membro específico.
   - Salvamento de rascunhos e envio para aprovação persistem `assigned_reviewer`.
4. **Testes:**
   - Criado `tests/test_approvals_assignment.py` (4 testes passando: revisor específico, fallback geral, reenvio com memória de revisor e renderização de e-mail com botão de ação).
   - Testes de regressão (109 testes) e checagem de sistema Django passaram sem erros.

## Múltiplos slides e ordenação no Composer

Implementado em 21/10/2026 a pedido do usuário:

1. **Problema identificado:**
   - Upload de múltiplos slides (ex.: 7 imagens de carrossel) disparava requisições assíncronas.
   - O autosave periódico ou salvamento prematuro capturava apenas os primeiros arquivos prontos na sessão e executava `del request.session[key]`, descartando os slides que ainda estavam subindo.
   - O endpoint de prévia consultava o banco com `id__in`, que em SQL não preserva a ordem do array, gerando slides fora da ordem selecionada.
2. **Solução implementada:**
   - Formulário e prévia agora trafegam a lista explícita e ordenada `media_ids` refletindo a ordem real do DOM (`#media-list`).
   - Criada a função `_sync_post_media` em `apps/composer/views.py`, garantindo persistência da sequência exata (`position = 0, 1, ..., N-1`) em `save_post` e `autosave`.
   - Adicionada trava no frontend (`htmx:configRequest`) para impedir que o autosave seja disparado enquanto houver uploads em andamento (`isUploading || uploadQueue.length > 0`).
   - Implementado Drag-and-drop nativo nos cards de miniaturas para reordenação visual dos slides, atualizando a prévia em tempo real.
   - Criada a suíte de testes `apps/composer/tests/test_multi_slide_preview_and_order.py` (3 testes cobrindo ordem exata de 7 slides na prévia, salvamento com posições corretas e persistência de reordenação).

## LinkedIn Company Pages (Páginas de Empresa)

Implementado em 21/10/2026:

1. **Configuração e Vetting no LinkedIn:**
   - Criado app dedicado "Social 2 Jobz" no LinkedIn Developer Portal.
   - Associação com a página "Grupo Jobz" verificada.
   - Submetido formulário oficial da Community Management API (Development Tier) para aprovação da Microsoft/LinkedIn Vetting Services.
   - Credenciais cadastradas no EasyPanel (`PLATFORM_LINKEDIN_CLIENT_ID` e `PLATFORM_LINKEDIN_CLIENT_SECRET`).
2. **Suporte no Sistema (Backend & Providers):**
   - Em `providers/linkedin_company.py`: implementado `get_user_pages` via `/v2/organizationalEntityAcls` e `/v2/organizations/{id}` para listar as páginas da empresa administradas pelo usuário.
   - Em `apps/social_accounts/views.py`: fluxo OAuth de `linkedin_company` agora direciona para `select_account`, permitindo selecionar a página desejada com nome e logo.
   - Em `apps/publisher/engine.py` e `providers/linkedin_company.py`: postagens para `linkedin_company` injetam autoridade como organização (`author = urn:li:organization:<id>`).
   - Criado `tests/providers/test_linkedin_company.py` (3 testes automatizados cobrindo instanciação, busca de páginas e injeção do autor organização).

## Outras limitações e pendências

- A tela `templates/credentials/list.html` ainda é um placeholder. As credenciais
  sociais foram configuradas pelo Ambiente do EasyPanel.
- Tradução para pt-BR foi discutida e explicitamente adiada. Não iniciá-la.
- Backup persistente, seleção de aprovador, entrega de notificações de aprovação
  e uso por clientes externos não estão validados em produção nesta conversa.
- Em `_send_invite_email`, falhas de SMTP são registradas mas o convite fica
  criado. Se não chegar, verificar logs, SMTP e preferências; não presumir envio.
- Em erro 500 na VPS, pedir o traceback do serviço web; não adivinhar a causa.
- Não publicar posts ou enviar mensagens reais de teste sem autorização.

## Verificações e testes

Os testes locais usam SQLite e não reproduzem todos os limites do PostgreSQL.
O teste de URL longa valida também o campo para não depender de varchar SQLite.

Comando de testes relevantes no PowerShell, dentro do projeto:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_meta_oauth.py tests/test_media_delivery.py tests/test_unassigned_drafts.py tests/test_local_storage.py apps/composer/tests/test_idea_media_flows.py tests/providers/test_base.py --ds=config.settings.development -q --override-ini=addopts=
```

Resultados registrados, não uma execução nova deste guia:

- 15 testes de upload/rascunhos/ideias passaram inicialmente.
- 16 testes de entrega de mídia/prévias/ideias passaram após as correções.
- 92 testes de OAuth/providers passaram após corrigir scopes do Instagram.
- 4 testes Meta passaram no último ajuste de avatar, com migração consistente.
- 202 testes automatizados validados com 100% de sucesso após tradução PT-BR, correção de agendamento, identidade visual Jobz (logo, favicon e cores), modal de seleção de revisor e proporção 4:5 (1080x1350) adaptativa na prévia do Instagram.
- Testes de navegador com Playwright/Edge reproduziram o bloqueio do Alpine,
  o redirecionamento CSP e o calendário sem CSS; os respectivos ajustes passaram.
- Warnings de `staticfiles` ausente nos testes locais foram registrados;
  o Dockerfile executa collectstatic na construção para produção.

Outros comandos úteis:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.settings.production
.\.venv\Scripts\python.exe manage.py makemigrations social_accounts --check --dry-run
git diff --check
```

O ambiente de execução do Codex pode restringir rede/processos/temporários;
instalações, browser tests e pushes anteriores exigiram execução autorizada
fora do sandbox. Não contornar bloqueios ou assumir que uma falha de permissão
é um defeito do aplicativo.
