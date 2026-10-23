---
name: redigir-documento
description: Redige contratos, aditivos, distratos, notificações extrajudiciais, acordos e minutas de petição (inicial, contestação, réplica, recursos) segundo o direito brasileiro, com fundamentação verificada na base de leis. Use quando o usuário pedir para criar, minutar, reescrever ou ajustar um documento jurídico.
license: MIT
metadata:
  author: Eduardo Silva
  version: 2.0.0
  plugin: advogado-br
---

# Redigir documento jurídico

## Ferramentas (passo 0 — obrigatório)
Use as ferramentas do servidor MCP `advogado-br` (nomes terminando em `ler_artigo`, `buscar_legislacao`,
`verificar_citacoes`, `caso_…`; procure com ToolSearch se estiverem adiadas). **Se não estiverem disponíveis e houver
terminal, use a linha de comando — mesma base, mesmos resultados; nunca responda de memória:**
```
L='uv run -q --script "${CLAUDE_PLUGIN_ROOT}/mcp/consultar.py"'
$L artigo CC 413            $L buscar "cláusula penal redução" --lei CC      $L norma "locação imóveis urbanos"
$L juris "dano moral" --tribunal STJ      $L precedente STJ sumula 227      $L verificar arquivo.md   (ou - para stdin)
$L acordaos "multa locação"  (acórdãos já conferidos)    $L biblioteca "cláusula penal"  (doutrina própria)
```
Na primeira vez a base de leis é baixada sozinha (~1 min). Se uma ferramenta responder `base_indisponivel`, avise o
usuário que a base está sendo baixada e tente de novo. Sem ferramentas e sem terminal (ex.: conversa na nuvem sem o
plugin), diga que o plugin `advogado-br` não está ativo e não responda de memória.

**Lacunas da base — como agir:**
- Acórdão comum (TJ, STJ fora de repetitivo): só cite se estiver em `buscar_precedentes_verificados`; senão delegue
  ao subagente `pesquisador-jurisprudencia`, que confere na fonte oficial e registra. Status `NAO_VERIFICADO` no
  verificador = conferir ou remover.
- Lei incompleta (`NAO_VERIFICAVEL`): corrija a base com `baixar_oficial(lei, url_do_planalto)`
  (`$L baixar "Lei 9.609/1998" https://www.planalto.gov.br/...`) e leia o artigo de novo.
- Doutrina: só a da biblioteca própria (`buscar_biblioteca`), citada pelo título/autor do arquivo. Nunca invente
  autor, obra ou página.

## Antes de escrever
- Identifique: tipo de documento, de que lado está o cliente, objetivo, destinatário, prazo.
- Se há pasta de caso, leia `caso.json`, a estratégia em `04-pesquisa/` e as provas listadas — a peça segue a estratégia.
- Contrato: parta do playbook `../analisar-contrato/referencias/playbook-contratos.md` e redija **a favor do cliente**,
  mas com cláusulas que sobrevivam a um juiz (multa proporcional, saída clara, reajuste anual, foro pertinente).
- Petição: siga o checklist `../estrategia-processual/referencias/checklist-processual.md` (requisitos do art. 319 do CPC,
  documentos, valor da causa, pedidos principal e subsidiários, tutela de urgência quando couber).

## Estilo
- Claro e objetivo; frases curtas; sem latinismos desnecessários; sem adjetivação vazia.
- Na petição: fatos → direito → precedentes obrigatórios → pedidos. Cada argumento com base lida na base.
- Precedente favorável: cite expressamente e peça sua aplicação (art. 927 do CPC). Contrário: faça a distinção.
- Nunca invente acórdão, número de processo, relator ou data. Se não tiver precedente verificado, não cite.

## Fluxo
1. Esqueleto (seções) → 2. Redação → 3. `verificar_citacoes` sobre o texto completo (ou subagente
`verificador-citacoes`) → 4. corrija tudo que não for `OK` → 5. entregue.
Formato: .docx quando o usuário pedir arquivo editável (skill docx), senão documento no chat/artefato.
Salve em `03-pecas/` da pasta do caso com `caso.py arquivar` quando houver caso.

Toda peça termina com campos de assinatura do advogado (nome, OAB/UF) — quem assina e protocola é advogado
inscrito na OAB (exceto no JEC até 20 salários mínimos, art. 9º da Lei 9.099/1995).
