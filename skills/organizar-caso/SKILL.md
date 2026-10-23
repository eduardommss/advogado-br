---
name: organizar-caso
description: Organiza cada assunto jurídico em pastas no computador do usuário — documentos, provas, peças, pesquisa, comunicações, decisões e links — com linha do tempo, prazos, hash das provas e índice geral. Use quando o usuário quiser abrir um caso/assunto, guardar um contrato, prova, print, e-mail ou link, classificar arquivos soltos, registrar um prazo ou ver como está a pasta de um caso.
license: MIT
metadata:
  author: Eduardo Silva
  version: 2.0.0
  plugin: advogado-br
---

# Organizar caso

Tudo passa pelo servidor MCP `advogado-br` (ferramentas `caso_*`) ou, no terminal, pelo script `caso.py` — a mesma
lógica. Nunca crie pastas ou mova arquivos "na mão": cada item é registrado no `caso.json`, recebe SHA-256, e o
`RESUMO.md` e o `_INDICE.md` são regenerados.

- **App do Claude (Windows/nuvem) ou qualquer cliente com o MCP:** use `caso_listar`, `caso_status`, `caso_prazos`,
  `caso_entrada`, `caso_ler_documento`, `caso_novo`, `caso_arquivar`, `caso_salvar_texto`, `caso_evento`,
  `caso_prazo`, `caso_fase`, `caso_passo`, `caso_link`, `caso_atualizar`. Elas rodam na máquina do usuário e aceitam
  caminhos do Windows (`C:\Users\...\Downloads\contrato.pdf`). `caso_ler_documento` extrai o texto de PDF/DOCX/MD;
  imagem e PDF escaneado: peça o arquivo anexado na conversa.
- **Terminal (Claude Code) sem MCP:**
```
S='uv run -q --script "${CLAUDE_PLUGIN_ROOT}/skills/organizar-caso/scripts/caso.py"'
```
Raiz das pastas: `Documentos/Juridico` do usuário (no Windows, a pasta Documentos real — inclusive no OneDrive), ou
a `juridico_dir` do config.json do advogado-br. `caso_listar` e `diagnostico` mostram o caminho (`raiz`,
`raiz_windows`) — informe-o ao usuário para ele abrir no Explorer/Finder. A subpasta `_escritorio/` guarda acórdãos
conferidos, complementos e biblioteca: não é um caso, não mexa nela.
**Não prefixe variáveis de ambiente nos comandos** (`JURIDICO_DIR=... python3 ...`): rode o comando direto.

## Estrutura criada
```
~/Juridico/
├── _INDICE.md                 ← todos os casos, fases, próximos passos e prazos
├── _ENTRADA/                  ← o usuário joga arquivos soltos aqui; você classifica
└── 2026-001-locacao-apto-centro/
    ├── caso.json              ← fonte da verdade (partes, fase, prazos, eventos, documentos, links, próximo passo)
    ├── RESUMO.md              ← gerado: visão humana do caso, linha do tempo, prazos, links
    ├── 01-documentos/         contratos, aditivos, procurações, docs pessoais/societários
    ├── 02-provas/             fotos, prints, áudios, vídeos, laudos, comprovantes, extratos
    ├── 03-pecas/              petições, notificações, minutas, contratos redigidos por nós
    ├── 04-pesquisa/           análises, estratégias, pareceres, precedentes salvos
    ├── 05-comunicacoes/       e-mails, conversas, notificações recebidas
    └── 06-decisoes/           decisões, sentenças, atas, acordos homologados
```
Arquivos recebem o nome `AAAA-MM-DD_descricao.ext`, onde a data é a **do documento/fato**, não a de hoje.

## Comandos
| Situação | Comando no terminal (no MCP: a ferramenta `caso_<comando>`) |
|---|---|
| Abrir assunto | `$S novo "Título curto" --tipo contrato\|processo\|consulta\|negociacao\|cobranca --area civil --papel locatário --parte "Fulano:locador"` |
| Guardar arquivo | `$S arquivar <caso> <arquivo> --categoria documentos\|provas\|pecas\|pesquisa\|comunicacoes\|decisoes --descricao "..." --data AAAA-MM-DD` |
| Guardar link | `$S link <caso> <url> --descricao "..."` |
| Fato na linha do tempo | `$S evento <caso> --data AAAA-MM-DD --descricao "..."` |
| Prazo / cumprir prazo | `$S prazo <caso> --data AAAA-MM-DD --descricao "..."` · `$S prazo <caso> --descricao "parte do texto" --cumprido` |
| Mudar fase | `$S fase <caso> analise\|negociacao\|notificacao\|pre-processual\|judicial\|recurso\|execucao\|acompanhamento\|encerrado` |
| Registrar próximo passo | `$S passo <caso> --acao "..." --motivo "..." --skill <skill>` |
| Ver caso / listar / prazos | `$S status <caso>` · `$S listar` · `$S prazos --dias 30` |
| Arquivos soltos | `$S entrada` |
| Corrigir dados do caso | `$S atualizar <caso> --numero-processo ... --tribunal ... --parte "Nome:papel"` |

`<caso>` aceita o id (`2026-001`) ou parte do nome da pasta.

## Como classificar arquivos (inclusive os da `_ENTRADA`)
1. Leia cada arquivo (texto, PDF, imagem) o suficiente para saber **o que é**, **de quando é** e **a qual caso pertence**.
2. Escolha a categoria pela função no caso: o contrato é *documento*; o print da conversa provando o fato é *prova*;
   o e-mail de negociação é *comunicação* (se ele prova um fato controvertido, é *prova*).
3. Se o arquivo serve a um caso que não existe, proponha abrir o caso (título, tipo, partes) e confirme com o usuário.
4. Arquivos da `_ENTRADA` são **movidos**; de outros lugares são **copiados** (o original fica intacto).
5. Duplicatas (mesmo hash) são recusadas automaticamente.
6. Ao receber um fato com data (ex.: "ele mandou mensagem dia 3"), registre também um `evento`.
7. Ao identificar um prazo (notificação com prazo, citação, vencimento, prescrição), registre com `prazo` e avise o usuário.

## Provas digitais
O SHA-256 gravado no `caso.json` ajuda a demonstrar que o arquivo não mudou depois de arquivado. Para provas
críticas (prints de conversa, páginas da web), recomende também **ata notarial** (art. 384 do CPC) e guardar o
arquivo original (exportação da conversa, e-mail em .eml, vídeo original).

## Quando as ferramentas `caso_*` não estiverem disponíveis
Numa conversa na nuvem sem o plugin ativo, um script rodaria no ambiente da nuvem — não no computador do usuário.
Não organize lá: diga que o plugin `advogado-br` não está ativo neste ambiente (ele precisa do app do Claude ou do
Claude Code no computador, com o `uv` instalado). Nunca simule a organização.
