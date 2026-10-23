# Retomar daqui — Jobz Social Media

Atualizado em 23/10/2026. Rafael pediu este arquivo para continuar em outra
sessão sem recomeçar, pois está com pouco uso disponível.

## Ponto exato em que paramos

Estamos preparando a análise do aplicativo da Meta para permitir que CLIENTES
conectem Facebook e Instagram usando seus próprios perfis. Não estamos
programando uma nova função nem recriando o sistema.

Última tela: **Enviar para a análise do app**. Seções visíveis:

- Verificação (aberta): botão azul **Ir para a verificação**.
- Configurações do app (fechada).
- Uso permitido (fechada).
- Tratamento de dados (fechada).
- Instruções da análise (fechada), com aviso **Precisa da sua análise**.

As seções têm indicadores vazios. A análise ainda NÃO FOI ENVIADA.
Próximo passo de orientação: clicar **Ir para a verificação** e conferir a
próxima tela com Rafael. Não assumir se será verificação empresarial, de
identidade ou outro processo até ver a exigência real do painel.

Captura local dessa última tela, se ainda existir:
`C:/Users/rafae/AppData/Local/Temp/codex-clipboard-b5f26373-723c-4655-a16e-98a17be9e4d8.png`.
O resumo acima é suficiente caso a imagem temporária tenha sido removida.

## Problema que levou à análise

- Facebook e Instagram da Jobz já estavam conectados e funcionando.
- Rafael quer conectar mais duas contas Instagram Business de clientes,
  possivelmente separando marcas em novos workspaces.
- LinkedIn pessoal conectou no novo workspace; Facebook/Instagram não.
- Confirmou que a autorização das contas dos clientes usa OUTRO perfil do
  Facebook, diferente do administrador do aplicativo.
- A Meta exibiu **Recurso indisponível — Como estamos atualizando detalhes
  adicionais para esse aplicativo, o Login do Facebook está indisponível
  para ele no momento. tente novamente mais tarde.**
- A falha exibida ocorre na janela da Meta, antes de selecionar contas no
  sistema. Não foi comprovado que o workspace causa o erro.
- Código conferido: `SocialAccount` é único por workspace/plataforma/ID;
  `_create_or_update_account` também inclui workspace. Não há evidência de
  que seja necessário implementar suporte a workspaces para resolver isso.

## O que foi confirmado no painel Meta

- App se chama **Jobz Social Media**.
- **Ações necessárias**: nenhuma pendência listada.
- **Publicar**: aplicativo já está **Publicado**. Não repetir que falta
  publicar ou prometer que mudar esse status resolverá o login.
- Casos de uso: Gerenciar tudo na sua Página; Gerenciar mensagens e conteúdo
  no Instagram; Interagir com os clientes no Messenger from Meta.
- Permissões estavam como **Pronto para teste**. Isso não comprova acesso
  avançado aprovado para clientes.
- Menu **Ações** de `pages_show_list` oferece **Adicionar à análise do app**.
- **Funções do app → Funções**: Rafael Simão aparece como Administrador.
- O aplicativo aparece gerenciado pelo portfólio **Kleber Alves**.
  Não mudar a titularidade nem assumir que esse nome é a razão social da Jobz.
- Inicialmente sugerimos adicionar o outro perfil como Testador. Rafael
  esclareceu que é um CLIENTE e não um desenvolvedor. A orientação atual é
  preparar análise e acesso adequado para clientes, não exigir função de
  desenvolvedor/testador como solução de produção.
- O texto genérico do erro de login não prova uma causa única; falta de
  permissões para usuários externos é uma hipótese forte, não diagnóstico
  final de todas as possíveis configurações.

## Permissões na solicitação ainda não enviada

A tela anterior **Envios de análise do app → Não enviado → Novas solicitações**
listava exatamente:

