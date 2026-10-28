# Aprovação externa por link

## Como usar

1. No editor, selecionar as contas, adicionar as mídias e a legenda.
2. Clicar em **Aprovação por link** (é necessário `approve_posts` no workspace).
3. Informar nome e e-mail do cliente e confirmar. O cliente não precisa ter
   cadastro nem acesso ao workspace.
4. A tela seguinte mostra **Copiar link**, validade e estado dos e-mails.
   O link pode ser compartilhado manualmente, inclusive por WhatsApp.
5. Para voltar à tela de acompanhamento, abrir o editor e clicar em
   **Ver link e envio**. O link completo fica disponível na sessão que o gerou;
   também está no convite enviado ao destinatário.

O cliente visualiza os canais, legendas e mídias (vídeos com controles), podendo
aprovar, rejeitar ou pedir ajustes. Rejeição e ajustes exigem comentários.
A resposta entra no histórico, e o resultado é enviado para
`rafael.simao@jobz.com.br`. Se essa conta existir na plataforma, recebe também
uma notificação interna. Comentários completos estão no histórico expansível.

O link vale sete dias e permite uma resposta. Após a resposta, fica inutilizado
imediatamente; o agradecimento é substituído por "Link encerrado" depois de dez
segundos. O histórico é preservado. Quem possuir o link pode responder em nome
do destinatário, portanto ele não deve ser encaminhado a outras pessoas.

Salvar conteúdo alterado ou reenviar para aprovação invalida os links anteriores.
Salvar automaticamente sem alterações não invalida. O GET não consome o link,
permitindo que verificadores de segurança de e-mail o abram sem aprovar nada.
Publicações já agendadas, em publicação, publicadas ou com falha devem voltar a
rascunho antes do envio. Uma aprovação preserva eventual data de agendamento,
seguindo o fluxo existente; sem data, a publicação fica aprovada.

## Implantação e operação

- Implantar **web** primeiro e verificar a aplicação de
  `approvals/0003_approvallink_approvalemail`. Depois implantar **worker**.
- Usa o SMTP já configurado; não exige novas credenciais. `APP_URL` precisa
  apontar para o domínio público HTTPS correto, como no restante do sistema.
- O worker existente `python manage.py process_tasks` envia e-mails pela tarefa
  `apps.approvals.email_tasks.deliver_approval_email`, descoberta através do
  módulo `apps.approvals.tasks`. Jobs e outbox são gravados na mesma transação.
- Exceções de SMTP persistem em ApprovalEmail e disparam novas tentativas do
  django-background-tasks. A tela também permite tentar e-mails pendentes de novo.
  Convites revogados, expirados ou de conteúdo alterado não são enviados.
- SMTP confirmar envio não comprova entrega na caixa de entrada. O fluxo oferece
  copiar link independentemente do envio; a decisão não depende do sucesso do SMTP.
- Token aleatório de 48 bytes; apenas SHA-256 no registro ApprovalLink. A URL
  completa permanece no convite e na sessão do emissor. Rotas públicas têm
  CSRF no POST, no-store/no-cache, Referrer-Policy same-origin e noindex.
  Essa política preserva Origin/Referer no próprio domínio para validar CSRF
  em HTTPS e não envia a URL do convite a outros domínios. Não criam login.
- Post e alvos são bloqueados antes do link para serializar decisões e reenvios
  em PostgreSQL. Testes locais usam SQLite; confirmar comportamento real na VPS.

## Verificação executada

31 testes: aprovação externa, fluxo interno, prévia de Reels e carrosséis.
Navegador Edge headless, sem rede externa: formulário em celular, comentário
obrigatório, agradecimento e encerramento em dez segundos. Django check,
lint dos módulos novos e verificação de migração de approvals passaram.
O check global de migrações aponta uma diferença preexistente no pacote
background_task (tipo do ID); nenhuma migração desse pacote foi criada.
Sem envio SMTP real, publicação real ou implantação durante o desenvolvimento.

## Correção CSRF em HTTPS (28/10/2026)

A política inicial no-referrer (header e meta) fez o Edge enviar Origin: null
ao submeter o formulário HTTPS, reproduzindo o erro de produção. Corrigidos
ambos para same-origin, sem csrf_exempt nem ampliação de origens confiáveis.
Teste no navegador agora usa HTTPS e confere os headers reais Origin e Referer;
três novos casos verificam aprovar/rejeitar/ajustes em HTTPS e preservam 403
para origem externa/null. Atualização só do web; reabrir o link após deploy
para carregar o novo formulário. O 403 não registra a decisão.
