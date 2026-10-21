# Jobz Social Media — contexto e passagem de trabalho

Atualizado em 21/10/2026, com base no código local e nas confirmações do usuário.

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
- 202 testes automatizados validados com 100% de sucesso após tradução PT-BR, correção de agendamento, identidade visual Jobz (logo, favicon e cores) e modal de seleção de revisor na aprovação do Composer.
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
