# Instruções para agentes

Antes de trabalhar, leia `PROXIMA_SESSAO.md` (ponto atual da análise Meta em
23/10/2026) e depois `CONTEXTO_PARA_IA.md`. Ele registra arquitetura,
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

O trabalho atual é orientar a análise do app Meta para conectar contas de
clientes, com outro perfil Facebook, em novos workspaces. A solicitação ainda
não foi enviada; tela atual e próximos passos estão em `PROXIMA_SESSAO.md`.
Colaboração Instagram, seletor de aprovador e correção de prévia já existem.
Música e compartilhamento nos Stories foram discutidos, mas não implementados.
Consulte a atualização no início do documento de contexto antes do histórico.

Atualize `CONTEXTO_PARA_IA.md` quando houver mudanças importantes confirmadas.
