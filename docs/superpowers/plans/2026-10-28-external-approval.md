# Aprovação externa por link — implementação

**Especificação aprovada:** mensagem do plano nesta conversa e confirmação de
Rafael em 28/10/2026. Link por publicação, sem login, válido por sete dias;
aprovar/rejeitar/pedir ajustes, resposta única, agradecimento por dez segundos,
e-mail para rafael.simao@jobz.com.br e histórico preservado.

**Arquitetura:** ApprovalLink guarda hash do segredo, versão do conteúdo,
destinatário, expiração e resposta. Rotas públicas não criam sessão de login.
ApprovalEmail é uma caixa de saída persistente, processada pelo worker existente.
O compositor oferece aprovação externa a quem pode aprovar posts; o fluxo
interno continua disponível. Envio externo substitui links anteriores do post.

**Tecnologias:** Django, PostgreSQL, django-background-tasks, templates HTML.

- [x] Testes de acesso anônimo, isolamento, expiração, respostas únicas,
  alteração de conteúdo e novos envios invalidando links anteriores.
- [x] Modelos e migração de links/e-mails; serviços de emissão, decisão,
  comparação de conteúdo e fila com novas tentativas.
- [x] Rotas públicas GET/POST com CSRF, cache privado e proteção de tokens;
  prévia por canal com imagens e vídeos; agradecimento encerra em dez segundos.
- [x] Modal no compositor com nome/e-mail; resultado autenticado com copiar
  link e estado do envio; integração sem interferir no fluxo interno.
- [x] Testes de todos os resultados, mídia, worker/e-mail, permissões e
  regressões do compositor/aprovações; verificar migrações e diff.

**Restrições:** sem e-mails ou publicações reais nos testes. Não deletar
histórico. GET nunca decide nem consome link (scanners de e-mail). Consumo e
alteração de estado na mesma transação com bloqueio das linhas; uma resposta
duplicada retorna link encerrado. Alteração de conteúdo invalida mesmo que não
tenha nova PostVersion. Não confiar em nome de usuário autenticado no link.
Links não autorizam acesso ao workspace nem a notas internas. Pessoa com o
link pode responder em nome do destinatário; a tela informa essa natureza.

**Verificação:** pytest tests/test_external_approval.py e regressões existentes;
makemigrations --check --dry-run; Django check. Produção requer migração no web
e implantação web + worker; confirmar envio e reprodução reais após deploy.
