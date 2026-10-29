# Ordenação e remoção de mídias — 29/10/2026

No editor, arraste as miniaturas ou use as setas esquerda/direita. A numeração
indica a ordem do carrossel. O X remove a mídia desta publicação, preservando o
arquivo original na biblioteca. A prévia atualiza e as mudanças disparam o
salvamento automático após um segundo; Salvar Rascunho continua disponível.

## Modal de recorte — 29/10/2026

O botão azul com ícone de recorte, entre as setas da miniatura, abre **Ajustar
recorte** nos carrosséis fotográficos do feed Instagram. A proporção fica fixa
conforme a capa; a pessoa pode arrastar a foto/seleção, aproximar, afastar,
recomeçar, conferir o Resultado e aplicar ou cancelar. Escape também cancela.

Reaproveita o Cropper.js 1.6.2 já distribuído no projeto. O navegador envia apenas
coordenadas ao servidor, que lê o arquivo pelo storage e recorta com Pillow;
não depende de exportar canvas de imagens hospedadas em outro domínio.

`POST compose/crop-media/<asset_id>/` exige login, create_posts, upload_media,
CSRF e vínculo com workspace. Origem e capa devem ser fotos desse workspace.
Valida área, coordenadas finitas, proporção da capa, orientação EXIF e até 40 MP.
Cria JPEG novo (até 1080×1350 sem ampliar), preservando o original e os vínculos
de outras publicações. Responde com uma miniatura substituta; save/autosave normal
persiste somente a nova lista de IDs, mantendo a ordem. Nenhum vínculo é alterado
no endpoint de recorte. Cancelar não cria arquivo nem modifica o formulário.
Falha mantém o modal e a foto original, com mensagem para tentar novamente.

Conferência: 61 testes Python (inclui 11 para recorte, área escolhida, reabertura,
isolamento e permissões) + navegador isolado com Cropper real: arraste, Escape,
proporção da capa, erro/retry, substituição e autosave no celular. Django check e
lint do código novo passaram. Sem migrações ou variáveis novas; implantar somente
web e Ctrl+F5. Não houve publicação real ou acesso às contas sociais nos testes.

## Proporções diferentes — 29/10/2026

Para carrosséis de fotos no feed do Instagram, a capa define o enquadramento.
O editor compara proporções, não tamanho em pixels: duas imagens 800×1000 e
1600×2000 são equivalentes. Diferenças menores que 1% são tratadas como
arredondamento. Usa dimensões salvas ou, quando faltam, as dimensões da imagem
original carregada pelo navegador; não usa uma miniatura quadrada como referência.

Fotos afetadas recebem borda vermelha, etiqueta Recorte e uma explicação. Todas
as miniaturas assumem o quadro da capa e exibem recorte central; a prévia de feed
já usa a primeira foto com `object-fit: cover`. Reordenar, remover a capa ou
adicionar fotos recalcula a indicação. O aviso não impede salvar/publicar.

O enquadramento segue os limites atuais da prévia (4:5 a 1,91:1). Stories,
Reels, uma única foto, seleções sem Instagram e carrosséis contendo vídeo não
ativam esse aviso de carrossel fotográfico. Vale para os dois conectores IG.
Os arquivos originais não são alterados: o envio continua usando a API existente,
que aplica seu enquadramento na publicação. Esta mudança é no editor, sem nova
opção de publicação manual e sem alterações em LinkedIn ou Insights.

Conferidos 27 testes Python e navegador isolado: mesma proporção em resoluções
diferentes não alerta; proporção diferente fica vermelha; troca da capa altera
as marcações e o quadro; Story desativa e feed reativa o aviso; ordenação,
remoção e autosave continuam funcionando. Implantar somente web e Ctrl+F5.

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
