# Company Page pedindo reconexão rapidamente — 09/11/2026

Rafael relatou que, após conectar a Company Page, recarregar ou trocar de workspace fazia aparecer **Reconectar**. Informou que não viu mensagem de erro. Não houve acesso a logs, banco ou APIs da VPS; o erro específico de produção não foi confirmado.

## Defeitos reproduzidos localmente

1. `get_profile()` Company consultava organização e seguidores como uma única operação obrigatória. Se a organização respondesse, mas `networkSizes` falhasse (403, limite, timeout, 5xx, campo ausente), a tarefa colocava a conexão em `error`. O menu mostra **Reconectar** para esse status. GET/recarregamento e troca de workspace apenas consultam o status persistido; não revogam o token nesses caminhos.
2. A tarefa carregava o objeto antes das chamadas de rede e depois salvava todos os campos, incluindo token. Uma reconexão concluída enquanto essa tarefa aguardava a API podia ser sobrescrita pelo objeto antigo, restaurando o token anterior e/ou status de erro. Um teste reproduziu a substituição do token novo pelo antigo.

## Correção local

- Falha opcional de seguidores, após leitura bem-sucedida da organização, retorna `follower_count=None` e aviso em `extra`. Não converte ausência em zero, nem falha de métricas em perda de autenticação. HTTP 401 continua propagando erro.
- A tarefa preserva o último total, não grava snapshot fictício e mantém a conexão disponível quando somente a coleta falha. O aviso aparece no cartão da conta, inclusive quando conectada, com texto completo.
- Falhas transitórias na leitura da organização (timeout, limite, 408/5xx) preservam o estado anterior da Company se há token e ele não está vencido segundo a data armazenada. Não recuperam automaticamente uma conta já em erro. HTTP 401 e 403 da própria organização continuam exigindo atenção.
- O LinkedIn distingue autenticação inválida (401), permissão (403), limite (429) e indisponibilidade (5xx) na [documentação oficial de erros](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/error-handling). Preservar uma conexão em falha transitória não garante que a publicação será aceita: publicação e coleta continuam podendo retornar seus próprios erros reais.
- A gravação final da verificação é atômica, com lock e comparação de `updated_at`. Se a conta mudou, foi reconectada ou removida durante a chamada, o resultado antigo é descartado, inclusive o snapshot. Uma tarefa iniciada para uma conta já desconectada também é ignorada.
- O contrato Python `AccountProfile.follower_count` passa a aceitar `None`; isso não altera o modelo do banco. O upsert OAuth omite o total ausente para preservar dados existentes e o default de novas contas.

## Validação

Oito casos falharam antes da correção e passaram depois; controles de autenticação real já exigiam reconexão antes e continuam assim. A bateria final passou com **86 testes**, cobrindo falhas de métricas, 401/403 da organização, erros temporários, expiração, concorrência com reconexão, ausência de snapshot antigo, zero confirmado, recuperação e limpeza de aviso, renderização do aviso, recarregamento/troca de workspace, OAuth e Insights.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_linkedin_company_health.py tests/test_linkedin_company_metrics.py tests/test_linkedin_metrics_transport.py tests/providers/test_linkedin_company.py tests/providers/test_linkedin_personal.py apps/social_accounts/tests/test_tasks.py apps/social_accounts/tests/test_models.py tests/test_followers_insights.py tests/test_insights.py --ds=config.settings.development -q
```

Ruff check nos arquivos alterados, Django check (`config.settings.development`) e `git diff --check` passaram. Avisos conhecidos de diretório `staticfiles` ausente. APIs simuladas; não houve revogação, publicação, reconexão ou coleta real. Houve uma execução intermediária com dois testes de transporte bloqueados por uma fixture de teste promovida indevidamente a plugin global; a fixture nova foi isolada no módulo, e a bateria final completa passou.

## Entrega e confirmação futura

Sem commit/push/deploy nesta etapa. Sem migração/env nova. Após envio autorizado, implantar **web + worker**; ambos precisam conter a correção para que um worker antigo não continue gravando estados incorretos. Não há alteração automática em contas de produção já marcadas com erro: fazer uma nova verificação em **Insights → Atualizar seguidores** ou reconectar uma vez depois do deploy. Recarregar, alternar workspace e conferir status/aviso na página de contas sociais. Se persistir, coletar o texto do erro real sem tokens; os defeitos reproduzidos não provam qual ocorreu na VPS.

Remotion, plano do carrossel e documentação histórica anterior permanecem preservados e separados.
