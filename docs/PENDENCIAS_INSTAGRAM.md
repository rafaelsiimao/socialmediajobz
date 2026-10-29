# Instagram — implementação adiada por Rafael (29/10/2026)

Rafael pediu guardar para depois a liberação de carrosséis mistos (fotos e vídeos).
A prioridade passou a ser corrigir publicação de várias fotos e legenda no LinkedIn.
Não implementar esta pendência durante a correção urgente.

Investigação já feita: `composerApp.processFiles` bloqueia múltiplos vídeos e
mistura imagem/vídeo. Ambos os providers Instagram já criam filhos image_url e
VIDEO/video_url para CAROUSEL; o engine resolve múltiplas mídias como carrossel.

Escopo futuro: liberar no Post de Instagram/Instagram Personal, validar o total
(até 10) e vídeos do carrossel (até 60s conforme documentação operacional
consultada), incluir play nos vídeos da prévia, preservar ordem, adaptar aviso
de enquadramento à primeira mídia (foto ou vídeo). Recorte manual continua apenas
para fotos. Reels mantêm um vídeo; Stories mantêm seu fluxo separado. Conferir
novamente os limites oficiais antes de implementar; não apenas remover o alert.

Fonte consultada: https://support.sproutsocial.com/hc/en-us/articles/42017616974349-Instagram-Mixed-Media-Posts