```text
pages_read_user_content
pages_manage_posts
pages_show_list
pages_manage_metadata
instagram_manage_comments
pages_messaging
instagram_content_publish
business_management
instagram_manage_messages
pages_read_engagement
public_profile
instagram_manage_insights
instagram_basic
```

Rafael clicou **Avançar**, chegando à tela atual. Não concluir que a análise
está submetida/aprovada. A lista inclui publicação, mensagens, comentários e
métricas. Antes de finalizar, conferir no código e na interface quais recursos
realmente funcionam e são necessários. Não inventar justificativas, resultados
ou vídeos de recursos não demonstráveis. Se reduzir escopo da solicitação,
conferir também os scopes pedidos pelo OAuth; não deixar o login pedindo
permissões indisponíveis. Nenhuma dessas mudanças foi autorizada/executada
apenas pela criação deste arquivo.

## Status da Meta e LinkedIn (atualizado depois)

- Meta: Rafael iniciou a **Verificação da empresa** (portfólio Kleber Alves,
  CNPJ informado por Rafael). Meta pediu aguardar até 48h. Aprovação não
  confirmada. Não enviar a análise do app antes da verificação ser aprovada.
- Enquanto isso: conferir política de privacidade e URL de exclusão de dados
  (Rafael usa os termos do site oficial), definir permissões reais e
  preparar roteiro/vídeo da análise.
- LinkedIn: app "Jobz 2 Social" com associação à empresa Grupo Jobz
  aprovada. Community Management API ainda em "Access Form Review"
  (1 de 2); pode haver pedido de documentos por e-mail em 10 a 14 dias úteis.

## Andamento das funcionalidades

- Cor: feita, commit `64d40f1`, implantada por Rafael.
- Publicados no calendário: já existia no código (selo verde), nada alterado.
- Analytics dos posts publicados pelo sistema: implementado localmente
  (Instagram e Facebook). Modelo `PlatformPostMetrics` (migração composer
  0017), serviço `apps/composer/metrics.py`, tarefa recorrente a cada 3h
  (`refresh_post_metrics`, registrada no post_migrate), últimos 90 dias.
  Coluna "Desempenho" na aba Enviados e tooltip nos chips do calendário.
  Providers atualizados: Instagram usa `reach, views, likes, comments,
  shares, saved, total_interactions` (impressions/engagement foram
  descontinuadas) com fallback para `like_count/comments_count`; Facebook
  lê só reações/comentários/compartilhamentos do post (insights exigem
  `read_insights`, que o app não pede). 166 testes passaram, lint ok.
  Sem teste com token real. Exige deploy de web E worker (migração).
  Commit `44ea419`.
- Modal de post publicado: clicar num post publicado (calendário ou aba
  Enviados) abre prévia somente leitura + desempenho + "Atualizar agora" +
  link "Ver na rede social" (permalink). Rotas `calendar:published_post_detail`
  e `published_post_refresh_metrics`. Conferido no navegador com banco
  temporário; 169 testes passaram.
  Commit `863034c`.
- Ajustes do modal: desempenho no topo, carrossel com setas e pontos (um
  slide por vez), legenda em 2 linhas com "Ver completa". Erro do Facebook
  "nonexisting field (shares)" corrigido: posts com foto guardavam o ID da
  foto; agora a publicação guarda o `post_id` do feed e as métricas resolvem
  `page_story_id` para posts antigos (fallback sem `shares` para vídeos).
- **Facebook desativado no desempenho (corrigir depois):** mesmo após o
  deploy, log da VPS mostrou `Facebook API error 400: (#100) Tried accessing
  nonexisting field (shares)` (PlatformPost 24564af8-...). Não confirmado se
  o log era de antes ou depois do deploy de `bce81ff`. `METRICS_PLATFORMS`
  em `apps/composer/metrics.py` ficou só com `instagram`; modal do Facebook
  mostra "Métricas ainda não disponíveis". Para retomar: descobrir que tipo
  de objeto é o ID salvo (GET `/{id}?metadata=1` com token da página),
  ajustar `providers/facebook.py` e voltar `facebook` à lista.
