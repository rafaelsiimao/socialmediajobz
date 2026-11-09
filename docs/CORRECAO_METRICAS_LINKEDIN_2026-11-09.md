# Métricas LinkedIn Company — 09/11/2026

Rafael apresentou erro HTTP 400 no modal de desempenho: `Invalid value type for parameter ugcPosts`.

## Diagnóstico e correção local

`LinkedInCompanyProvider.get_post_metrics` passava `List(urn:li:ugcPost:...)` no dicionário `params` do HTTPX. O transporte codificava os delimitadores para `List%28...%29`. Rest.li 2.0 exige `List(...)` literal e o URN codificado dentro dos parênteses.

A consulta agora é montada na URL, codificando os valores e preservando exclusivamente a estrutura da lista. A alteração cobre tanto `ugcPosts` quanto `shares`. Não altera o cliente HTTP compartilhado, tokens, publicação, perfil pessoal ou dados existentes.

Referências oficiais:
- [Versões do protocolo e codificação](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/protocol-version)
- [Estatísticas por publicação da organização](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics?view=li-lms-2026-08)

## Verificação

- Novo teste usa `httpx.MockTransport` e o `_request` real, inspecionando a query recebida pelo transporte. Os dois casos (`share` e `ugcPost`) falharam antes da correção com parênteses codificados, e passaram depois.
- 31 testes passaram: transporte, métricas Company, snapshots/modal de métricas e provider Company. Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_linkedin_metrics_transport.py tests/test_linkedin_company_metrics.py tests/test_post_metrics.py tests/providers/test_linkedin_company.py --ds=config.settings.development -q`.
- O teste usa SQLite local; a primeira tentativa com as configurações padrão de teste foi interrompida porque tentava acessar PostgreSQL indisponível. Execução Python exigiu liberação do sandbox, concedida pela revisão automática.
- Django check com `config.settings.test` sem problemas. Avisos dos testes sobre diretório `staticfiles` local ausente não impediram a execução.
- Sem chamada ao LinkedIn real. A correspondência entre esse defeito e o erro da VPS deve ser confirmada após implantação.

## Implantação futura

Sem migração ou variável nova. Após envio e implantação autorizados, atualizar web e worker, pois ambos utilizam o provider (atualização manual e coleta periódica). Abrir um post Company já publicado, clicar em **Atualizar agora** e confirmar métricas sem o erro 400. Não é necessário republicar nem reconectar a conta para aplicar esta correção de serialização.

O plano de carrossel público continua em `docs/superpowers/plans/2026-11-09-carrossel-preview-publico.md`, ainda sem implementação. Alterações antigas de Insights/Remotion foram preservadas. Nenhum commit, push ou deploy realizado nesta tarefa.
