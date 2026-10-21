# Teste local no Windows

Na pasta do repositorio, execute no PowerShell:

```powershell
.\start-local.ps1
```

Abra http://127.0.0.1:8000. Para encerrar:

```powershell
.\stop-local.ps1
```

O ambiente usa `.venv`, SQLite (`db.sqlite3`) e arquivos em `media/`.
Os logs ficam em `media/.local/`. O email aparece no console/log local.
O CSS ja esta compilado; apos alterar estilos, execute `npm.cmd run build`
na pasta `theme/static_src`.

Credenciais das redes sociais nao foram configuradas. FFmpeg e necessario
para recursos de processamento de video; nao esta incluido neste ambiente.

Esta configuracao e apenas para testes. Na VPS, configure PostgreSQL,
HTTPS, email e segredos proprios, seguindo a configuracao de producao.
