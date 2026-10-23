# Análise do app Meta — textos para "Uso permitido"

Textos em inglês, porque a equipe de análise da Meta costuma ler em inglês.
Cada texto descreve só o que o sistema faz hoje (conferido no código em
23/10/2026). Cole o texto no campo de descrição de cada permissão, envie o
mesmo vídeo (roteiro no fim) e marque o aceite.

Não incluir permissões que não serão demonstradas no vídeo.

---

## instagram_basic

Jobz Social Media is a social media management tool used by our team and our
clients to plan, approve, publish and analyze content on their own Instagram
Business/Creator accounts. We use instagram_basic to read the connected
account's profile (username, name, profile picture and follower count) so the
user can confirm which account was connected and see it in the channel list.
We also read the account's media list (caption, media type, thumbnail,
permalink, timestamp, like and comment counts) to show the posts the user
published in our content calendar and performance reports. Without this
permission the user could not connect the account or see their own published
content in the app.

## instagram_content_publish

We use instagram_content_publish to publish content that the user creates and
schedules in our composer to their own Instagram Business/Creator account:
single photos, carousels, Reels and Stories (one or more Stories in sequence).
The user chooses the account, format, media and caption, optionally adds
collaborators, and the post is published at the scheduled time. This is the
core function of the app: it lets teams plan and approve content in one place
and publish it without posting manually.

## instagram_manage_comments

We use instagram_manage_comments to show comments left on the user's own
Instagram posts in our unified Inbox and to let the user reply to them from
the app. It is also used to publish an optional "first comment" that the user
writes in the composer right after the post is published. This lets the team
answer its audience without switching between tools.

## instagram_manage_insights

We use instagram_manage_insights to read performance metrics of the user's own
Instagram posts (reach, views, likes, comments, shares, saves and total
interactions). The app shows these numbers in the post preview, in the
"Insights" page (period summary, top posts, performance per channel) and in a
CSV export, so the user can understand which content performs best.

## instagram_manage_messages

We use instagram_manage_messages to show the Direct Messages received by the
user's own Instagram professional account in our unified Inbox and to let the
user reply to them from the app, within Instagram's 24-hour messaging window.
Messages are only read from accounts the user connected and are used only to
reply to the people who wrote to the business.

## pages_show_list

We use pages_show_list to list the Facebook Pages the user manages during the
connection flow, so the user can choose which Page (and the Instagram
professional account linked to it) to connect to the app. It is also used to
find the Page linked to an Instagram account in order to read its Instagram
Direct Messages.

## pages_read_engagement

We use pages_read_engagement to read the content and basic data of the Pages
the user connected (Page name, picture and the posts published through the
app), which is required to obtain the Page access token and to identify the
Instagram professional account linked to the Page. Without it the user could
not connect their Page or Instagram account.

## pages_manage_posts

We use pages_manage_posts to publish posts that the user creates and schedules
in our composer (text, links, photos and videos) to the Facebook Page they
manage and connected to the app, at the time they choose.

## pages_manage_metadata

We use pages_manage_metadata, together with instagram_manage_messages, to
access the messaging data of the connected Page and its linked Instagram
professional account so that Direct Messages can be shown and answered in our
Inbox. It is required by Meta for the Instagram messaging integration.

## pages_messaging

We use pages_messaging to show the Messenger conversations of the Page the
user connected in our unified Inbox and to let the user reply to people who
messaged the Page, within the standard messaging window.

## business_management

We use business_management so that users whose Pages and Instagram accounts
are owned by a Business portfolio (common for companies and agencies) can see
and connect those assets during the connection flow. Without it, assets that
belong to a Business portfolio would not appear for the user to connect.

## public_profile

Granted by default with Facebook Login. We use the user's name to identify who
connected the account inside the app.

---

## Pontos de atenção antes de enviar

- **pages_read_user_content:** o código pede essa permissão, mas hoje o
  sistema não mostra comentários de Páginas do Facebook (as métricas do
  Facebook estão desativadas). Difícil demonstrar no vídeo. Recomendação:
  remover da solicitação e do login do Facebook, ou reativar a leitura de
  comentários do Facebook antes de pedir.
- **Threads:** decisão pendente do Rafael. Se incluir, é preciso conectar e
  testar uma conta Threads na VPS antes de gravar o vídeo.
- **Chamadas de teste de API:** cada permissão precisa aparecer como
  "Concluída". Elas são marcadas quando o app usa a permissão de verdade
  (até 24 h para aparecer).

## Roteiro do vídeo (um vídeo serve para todas as permissões)

Gravar a tela na VPS, com legenda ou narração em inglês, mostrando:

1. Login no Jobz Social Media.
2. **Conectar conta:** clicar em conectar Instagram → janela do Facebook
   Login (mostrar a tela de permissões) → escolher a Página e a conta
   Instagram → conta aparece conectada com nome e foto.
   (instagram_basic, pages_show_list, pages_read_engagement,
   business_management, public_profile)
3. Repetir para conectar a Página do Facebook. (pages_manage_posts)
4. **Composer:** criar um post de foto no Instagram com legenda e primeiro
   comentário, e um Story; publicar agora. Mostrar o post publicado no app do
   Instagram. (instagram_content_publish, instagram_manage_comments)
5. Publicar um post na Página do Facebook e mostrar na Página.
   (pages_manage_posts)
6. **Inbox:** mostrar um comentário do Instagram e responder; mostrar uma DM
   do Instagram e responder; mostrar uma conversa do Messenger e responder.
   (instagram_manage_comments, instagram_manage_messages,
   pages_manage_metadata, pages_messaging)
7. **Insights / prévia do post:** abrir um post publicado e mostrar alcance,
   visualizações e curtidas; abrir a página Insights. (instagram_manage_insights)
