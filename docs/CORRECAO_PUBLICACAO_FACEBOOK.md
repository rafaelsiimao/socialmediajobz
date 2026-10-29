# Facebook: publicação com várias fotos

## Problema confirmado e correção — 29/10/2026

O worker já entregava as mídias na ordem de PostMedia.position, mas o provider
Facebook usava apenas media_urls[0]. Várias fotos viravam uma publicação com
somente a primeira. A correção fica em providers/facebook.py e atende os tipos
IMAGE e CAROUSEL, sem mudar a resolução de formatos das outras redes.

Para várias fotos, cada URL é enviada a /{page_id}/photos com published=false.
Somente após todos os uploads retornarem IDs, uma chamada a /{page_id}/feed
envia attached_media com todos os IDs na ordem original e message com a legenda
efetiva completa. O ID armazenado é o da publicação final, utilizado também
pelas métricas e pelo primeiro comentário. Uma foto mantém o fluxo anterior.

Falha de upload ou ausência de ID interrompe o processo antes de criar o post
visível. Falha no feed propaga erro; o worker não marca como publicado. Uploads
anteriores permanecem não publicados na Meta; não se apagam arquivos locais ou
posts existentes. As retentativas continuam sob a política já existente do worker.
Timeout após a Meta criar o post continua sujeito à ambiguidade da política de
retentativas preexistente; esta correção não implementa idempotência remota.

Também se impede que conjuntos com vídeo sejam silenciosamente reduzidos ao
primeiro arquivo: esta integração continua aceitando várias fotos ou um vídeo.
Isso não declara que o aplicativo nativo do Facebook tenha a mesma limitação.
Não implementado envio misto fotos/vídeos neste ajuste. LinkedIn e Instagram não
foram alterados.

## Validação

- Testes do provider com 2, 3 e 10 fotos, IMAGE/CAROUSEL, ordem, legenda longa,
  IDs finais, falha no meio do upload, ID ausente e falha ao criar o feed.
- Testes do worker com modelos reais, arquivos sintéticos, ordem alterada 2/0/1,
  legenda geral/personalizada e confirmação de status publicado/erro.
- Chamadas HTTP à Meta simuladas: nenhuma publicação real foi realizada.
- Lint e check Django. Executar:

```powershell
.venv/Scripts/python.exe -m pytest tests/providers tests/test_facebook_publish_dispatch.py tests/test_linkedin_publish_dispatch.py tests/test_publish_queue.py --ds=config.settings.development --basetemp=media/.local/facebook-tests-20261029 -q --tb=short
```

## Implantação

Implantar web e worker no EasyPanel. Não há migração ou variável nova.
Validar na VPS com um post novo autorizado contendo três fotos na ordem desejada.
Posts antigos já publicados com uma foto não são alterados automaticamente.

Referência da API: https://developers.facebook.com/docs/graph-api/reference/page/photos/
e https://developers.facebook.com/docs/pages-api/posts/ . A consulta direta à
documentação nesta sessão retornou HTTP 429; os testes locais validam o protocolo
de upload não publicado + attached_media, não a aceitação real pela Meta na VPS.