- **Inbox (implementado localmente):** a sincronização nunca rodava na VPS
  (só existia o comando `run_inbox_sync`, processo separado). Agora é a
  tarefa recorrente `run_inbox_sync_cycle` (5 min) registrada no
  post_migrate do app inbox, rodando no worker. Primeira sincronização de
  cada conta importa 30 dias sem notificar. Instagram: comentários das 25
  mídias recentes + DMs via `/{page_id}/conversations?platform=instagram`
  com token da Página; resposta a comentário (`/{comment}/replies`) e a DM
  (`/{page_id}/messages`, janela de 24h). Scopes adicionados ao login do
  Instagram: `instagram_manage_messages` e `pages_manage_metadata`; exige
  RECONECTAR a conta Instagram após o deploy. DMs também exigem ativar no
  app do Instagram "Ferramentas conectadas / Permitir acesso às mensagens"
  e, segundo a doc da Meta, empresa verificada. Sem teste com conta real.
- Inbox: bug das mensagens exibidas como avisos azuis no topo corrigido
  (`89a20ea`, contexto usava a chave `messages` do Django).
- **Futuro: reformular o Inbox no estilo "Community" do Buffer** (Rafael
  enviou captura de referência; adiado a pedido dele). Escopo combinado:
  abas Comentários / Mensagens com contagem; coluna esquerda com posts
  (conta, início da legenda, miniatura, nº de comentários, barra
  respondidos/total); painel direito com cabeçalho do post, "X respondidos /
  Y comentários" e comentários em sequência, cada um com caixa de resposta
  inline já com `@usuario`, sugestões rápidas ("Obrigado, @x! 🙌", "Valeu
  demais! 😊") e botão de resolver. DMs agrupadas por conversa. Tudo em
  português. Por trás: sync deve guardar `media_url`/`thumbnail_url`/
  `timestamp` da mídia no `extra` (hoje guarda `media_id`, `permalink`,
  `media_caption`). "Respondido" = tem `InboxReply` ou status resolvido.
  Fora do escopo inicial: Menções (webhooks) e comentários do Facebook.
- **Stories no Instagram (implementado localmente):** seletor "Formato:
  Feed / Story" por conta Instagram no Composer (`ig_format_<id>`), salvo
  como `platform_extra.post_type = "story"` (save_post e autosave). Story
  remove colaboradores e desativa o campo; Story + colaboradores → 400.
  Provider: Story sem legenda, exatamente 1 mídia, detecção de vídeo
  ignorando query string de URL assinada (vale também para carrossel).
  Primeiro comentário não é enviado em Story. Sem publicação real testada.
  "Compartilhar post do feed nos Stories" (cartão nativo) continua fora.
  Commit `d43c557`.
- **Prévia de Story e sequência (implementado localmente):** com Story
  selecionado, a prévia do Composer vira um Story 9:16 (barras de
  progresso por mídia, toque nas laterais para navegar). Sequência: cada
  mídia vira um Story, publicados em ordem (1 a 10). O provider cria e
  processa todos os contêineres antes de publicar (falha de mídia = nada
  publicado, retry seguro); se falhar no meio da publicação, marca como
  publicado com `story_ids` e `story_errors` para não duplicar no retry.
  Métricas usam só o primeiro Story da sequência.
- Commit `901d059` (prévia de Story e sequência).
- **Futuro: página "Início" no estilo Buffer** (Rafael enviou 2 capturas
  da Home do Buffer em 23/10/2026; só plano, nada implementado). Hoje,
  após login, `apps/accounts/views.py:dashboard` redireciona direto para o
  calendário; não existe página inicial do workspace.
  Blocos da referência e como fazer aqui:
  1. Saudação + data ("Boa tarde, Nome!" + data por extenso). Simples.
  2. Faixa de indicadores (3 círculos):
     - Sequência semanal: semanas seguidas com ≥1 post publicado
       (`PlatformPost.published_at`). Sem migração. O selo "Top 15%" do
       Buffer compara com outros usuários: não temos base, omitir.
     - Metas de publicação: "1 de 3 metas atingidas". Precisa modelo novo
       de meta por workspace (ex.: N posts/semana por rede) + migração +
       tela simples para definir metas.
     - Pontuação de comentários: no Buffer é métrica própria. Proposta:
       % de comentários respondidos nos últimos 7 dias vs semana anterior
       (Inbox: `InboxMessage` + `InboxReply`/status resolvido).
  3. "Pulso da semana" (semana atual vs anterior): Posts publicados
     (contagem, sem migração); Total de seguidores (soma de
     `SocialAccount.follower_count`, já atualizado a cada 6h; a variação
     semanal exige histórico → modelo `FollowerSnapshot` diário +
     migração); Comentários recebidos (Inbox).
  4. Últimos rascunhos: 3 cards com rede, início da legenda e miniatura
     (Posts em rascunho; já existe, só listar). Clique abre o Composer.
  5. "A seguir": próximos agendados (PlatformPost `scheduled`), com estado
     vazio "Nenhum post agendado" + botão Criar post.
  6. Comentários sem resposta: lista curta do Inbox com @usuário e texto;
     clique leva ao Inbox. Depende da sincronização do Inbox.
  7. Modelos: 4 cards de ideias/modelos (já existem `PostTemplate` e
     `apps/composer/builtin_templates.py`); clique abre o Composer com o
     modelo. Textos em português, adaptados à Jobz.
  8. "Do blog": conteúdo externo do Buffer. Sugestão: omitir ou trocar
     por algo interno (ex.: melhores horários dos `PostingSlot`). Não
     assumir que a Jobz tem blog/feed sem confirmar com Rafael.
  Menu lateral: adicionar item "Início" no topo; o login passa a abrir o
  Início em vez do calendário.
  Ordem sugerida: (a) página + blocos sem migração (1, 2a, 3 posts/
  comentários, 4, 5, 6, 7); (b) histórico de seguidores; (c) metas de
  publicação; (d) pontuação de comentários. Tudo em português.
- Pendentes: importação do histórico do Instagram, reformulação do Inbox,
  página Início, correção das métricas do Facebook.

## Novas funcionalidades planejadas (ordem combinada)

1. Trocar cor `#F7F6F2` por `#F1F4F7`: `--surface-page` em
   `theme/static_src/src/styles.css`. Exige build Tailwind e deploy do web.
2. Mostrar publicações já publicadas no calendário (filtro de status
   `published`). Sem migração nem Meta.
3. Postar Stories: Instagram tem código inicial (`providers/instagram.py`);
   falta oferecer no Composer, validar 9:16 e testar. Facebook Stories
   não coberto. Opção "publicar também como Story" gera um Story novo com a
   mesma mídia; o cartão clicável do feed NÃO está confirmado na API.
4. Importar histórico: Rafael publicou direto no Instagram, então o sistema
   não conhece esses posts. Importar via `/{ig-user-id}/media` (tarefa no
   worker, migração para marcar importados e evitar duplicata). Só contas
   Business via Facebook. Stories expirados não são listados. Decidir se
   guarda cópia da mídia.
5. Analytics: `get_post_metrics`/`get_account_metrics` já existem nos
   providers Instagram e Facebook, mas nada os chama. Falta modelo
   (migração), tarefa periódica e tela, no calendário e por publicação.
   Precisa de `instagram_manage_insights`. Para clientes, depende da
   aprovação da Meta.

## Como continuar com Rafael

1. Ler este arquivo e `CONTEXTO_PARA_IA.md`; não reiniciar as perguntas já
   respondidas acima.
2. Orientar uma etapa por vez, com os nomes visíveis no painel, em português
   simples. Aguardar a captura da etapa seguinte quando necessária.
3. Conferir a verificação exigida, depois configurações, usos permitidos,
   tratamento de dados e instruções para os revisores.
4. Ajudar a preparar justificativas e demonstrações com base no comportamento
   real do produto. Não presumir URLs de privacidade/exclusão, documentos da
   empresa, domínio verificado ou práticas de dados inexistentes.
5. Não submeter análise, enviar mensagens/e-mails, alterar configurações
   externas ou publicar conteúdo apenas com base nesta passagem de trabalho.
   O pedido atual foi preparar este arquivo. Revisar a autorização vigente
   quando Rafael pedir o próximo trabalho.
6. Consultar documentação oficial atual da Meta quando precisar afirmar
   requisitos. Não prometer prazo nem aprovação. As páginas da Meta às vezes
   retornam HTTP 429 às ferramentas; comunicar limites de verificação.

## Projeto, implantação e segurança

- Pasta: `C:/Users/rafae/OneDrive/Documentos/ChatGPT/app socialmedia/brightbean-socialmediastudio`.
- GitHub: https://github.com/rafaelsiimao/socialmediajobz — branch `main`.
- HEAD local ao preparar esta passagem: `afe9f47` (LinkedIn pessoal com OIDC).
  Árvore limpa antes de criar/atualizar estes documentos. Conferir Git novamente
  na sessão seguinte; podem existir alterações posteriores de Rafael/outra IA.
- Site: https://socialmedia-web.hqzarv.easypanel.host
- Django/templates/HTMX/Alpine/Tailwind; PostgreSQL em produção.
- EasyPanel: banco `socialmedia`, aplicações `web` e `worker`.
- Worker usa `python manage.py process_tasks` (não Celery).
- Mídias compartilhadas/persistentes: host `/opt/socialmediajobz/media`
  montado em `/app/media` no web e worker. Usuário confirmou funcionamento.
- Código enviado ao GitHub não comprova implantação; Rafael implanta no
  EasyPanel. Não mexer em banco/tokens/uploads/chaves existentes.
- Segredos ficam no EasyPanel. Não pedir para mostrar App Secret/Client Secret,
  não comitar `.env`, banco, uploads ou credenciais.
- OAuth Meta usa callbacks sem workspace na URL:
  `/social-accounts/callback/facebook/` e `/social-accounts/callback/instagram/`.
  O workspace vai no estado OAuth assinado. Não adicionar redirects por workspace.

## Outras frentes — não confundir com a tarefa Meta atual

- Colaboração no Instagram implementada: até três perfis por publicação,
  persistência em rascunho/autosave/aprovação e payload no provider.
- Prévia corrigida: `hx-vals='js:{...getPreviewVals()}'`.
- LinkedIn pessoal: usuário confirmou conexão funcionando. Usa `openid`,
  `profile`, `w_member_social` e `/v2/userinfo`.
- LinkedIn Company: ainda depende das permissões/aprovação da Community
  Management API. Rafael excluiu um app anterior e refez a solicitação.
  A última captura mostrou **Thank you**, confirmação de envio e **100%**.
  Aguarda verificação por e-mail **Microsoft Vetting Services** e decisão;
  não há aprovação confirmada. Não confundir com o app da Meta.
- Música e compartilhar a publicação do feed nos Stories foram discutidos,
  mas não implementados. Nova postagem em Story não equivale ao cartão nativo
  clicável de compartilhamento do feed.
- Aprovação com seletor de revisor já existe; e-mail via Gmail funcionou.
- Última validação de código nesta conversa: 145 testes de providers/contas
  sociais/OAuth passaram após o ajuste LinkedIn pessoal. Não equivale a
  autorização/publicação real nas redes.

## Mensagem sugerida para começar a próxima sessão

“Li a passagem de trabalho. Paramos em ‘Enviar para a análise do app’, com a
seção Verificação aberta. Clique em ‘Ir para a verificação’ e me mostre a tela
seguinte para continuarmos sem refazer o que já foi feito.”
