# Instruções para agentes

Antes de trabalhar, leia `CONTEXTO_PARA_IA.md`. Ele registra arquitetura,
correções, implantação e o ponto em que a conversa parou. Consulte também
`README.md`, `LOCAL.md` e os arquivos reais antes de assumir comportamentos.

## Como colaborar

- Responda em português brasileiro, de forma simples, curta e objetiva.
- Rafael prefere orientações de operação em uma etapa por vez, principalmente
  no EasyPanel e no painel da Meta. Use os nomes visíveis nas telas enviadas.
- Investigue logs e reproduza erros antes de alterar o código. Diferencie
  diagnóstico confirmado de hipótese e teste local de confirmação na VPS.
- Preserve dados existentes, vínculos sociais e configurações de produção.
- Não comite `.env`, senhas, tokens, banco local, uploads, logs ou ambientes.
- Não copie credenciais da conversa para arquivos. Elas ficam no EasyPanel.
- Não altere chaves de criptografia de uma instalação existente: isso afeta
  a leitura dos tokens já armazenados.
- Mudanças em modelos exigem migração. Não trunque URLs ou tokens para
  contornar limites de campos.
- Execute testes relevantes; veja os comandos no documento de contexto.
- Um push ao GitHub não comprova implantação. O usuário executa Implantar
  no EasyPanel. Não afirme que algo está ativo na VPS sem evidência.
- Criar documentação ou desenvolver localmente não significa autorização
  automática para implantar, enviar e-mails ou publicar em redes sociais.
- Mantenha licença AGPL-3.0 e créditos do projeto de origem.

## Estado da tarefa

O usuário pediu este material de passagem de contexto. A próxima necessidade
de produto em discussão é escolher destinatários para aprovação de posts.
Essa escolha por publicação ainda NÃO existe e NÃO foi solicitada como
implementação; não trate a conversa explicativa como uma especificação aprovada.

Atualize `CONTEXTO_PARA_IA.md` quando houver mudanças importantes confirmadas.
