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

### 1. Criar a configuração

```bash
abl-deploy init
```

Isso gera um `abl-deploy.toml`. Edite os ambientes (host, usuário, diretório
remoto, autenticação). Exemplo completo em
[`abl-deploy.example.toml`](abl-deploy.example.toml).

### 2. Ver os ambientes

```bash
abl-deploy envs
```

### 3. Compilar e enviar

```bash
abl-deploy deploy escq9986rp.p --env prod
```

Opções úteis:

| Flag               | Efeito                                            |
|--------------------|---------------------------------------------------|
| `--env / -e`       | ambiente alvo (obrigatório)                       |
| `--compile-only`   | só compila, não envia                             |
| `--skip-compile`   | envia um `.r` já existente em `build_dir`         |
| `--version`        | mostra a versão                                   |

## Configuração

O `abl-deploy.toml` tem uma seção `[default]` (vale para todos os ambientes) e
um bloco `[env.<nome>]` por ambiente, que sobrescreve os defaults.

```toml
[default]
dlc = "C:/Progress/OpenEdge"   # $DLC
source_dir = "src"
build_dir = "build"
propath = ["src", "src/lib"]

[env.prod]
host = "prod.suaempresa.com"
username = "deploy"
key_file = "~/.ssh/id_rsa"
remote_dir = "/u/app/prod/rcode"
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

- [ ] Deploy de múltiplos fontes (glob / lista)
- [ ] Rollback do `.r` anterior
- [ ] Hook de backup remoto antes de sobrescrever
- [ ] `--dry-run`

## Licença

MIT — veja [LICENSE](LICENSE).
