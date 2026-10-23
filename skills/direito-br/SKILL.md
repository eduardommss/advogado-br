---
name: direito-br
description: Base obrigatória para QUALQUER assunto de direito brasileiro — pergunta sobre lei, artigo, código (CC, CPC, CDC, CLT, CF, Lei do Inquilinato, LGPD…), súmula, tema, jurisprudência ou prazo legal; revisar, conferir ou corrigir citações de minuta, peça, parecer, notificação ou contrato; checar se um artigo ou acórdão existe. Garante que toda base legal venha da base oficial (servidor MCP advogado-br ou consultar.py), nunca da memória, e que o texto final passe pelo verificador de citações. Use junto com analisar-contrato, estrategia-processual, redigir-documento e organizar-caso quando eles se aplicarem.
license: MIT
metadata:
  author: Eduardo Silva
  version: 2.0.0
  plugin: advogado-br
---

# Direito brasileiro — fundamentação verificada

Regra única: **nenhuma afirmação sobre o conteúdo de lei, súmula, tema ou acórdão sai da memória.** Tudo é lido na
base durante a conversa, e todo texto entregue passa pelo verificador. Isso vale até para "perguntas rápidas".

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

## Pergunta sobre a lei ("o que diz o art. X?", "qual o prazo para Y?")
1. Ache a norma/artigo (`buscar_legislacao` com 2–3 variações de termos, `buscar_norma`, `ler_artigo`).
2. Responda citando o dispositivo, transcrevendo o trecho decisivo e o link `fonte`.
3. Precedente vinculante sobre o tema? `buscar_jurisprudencia`.

## Revisar/conferir citações de um texto (minuta, peça, parecer, contrato)
1. Rode `verificar_citacoes` no texto **inteiro** (ou delegue ao subagente `verificador-citacoes`).
2. Para cada item, aja pelo status:

| Status | Ação |
|---|---|
| `OK` | Leia o `texto_oficial` e confirme que o dispositivo **diz o que o texto afirma**; ajuste a redação se não disser |
| `NAO_ENCONTRADO` / `DIVERGENTE` / `REVOGADO` | Corrija para o dispositivo certo (buscando na base) ou remova |
| `AMBIGUO` | Complete (tribunal, seção da OJ, tipo do tema) |
| `NAO_VERIFICADO` (acórdão / nº de processo) | Peça ao subagente `pesquisador-jurisprudencia` para conferir na página oficial e registrar; se não for possível conferir, remova e diga por quê |
| `NAO_VERIFICAVEL` (lei incompleta na base) | Corrija a base: `baixar_oficial(lei, url_do_planalto)` e leia de novo; sem acesso, avise que não foi verificado |

3. Rode o verificador de novo na versão final e só entregue com tudo `OK` (ou com as pendências declaradas).
4. Na resposta, liste o que mudou e por quê, com a fonte de cada correção.

## Encaminhamento
- Contrato para avaliar → `analisar-contrato` · litígio/tese → `estrategia-processual` · escrever documento →
  `redigir-documento` · arquivos e prazos de um caso → `organizar-caso` · "e agora?" → `proximo-passo`.

Linha final em pareceres e peças: "Análise de apoio; a decisão e a assinatura de peças cabem a advogado inscrito na OAB."
