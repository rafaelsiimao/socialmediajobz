# Ordenação e remoção de mídias — 29/10/2026

No editor, arraste as miniaturas ou use as setas esquerda/direita. A numeração
indica a ordem do carrossel. O X remove a mídia desta publicação, preservando o
arquivo original na biblioteca. A prévia atualiza e as mudanças disparam o
salvamento automático após um segundo; Salvar Rascunho continua disponível.

## Causas corrigidas

- Miniaturas de uploads inseridas por XMLHttpRequest não inicializavam os
  atributos HTMX do X dos anexos salvos. Ambos os tipos de miniatura agora usam
  a mesma remoção do estado do formulário, persistida no save/autosave.
- O arraste guardava uma variável diferente a cada inicialização, impedindo
  mover entre fotos carregadas em momentos diferentes. O estado agora pertence
  à lista; os filhos de imagem não iniciam seu próprio arraste.
- A sessão de uploads pendentes era mesclada à lista explícita do formulário,
  recolocando fotos retiradas. `media_submitted=1` torna a lista explícita,
  inclusive vazia, a fonte do salvamento e da prévia. Fallback legado continua
  disponível para chamadas sem lista explícita.
- Fotos adicionadas pela biblioteca também inicializam os controles após o
  swap HTMX. Alterações reais continuam invalidando links de aprovação.

## Conferência

`tests/test_carousel_editor.py`: remoção total/parcial, nova ordem, save e
autosave com sessão antiga, reabertura, preservação dos arquivos da biblioteca
e prévia vazia. `tests/browser/carousel-editor.cjs`: HTML real com dados
fictícios, Alpine/HTMX e requisições interceptadas; uploads sucessivos, arraste,
setas, X, payloads de autosave e prévia, miniaturas pendentes e salvas.

Para exportar a fixture do navegador, execute o teste `carousel_browser_fixture`
com `CAROUSEL_BROWSER_FIXTURE_DIR=media/.local`; execute o script Node passando
`media/.local/carousel-editor.json`, com Playwright disponível em NODE_PATH.

Sem migrações ou novas variáveis. Implantar apenas **web** no EasyPanel e
recarregar com Ctrl+F5. A confirmação final na VPS deve incluir reabrir um
rascunho após mudar a ordem e remover uma foto. Não houve publicação real
durante os testes.
