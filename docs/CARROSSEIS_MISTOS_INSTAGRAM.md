# Carrossel de fotos e vídeos no Instagram

## Uso

Selecione somente contas Instagram/Instagram Personal no formato **Post**.
Envie fotos, vídeos ou os dois na mesma seleção. É permitido selecionar vários
vídeos. Arraste ou use as setas para ordenar; a primeira mídia é a capa.

- Até 10 mídias no total, contando as já anexadas e uploads na fila.
- Cada vídeo do carrossel: até 60 segundos, em MP4/MOV compatível. MP4 com
  H.264/AAC é a opção recomendada. Não há transcodificação automática.
- A prévia oferece play, áudio e pausa ao trocar de slide.
- A primeira foto **ou vídeo** define o enquadramento, incluindo aviso vermelho
  de recorte. O ajuste manual continua sendo para fotos, inclusive com capa vídeo.
- Uma foto com vídeos e outras redes na mesma seleção gera aviso para manter
  somente Instagram/Post, evitando descartar conteúdo nos outros conectores.
- Reels continuam exigindo um vídeo; Stories seguem o fluxo separado existente.
  Um vídeo único no feed continua sendo resolvido como Reel, como antes.

## Validações

`composer-media.js` confere os arquivos locais antes de enviá-los e as mídias do
editor. `instagram_media.py` valida save/autosave e preserva a ordem e o escopo
do workspace. Duração desconhecida pode ficar em rascunho; agendamento/envio e
worker exigem duração conferida no servidor.

Uploads de vídeos na composição de feed pedem leitura por ffprobe; as dimensões
e duração vêm do arquivo armazenado, não de campos enviados pelo navegador.
Arquivos antigos sem duração são inspecionados novamente antes de publicar,
reutilizando o arquivo temporário baixado pelo worker. Se a leitura falhar,
o envio para antes de chamar a API e pede reenvio do vídeo. O FFmpeg/ffprobe já
faz parte do Dockerfile. Não há nova variável de ambiente nem migração.

Ambos os providers mantêm filhos `image_url` e `VIDEO/video_url`, uma mídia por
filho, e um único pai CAROUSEL com a ordem completa. Colaboradores e legenda
ficam no pai. Há proteção de 2–10 filhos antes de qualquer chamada à API.

## Conferência

Validação local: **138 testes passaram**, incluindo leitura real via ffprobe
de MP4s sintéticos de 30 e 61 segundos e rotação de vídeos de celular. Django
check e lint dos arquivos novos/alterados passaram. Os três scripts de navegador
(misto, carrossel/recorte e Story) passaram. Falta implantação e validação na VPS.

Os testes cobrem seleção mista, ordem, durações, quantidade, outras redes,
MP4/MOV, metadados de upload, leitura real por ffprobe de vídeos sintéticos,
guardas do worker, payload dos dois conectores e controles da prévia. O script
`tests/browser/mixed-carousel.cjs` usa HTML real/Alpine/HTMX/Cropper, gera um MP4
sintético via FFmpeg e intercepta todas as requisições. Nenhuma conta real é usada.

Exportação do HTML: `MIXED_BROWSER_FIXTURE_DIR=media/.local` ao executar
`test_mixed_preview_and_browser_fixture`. Executar o script Node passando
`media/.local/mixed-editor.json`, com Playwright em NODE_PATH e FFmpeg no PATH.
Também conferir `carousel-editor.cjs` e `story-composer.cjs` para regressões.

Implantar **web e worker** no EasyPanel, depois Ctrl+F5. Validar um rascunho com
foto + vídeo curto, ordem, prévia e aprovação antes de uma publicação real.

Referência operacional consultada em 29/10/2026:
https://support.sproutsocial.com/hc/en-us/articles/42017616974349-Instagram-Mixed-Media-Posts
