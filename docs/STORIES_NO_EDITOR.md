# Stories no editor

Ao escolher Story para uma conta Instagram (inclusive Instagram Personal),
o editor mostra **Mídias do Story** e mantém upload, biblioteca e ordenação.
Legenda, contador, modelos, personalização de texto e primeiro comentário
ficam ocultos. O texto bruto continua no rascunho: ao voltar para Post ou Reel,
os campos e seus valores reaparecem. Mídias e ordem não são apagadas.

Uma publicação com Story só aceita contas Instagram também configuradas como
Story. Se houver Post, Reel ou outra rede, a interface mostra o conflito e
bloqueia salvar/enviar e autosalvar até corrigir a seleção. O servidor também
rejeita a combinação antes de alterar o rascunho; considera formatos salvos
quando o pedido não os envia ou envia um valor desconhecido. Não altera os
formatos de outras contas nem remove seleções automaticamente.

Prévia e link público de aprovação de Story não mostram legenda, primeiro
comentário ou contador. No worker, `effective_caption` e
`effective_first_comment` retornam vazio somente para Instagram Story,
inclusive em tarefas de comentário já enfileiradas. Textos brutos e overrides
continuam armazenados. Post e Reel usam os campos como antes.

## Implantação e validação

- Implantar **web e worker**; não há migração nem nova variável de ambiente.
- Atualizar o navegador com Ctrl+F5 após o deploy.
- 91 testes passaram: seleção, rascunhos existentes, prévia, aprovação externa,
  Instagram/Instagram Personal, colaboração, Reel e ordenação de carrosséis.
- Teste Edge headless com HTML completo do editor e Alpine/HTMX reais confere
  Story → Reel → Post, retenção de textos e ordem da mídia e bloqueio de salvar
  e autosalvar uma combinação incompatível. Todos os dados são fictícios.
- Django check e makemigrations composer --check --dry-run passaram. Nenhuma
  publicação ou chamada real à API das redes durante os testes.

Teste de navegador em `tests/browser/story-composer.cjs`; instruções de exportar
o HTML fictício estão no início do script. Exportações ficam em media/.local,
ignoradas pelo Git. A validação real na VPS ocorre após a implantação.
