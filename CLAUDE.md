# CLAUDE.md

Guia para o Claude Code trabalhar **neste repositório** (manutenção do plugin). Para usar o plugin, ver o README.

## O que é

Plugin do Claude Code/app do Claude (`.claude-plugin/plugin.json`) com skills, subagentes, um comando e um servidor
MCP em Python. Também é o próprio marketplace (`.claude-plugin/marketplace.json`, nome `advogado-br`) e está listado
no marketplace `eduardommss/ai-development-docs` (entrada com `source` github apontando para cá).

## Arquitetura — três regras que não se quebram

1. **Nada a instalar além do uv.** O servidor e as CLIs são scripts PEP 723 (`# /// script`) rodados com
   `uv run --script`; dependências só no cabeçalho do `servidor.py` (`mcp`, `pypdf`). O resto é biblioteca padrão.
2. **Base de leis = cache descartável; dados do usuário = pasta Jurídico.** A base vem da Release
   (`releases/latest/download/leis.db.gz` + `manifest.json`) para `config.cache_dir()`. Tudo que o usuário produz —
   casos, `_escritorio/precedentes.db`, `_escritorio/complementos/`, `_escritorio/biblioteca/` — fica em
   `config.juridico_dir()` (padrão `Documentos/Juridico`). Nunca grave dado do usuário no cache nem no plugin.
3. **Funciona igual em Windows, macOS, Linux e WSL.** Caminhos sempre por `config.py`; nada de `/mnt/c`, `wsl.exe`,
   shell script obrigatório ou bit de execução (o Git do Windows não grava `+x`). `casos.caminho_local` converte
   `C:\...` só quando o servidor roda no WSL.

## Mapa

| Arquivo | Papel |
|---|---|
| `mcp/servidor.py` | MCP (stdio local com escrita + `caso_*`; `--http` sempre somente leitura e sem casos). `INSTRUCOES` repete as regras das skills de propósito: no app o servidor pode estar sem as skills |
| `mcp/base.py` | download/verificação semanal da base, cópia de trabalho = base + complementos + biblioteca (troca atômica, em segundo plano) |
| `mcp/nucleo.py` | busca FTS5, leitura de artigo/precedente, verificador de citações, acórdãos conferidos, complementos |
| `mcp/casos.py` + `skills/organizar-caso/scripts/caso.py` | casos; a lógica mora só no `caso.py` |
| `mcp/indexador.py` | gera o índice (Action) e aplica overlays locais |
| `mcp/html2md.py` | conversor do ctresb/leis (MIT, ver THIRD_PARTY_NOTICES.md) |
| `scripts/gerar_base.py` + `.github/workflows/base.yml` | gera, testa e publica a base (Release `base-AAAAMMDD-N`, mantém as 4 últimas) |
| `dados/complementos/` | textos oficiais que corrigem normas incompletas da fonte — entram na próxima base |

## Regras de conteúdo

- **Nenhum artigo ou precedente citado em skill, referência ou doc entra sem passar pelo verificador** — e sem ler o
  texto para conferir que o artigo diz o que a frase afirma. O `gerar_base.py` falha o build se uma citação das
  skills deixar de existir na base nova.
- Prosa em pt-BR; commits em Conventional Commits, em pt-BR.
- Mudança de comportamento: bump de `metadata.version` nas skills afetadas **e** de `version` no `plugin.json`.

## Testar sem tocar no seu $HOME

```bash
python3 -m py_compile mcp/*.py skills/organizar-caso/scripts/caso.py scripts/*.py
# base gerada localmente e servida como se fosse a Release:
python3 scripts/gerar_base.py --leis <clone-parcial-ctresb-leis> --saida /tmp/dist
(cd /tmp/dist && python3 -m http.server 8799 &)
HOME=/tmp/h ADVOGADO_BR_URL_BASE=http://127.0.0.1:8799 uv run --script mcp/consultar.py artigo CC 413
claude plugin validate .
```
Variáveis úteis: `LEIS_DB` (índice fixo, sem download), `ADVOGADO_BR_URL_BASE` (espelho da Release),
`ADVOGADO_BR_CACHE`, `JURIDICO_DIR`, `ADVOGADO_BR_CONFIG`.
