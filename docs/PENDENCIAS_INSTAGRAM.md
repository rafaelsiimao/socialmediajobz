# Instagram — carrosséis mistos retomados (29/10/2026)

**Status:** Rafael retomou a implementação após a correção urgente do LinkedIn.
Consultar `docs/CARROSSEIS_MISTOS_INSTAGRAM.md` para o fluxo implementado,
validações, testes e implantação. O registro abaixo é histórico, não uma nova
tarefa pendente nem uma instrução para adiar novamente.

Rafael pediu guardar para depois a liberação de carrosséis mistos (fotos e vídeos).
A prioridade passou a ser corrigir publicação de várias fotos e legenda no LinkedIn.
A correção urgente do LinkedIn foi enviada no commit `8fe0f0d` antes da retomada.

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
