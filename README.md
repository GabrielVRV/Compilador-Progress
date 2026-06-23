# 🚀 ABL Deploy CLI

Pipeline de deploy para **Progress OpenEdge (ABL)** em um único comando.

```bash
abl-deploy deploy escq9986rp.p --env prod
```

A CLI faz todo o fluxo que hoje é manual no App Builder + WinSCP: **compila** o
fonte, gera o `.r`, e **envia via SFTP** para o servidor do ambiente escolhido.

---

## Por que existe

No dia a dia com OpenEdge, publicar uma alteração costuma ser: abrir o editor,
compilar pelo App Builder, achar o `.r`, abrir o WinSCP, arrastar pro servidor
certo. É manual, repetitivo e fácil de errar de ambiente. A `abl-deploy`
transforma isso em um comando versionável e reproduzível.

## Stack

| Camada        | Ferramenta                          |
|---------------|-------------------------------------|
| CLI           | [`typer`](https://typer.tiangolo.com) |
| Output        | [`rich`](https://rich.readthedocs.io) (spinner, barra de progresso, cores) |
| Compilação    | `subprocess` chamando `_progres -b` com um `compile.p` |
| Deploy        | [`paramiko`](https://www.paramiko.org) (SFTP, substitui o WinSCP) |
| Config        | arquivo `.toml` com ambientes `dev` / `staging` / `prod` |

## Como funciona

```
abl-deploy deploy fonte.p --env prod
        │
        ├─ 1. carrega o ambiente do abl-deploy.toml
        ├─ 2. _progres -b -p compile.p  →  gera build/fonte.r
        └─ 3. paramiko SFTP  →  envia o .r para o remote_dir do ambiente
```

A compilação roda o template [`compile.p`](abl_deploy/templates/compile.p), que
faz `COMPILE ... SAVE INTO` e devolve `COMPILE-OK` ou as mensagens de erro do
compilador ABL, capturadas e exibidas pela CLI.

## Instalação

Requer Python 3.9+ e um ambiente com o OpenEdge instalado (para o passo de
compilação).

```bash
git clone https://github.com/GabrielVRV/Compilador-Progress.git
cd Compilador-Progress
pip install -e .
```

## Uso

### Menu interativo (mais fácil)

Rode sem argumentos e siga as setas:

```bash
abl-deploy
```

Ele pergunta: **projeto → ambiente → ação → fonte** (listando os `.p` das suas
pastas) → confirma → compila e envia.

### Por comando

```bash
abl-deploy init               # cria abl-deploy.toml (projeto único)
abl-deploy init --global      # cria ~/.abl-deploy.toml (vários projetos)
abl-deploy projects           # lista os projetos
abl-deploy envs               # lista os ambientes
abl-deploy deploy escq9986rp.p --env prod
abl-deploy deploy escq9986rp.p --env prod --project financeiro
```

Opções do `deploy`:

| Flag               | Efeito                                            |
|--------------------|---------------------------------------------------|
| `--env / -e`       | ambiente alvo (obrigatório)                       |
| `--project / -p`   | projeto (se houver mais de um na config)          |
| `--compile-only`   | só compila, não envia                             |
| `--skip-compile`   | envia um `.r` já existente em `build_dir`         |
| `--version`        | mostra a versão                                   |

## Configuração

### Um projeto

`abl-deploy.toml` na pasta do projeto, com `[default]` (vale para todos os
ambientes) e um bloco `[env.<nome>]` por ambiente.

### Vários projetos

Um config global em `~/.abl-deploy.toml` com um bloco `[project.<nome>]` por
projeto, cada um com seus ambientes. A CLI procura, nesta ordem: a variável
`ABL_DEPLOY_CONFIG`, um `abl-deploy.toml` local, e por fim `~/.abl-deploy.toml`.

```toml
[project.financeiro]
source_dir = "C:/projetos/financeiro/src"
build_dir  = "C:/projetos/financeiro/build"

[project.financeiro.env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"
```

### Buscar o fonte em várias pastas

Se a tela e o `rp` ficam em pastas diferentes, liste todas em `source_dirs` —
a CLI acha o fonte pelo nome em qualquer uma delas:

```toml
source_dir  = "src"
source_dirs = ["src/telas", "src/rp"]
```

### Roteamento por nome do arquivo

Para mandar `escq9986.r` (tela) e `escq9986rp.r` (programa) para pastas
diferentes no servidor, use `routes` — a primeira regra cujo `match` casa vence;
se nenhuma casar, usa o `remote_dir` do ambiente:

```toml
[env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"   # fallback

[[env.prod.routes]]
match = "*rp.p"
remote_dir = "/u/app/prod/rp"

[[env.prod.routes]]
match = "*.p"
remote_dir = "/u/app/prod/telas"
```

### Credenciais com segurança

Nunca coloque senhas no arquivo versionado. Use uma das opções:

- **Chave SSH** (recomendado): `key_file = "~/.ssh/id_rsa"`
- **Variável de ambiente**: `password = "env:ABL_PROD_PASS"` — a CLI lê de
  `$ABL_PROD_PASS` na hora do deploy.

O `abl-deploy.toml` real já está no `.gitignore`.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [x] Menu interativo
- [x] Vários projetos em um config global
- [x] Roteamento do `.r` por nome do arquivo
- [ ] Deploy de múltiplos fontes (glob / lista)
- [ ] Rollback do `.r` anterior
- [ ] Hook de backup remoto antes de sobrescrever
- [ ] `--dry-run`

## Licença

MIT — veja [LICENSE](LICENSE).
