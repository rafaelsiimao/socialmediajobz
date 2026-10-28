# Story exclusivo do Instagram

Especificação aprovada na conversa: Story não usa legenda nem primeiro
comentário; não pode ser combinado com Post, Reel ou outras redes. Post e Reel
mantêm comportamento. Ao voltar de Story para outro formato, preservar texto.

Implementar no compositor existente, sem migração nem mudança dos providers.

- [x] Testes de salvar/autosalvar seleção inválida sem alterar dados;
  Instagram/Instagram Personal, texto efetivo, prévia e aprovação externa.
- [x] Validador de seleção compartilhado entre POST e GET; considerar formato
  já salvo quando um pedido não enviar o campo. Apenas seleções com Story
  recebem a restrição de mistura.
- [x] Propriedade is_instagram_story e texto efetivo vazio apenas nesses alvos;
  preservar texto bruto do rascunho para retorno a Post/Reel. Publisher já usa
  effective_caption/effective_first_comment, inclusive tarefa de comentário.
- [x] Estado Story no Alpine; ocultar texto, contador, modelos, personalização
  e comentário sem esconder/remover DOM de mídia. Conflito visível e bloqueio
  de submit/autosave. Contas não selecionadas não definem modo Story.
- [x] Prévia sem contador/legenda/comentário e aprovação por link só com mídias
  para Story. Não alterar apresentação/textos de Post/Reel.
- [x] Testes de navegador com Alpine real: ida/volta dos três formatos,
  retenção de texto/mídias/ordem e conflito; regressões existentes.

Múltiplas contas Instagram são compatíveis somente se todas usarem Story.
Qualquer outro formato/rede na mesma seleção bloqueia salvar/enviar; não mudar
formatos de outras contas nem remover seleções automaticamente.
