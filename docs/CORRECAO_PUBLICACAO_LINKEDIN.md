# LinkedIn: várias fotos e legenda — 29/10/2026

## Proteção contra vídeo com outros anexos — 29/10/2026

Corrigido também o descarte silencioso quando o primeiro anexo era vídeo:
o provider escolhia somente o primeiro arquivo. Personal e Company agora validam
o conjunto antes de consultar o perfil ou iniciar uploads. A regra é várias fotos
ou um vídeo por publicação; conjuntos com vídeo e outro anexo retornam erro.
Uma foto, várias fotos e um vídeo individual mantêm os fluxos existentes.

O editor avisa e impede upload adicional incompatível, salvamento, autosave e
abertura do envio para aprovação enquanto o conjunto for inválido. Trocar canais
ou remover anexos recalcula o aviso. O servidor verifica os tipos reais dos
MediaAssets do workspace antes de criar/alterar/agendar o post, incluindo mídias
pendentes na sessão, IDs explícitos e anexos já salvos. Lista explícita vazia
permite remover todos os anexos, sem recuperar os anteriores da sessão.

O worker é protegido pelo provider também para publicações antigas já agendadas:
recusa antes da API e registra erro conforme a política de retentativas existente,
preservando arquivos e legenda. Não limpa automaticamente anexos ou posts antigos.
Rafael deve editar conjuntos antigos incompatíveis e separar os vídeos.

Testes simulam HTTP; nenhum post real é publicado. Browser local testa aviso nos
dois conectores, bloqueio de save/upload e recuperação após remoção. Não altera
OAuth, credenciais, métricas, renovação de tokens ou saúde da Company Page.
Implantar web + worker, Ctrl+F5. Sem migração ou ambiente novo.

Testes novos: tests/test_linkedin_media_selection.py,
tests/test_linkedin_publish_dispatch.py, tests/providers/test_linkedin_publishing.py
e tests/browser/linkedin-media.cjs. Regressões incluem Facebook, fila,
Instagram misto, Stories, Reels e aprovação externa.

## Problema relatado e causa encontrada

Rafael confirmou que posts com várias fotos publicavam só a primeira e que a
legenda chegava cortada, sem botão "ver mais". O provider compartilhado pelos
conectores Personal/Company escolhia explicitamente `media_files[0]` ou
`media_urls[0]`, fazia um upload e montava `content.media`. As outras fotos
eram descartadas. Além disso, CAROUSEL explícito caía no envio de texto puro.

O fluxo de legenda usa `PlatformPost.effective_caption` completo. Não foi
encontrado slice/truncamento nessa passagem; porém `_build_post_body` enviava
texto bruto para um campo interpretado como little text pelo LinkedIn, sem
escapar os caracteres reservados. Corrigido esse defeito documentado; ainda
falta validar com o post real após implantação para confirmar a causa exata
do texto incompleto observado na VPS.

## Correção

- Faz upload de todas as imagens, na ordem recebida, preferindo arquivos locais.
- Uma imagem mantém `content.media`; 2–20 usam `content.multiImage.images`.
- IMAGE e CAROUSEL seguem esse caminho. Falha em qualquer upload impede criar
  o post final; nunca reduz silenciosamente o conjunto para a primeira imagem.
- Mais de 20 fotos e vídeo enviado como foto de carrossel geram erro explícito.
- Commentary escapa os caracteres reservados conforme little text, sem truncar
  legenda, alterar dados salvos, remover acentos/emoji ou mudar quebras de linha.
- Vale para Personal/Company; não altera OAuth, credenciais, saúde da conta,
  métricas, primeira mensagem/comentário ou demais redes.

Referências oficiais:

- https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/multiimage-post-api?view=li-lms-2026-01
- https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format?view=li-lms-2026-01

## Verificação e implantação

Validação local: **60 testes passaram**, lint dos arquivos alterados limpo e
Django check sem problemas. HTTP e uploads externos foram simulados.

Testes de provider cobrem 2/3/20 imagens, URLs/arquivos locais, IMAGE/CAROUSEL,
ambos conectores, uma imagem, texto longo e caracteres especiais, limite e erro
intermediário. O teste de dispatch passa por Post → anexos ordenados → arquivos
temporários → provider real → payload, com HTTP/upload simulados, incluindo
legenda personalizada. Nenhuma publicação real foi realizada.

Sem migrações ou novas variáveis. Implantar **web e worker** no EasyPanel.
Validar uma nova publicação com várias fotos e texto com parênteses/listas.
Posts já publicados não são modificados automaticamente: repostar cria outro
post, então Rafael deve escolher o que fazer com a publicação antiga.

Carrosséis de fotos/vídeos Instagram foram adiados por Rafael e estão em
`docs/PENDENCIAS_INSTAGRAM.md`; não fazem parte desta correção.
