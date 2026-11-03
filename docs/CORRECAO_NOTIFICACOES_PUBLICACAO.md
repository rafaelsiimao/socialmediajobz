# Falhas de publicação e notificações — 31/10/2026

Pedido de Rafael: investigar relato de erros e notificações, esclarecido como
falhas ao publicar posts. Envio ao GitHub autorizado em 02/11/2026;
implantação na VPS pendente.

## Causas reproduzidas

- O publicador salvava `publish_error` e `PublishLog`, mas não chamava `notify`
  para sucesso ou falha definitiva. Os tipos de evento existiam sem integração.
- O poll normal incluía posts aguardando retry, ignorando `next_retry_at`.
- Sucesso posterior mantinha erro e próximo retry antigos no registro.
- Bloqueio por rate limit não gerava `PublishLog`.
- O editor não apresentava o erro de publicação salvo.
- O menu Notificações não inicializava o contador; o código do sino estava sem
  componente ativo. O refresh também usava `__x`, incompatível com Alpine 3.
- O clique do drawer era interceptado pelo POST HTMX, impedindo navegação.
- Marcar todas via HTMX chamava uma view restrita a GET com uma requisição POST
  (405). O histórico também precisava receber o seu próprio partial.
- Marcar uma no histórico removia o registro da tela mesmo sem filtro de não lidas.
- Página inválida no histórico causava erro 500.
- A rotina de retry das entregas não tinha tarefa recorrente registrada.

## Comportamento corrigido

- Autor do post recebe resultado por conta/rede, com link absoluto para o editor.
  Sucesso: notificação interna por padrão; falha definitiva: interna e e-mail,
  conforme preferências já existentes. Falhas temporárias ficam no editor até
  concluir as tentativas. Sem autor, não há destinatário para esse alerta.
- Notificar não pode transformar publicação bem-sucedida em nova tentativa se o
  mecanismo de notificações falhar.
- Poll normal exclui posts com `next_retry_at`; rotina específica respeita o prazo.
  Mantidos os intervalos existentes de 1, 5 e 30 minutos e três retries.
- Sucesso limpa erro e retry pendente; falha final limpa próximo retry. Histórico
  de tentativas preservado, incluindo bloqueios por rate limit.
- Editor mostra motivo por conta e próxima tentativa (ou tentativas esgotadas).
- Menu mostra contagem de não lidas atualizada a cada 30 segundos; ações HTMX
  atualizam o contador. Histórico mantém registros lidos e respeita os filtros.
- Drawer marca leitura com POST/CSRF e preserva a navegação do link.
- Tarefa `retry_notification_deliveries` registrada uma vez, a cada 60 segundos,
  no `post_migrate`, consumida pelo `process_tasks` existente.

## Validação local

99 testes passaram: regressões novas, notificações, publicador, dispatch Facebook
e LinkedIn, e-mails em português, atribuição de aprovação e aprovação externa.
Ruff e Django check passaram. Teste Edge headless com templates reais + Alpine/HTMX
passou: contador, atualização após leitura, preservação do histórico, CSRF e
navegação do drawer. Todas as respostas de rede desse teste são simuladas.
Nenhuma postagem ou mensagem/e-mail real foi enviada.

Comandos a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_publish_notifications.py apps/notifications/tests.py apps/publisher/tests.py tests/test_facebook_publish_dispatch.py tests/test_linkedin_publish_dispatch.py tests/test_emails_ptbr.py tests/test_approvals_assignment.py tests/test_external_approval.py --ds=config.settings.development -q --tb=short --override-ini=addopts= --basetemp=media/.local/notification-verification --reuse-db
$env:NODE_PATH='C:\Users\rafae\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
node tests/browser/notifications.cjs
```

O Edge precisou executar fora do sandbox do Windows; o teste bloqueia origens
externas e usa perfil descartável. Os testes pytest usam SQLite de teste; nunca
executar o worker de produção como forma de testar esta correção.

## Implantação pendente

Enviar somente arquivos desta correção, conforme autorizado por Rafael em
02/11/2026, preservando
mudanças locais anteriores de Insights e Remotion. Implantar web com o `migrate`
habitual para registrar a tarefa, depois reiniciar/implantar worker e atualizar o
navegador. Sem novas migrações de modelos ou variáveis de ambiente. SMTP e execução
do `process_tasks` precisam estar funcionais na VPS; isso não foi confirmado.

O check global de migrações aponta drift preexistente de AutoField/BigAutoField
no pacote `background_task`; nenhuma migração desse pacote foi gerada/alterada.

Alertas novos valem para novos resultados; não foram reenviadas notificações
retroativas nem alterados posts antigos. Resumo diário, webhooks e alertas de
desconexão não foram modificados nesta correção focada na publicação.
