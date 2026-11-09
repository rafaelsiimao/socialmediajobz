# Seguidores em Insights — 09/11/2026

Rafael apresentou o gráfico com Facebook/LinkedIn zerados e Instagram com variação negativa. A captura não prova que a perda do Instagram seja incorreta, nem revela o erro de coleta específico do LinkedIn na VPS.

## Defeitos confirmados no código e correções locais

- O perfil Facebook consultava somente `id,name,picture` e devolvia o `follower_count=0` padrão. A verificação gravava esse zero no histórico. Agora a tarefa fornece `page_id`, e o provider consulta a página correta com `followers_count`. Resposta sem total ou com ID diferente falha explicitamente; a tarefa preserva o total anterior em caso de falha. O fluxo OAuth de perfil de usuário, sem `page_id`, mantém sua consulta anterior.
- O gráfico inseria o total armazenado como ponto artificial de hoje e usava o total atual mesmo em períodos antigos sem histórico. Agora usa observações reais até o fim do período; total positivo em cache só serve de fallback para um intervalo que inclui hoje, sem inventar linha ou crescimento. Zero sem observação é indisponível; zero com snapshot continua válido.
- O primeiro snapshot encontrado dentro do período era tratado como se fosse o início. Agora a variação exige baseline no início/antes dele e uma observação posterior dentro do intervalo. O resumo não soma dados parciais como se fossem o total de todos os canais.
- Datas de novas observações e o cálculo de hoje seguem o fuso do workspace.
- A página informa data da coleta e problema de conexão por canal. CSS e coordenadas SVG numéricas do gráfico usam ponto decimal, independentemente da localização pt-BR.
- Novo POST `insights:refresh_followers` e botão **Atualizar seguidores**: usuários com `manage_social_accounts` podem enfileirar verificações do workspace ou canal selecionado. Inclui contas em erro para permitir nova tentativa; exclui desconectadas. Redes atendidas: Facebook, Instagram e Instagram Personal, LinkedIn Company. Perfis pessoais LinkedIn não são apresentados como compatíveis com essa coleta. O processamento permanece no worker; recarregar a página após conclusão.

O coletor Company já usa o ID da organização e `networkSizes`, conforme a [documentação oficial LinkedIn](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-lookup-api?view=li-lms-2026-06). Não foi identificado nesta análise um novo defeito específico desse endpoint. A nova atualização permite repetir a coleta; falhas continuam registradas na conexão e não viram total zero.

## Validação

Sete testes novos falharam antes das correções, reproduzindo consulta Facebook, zeros sem coleta, datas históricas, baseline parcial, ID da página e ausência de atualização manual. Depois foram acrescentadas verificações de permissão, isolamento por workspace, resumo parcial e renderização decimal.

55 testes passaram:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_followers_insights.py tests/test_insights.py apps/social_accounts/tests/test_tasks.py tests/test_linkedin_company_metrics.py tests/providers/test_facebook_publishing.py tests/test_facebook_publish_dispatch.py --ds=config.settings.development -q
```

Ruff check, Django check (`config.settings.development`) e `git diff --check` passaram. Somente avisos conhecidos de `staticfiles` ausente nos testes. APIs simuladas, sem coleta real ou publicação. Não foi realizada validação visual em navegador nesta etapa; o template real foi renderizado nos testes Django.

## Estado e operação futura

Correção local, sem commit/push/deploy. As alterações locais anteriores de Insights foram preservadas e estão no mesmo conjunto de arquivos; não descartar seus testes ou o suporte a histórico de conexões com erro. Remotion e plano de carrossel não foram alterados.

Sem migração ou configuração nova. Após envio/implantação autorizados: atualizar web e worker, abrir Insights e clicar **Atualizar seguidores**; aguardar o processamento e recarregar. Verificar em Contas sociais o erro persistido se uma conta continuar sem coleta. Confirmar totais reais de cada rede e período com o usuário. Não recriar ou apagar snapshots antigos: zeros já gravados pela coleta anterior não podem ser reconstruídos com segurança sem dados da plataforma.
