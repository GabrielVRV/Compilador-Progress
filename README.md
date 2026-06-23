# 🚀 ABL Deploy CLI

Deploy para **Progress OpenEdge (ABL)** — e para o **frontend** — sem sair de um menu.

Configura uma vez e depois é só abrir o menu e escolher o que fazer:

```bash
abl-deploy
```

```
? O que você quer fazer?
  ❯ Compilar e enviar ABL
    Enviar frontend (uma vez)
    Observar frontend (watch, auto-envio)
    Configurar (assistente)
    Sair
```

Acaba com o ritual manual de abrir o App Builder pra compilar e o WinSCP pra
arrastar arquivo — tanto o `.r` do ABL quanto os arquivos de tela do frontend.

## O que ela faz

- **ABL**: compila o fonte (`_progres` em batch) e envia o `.r` via SFTP.
- **Frontend**: envia os arquivos estáticos (html/js/css/…) via SFTP, sem compilar.
- **Watch**: observa a pasta do frontend e **envia sozinho a cada vez que você salva**.
- **Assistente**: configura tudo respondendo perguntas — sem editar arquivo na mão.
- **Vários projetos** e **vários ambientes** (dev/staging/prod) num só lugar.
- **Roteamento por nome**: `*rp.p` vai pra uma pasta, `*.p` pra outra.

## Stack

`typer` (CLI) · `rich` (output) · `questionary` (menu) · `paramiko` (SFTP, no lugar do
WinSCP) · `watchdog` (watch) · config em `.toml`.

## Instalação

Requer Python 3.9+ e, para compilar ABL, o OpenEdge instalado.

```bash
git clone https://github.com/GabrielVRV/Compilador-Progress.git
cd Compilador-Progress
pip install -e .
```

## Uso

Na prática, só isto:

```bash
abl-deploy
```

Na primeira vez ele abre o assistente, você responde host, pastas, etc., e pronto.
Depois é só rodar `abl-deploy` e escolher a ação no menu.

### Watch do frontend (a parte que mais economiza tempo)

Escolha "Observar frontend" (ou `abl-deploy watch -e dev`). Ele faz um envio
inicial e fica observando a pasta: salvou um arquivo no editor, ele sobe na hora,
mantendo a conexão SFTP aberta. `Ctrl+C` para parar.

### Comandos (para quem prefere linha de comando)

| Comando | Faz |
|---|---|
| `abl-deploy` | abre o menu (recomendado) |
| `abl-deploy config` | assistente de configuração |
| `abl-deploy deploy escq9986rp.p -e prod` | compila e envia um fonte ABL |
| `abl-deploy frontend -e dev` | envia o frontend uma vez |
| `abl-deploy watch -e dev` | observa o frontend e auto-envia ao salvar |
| `abl-deploy projects` / `envs` | lista projetos / ambientes |

Opções comuns: `--env/-e` (ambiente), `--project/-p` (projeto), e no `deploy`
ainda `--compile-only` e `--skip-compile`.

## Configuração

O assistente grava o `.toml` pra você, mas o formato é simples e dá pra editar à mão.
A CLI procura, nesta ordem: a variável `ABL_DEPLOY_CONFIG`, um `abl-deploy.toml`
local, e por fim `~/.abl-deploy.toml` (global, para vários projetos).

```toml
[project.financeiro]
source_dir  = "C:/projetos/financeiro/src"
source_dirs = ["C:/projetos/financeiro/src/telas", "C:/projetos/financeiro/src/rp"]
build_dir   = "C:/projetos/financeiro/build"

[project.financeiro.env.dev]
host = "dev.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/dev/rcode"

# .r da tela e do "rp" vão para pastas diferentes:
[[project.financeiro.env.dev.routes]]
match = "*rp.p"
remote_dir = "/u/app/dev/rp"

[[project.financeiro.env.dev.routes]]
match = "*.p"
remote_dir = "/u/app/dev/telas"

# Frontend (enviado sem compilar; use o watch):
[project.financeiro.env.dev.frontend]
local_dir = "C:/projetos/financeiro/web"
remote_dir = "/u/app/dev/web"
include = ["*.html", "*.js", "*.css", "*.png"]   # vazio = tudo
```

Exemplo completo em [`abl-deploy.example.toml`](abl-deploy.example.toml).

### Credenciais com segurança

Use **chave SSH** (`key_file = "~/.ssh/id_rsa"`) ou **variável de ambiente**
(`password = "env:ABL_PROD_PASS"`). O `abl-deploy.toml` real está no `.gitignore`.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [x] Menu interativo como hub central
- [x] Assistente de configuração
- [x] Vários projetos / ambientes
- [x] Roteamento do `.r` por nome do arquivo
- [x] Envio de frontend + modo watch (auto-envio ao salvar)
- [ ] Envio só de arquivos alterados (hash/manifest)
- [ ] Deploy de múltiplos fontes ABL de uma vez
- [ ] `--dry-run`

## Licença

MIT — veja [LICENSE](LICENSE).
