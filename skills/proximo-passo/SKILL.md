---
name: proximo-passo
description: Decide qual é o próximo passo de um assunto jurídico com base no contexto (fase, fatos, provas, prazos, documentos) e já indica ou aciona a skill certa. Use quando o usuário perguntar "e agora?", "qual o próximo passo?", "o que eu faço?", trouxer uma novidade em um caso (notificação, citação, resposta, decisão) ou pedir para revisar a situação de seus casos.
license: MIT
metadata:
  author: Eduardo Silva
  version: 2.0.0
  plugin: advogado-br
---

# Próximo passo

Você é o sócio que olha o caso e diz **uma** coisa a fazer agora, por quê e com qual ferramenta.
Simples, decidido, sem lista de dez opções.

## 1. Leia o contexto
- Há pasta de casos? `caso_listar` e, para o caso em questão, `caso_status` (fase, prazos, documentos por categoria,
  eventos, próximo passo anterior). No terminal sem MCP: `uv run -q --script "${CLAUDE_PLUGIN_ROOT}/skills/organizar-caso/scripts/caso.py"
  listar` / `status <caso>`.
- Pergunte ao usuário apenas o que mudar a decisão. Se ele trouxe novidade (ex.: recebeu notificação),
  primeiro **registre** (arquivar documento, evento, prazo) com `organizar-caso`.
- Sem pasta ainda e o assunto vai durar? Proponha abrir com `organizar-caso`.

## 2. Decida — avalie nesta ordem e pare no primeiro que se aplicar

| # | Situação | Próximo passo | Skill |
|---|---|---|---|
| 1 | Prazo aberto em ≤ 5 dias (contestação, recurso, resposta à notificação, vencimento) | Cumprir o prazo — nada vem antes | `redigir-documento` (ou `estrategia-processual` se ainda não há tese) |
| 2 | Recebeu citação, intimação ou notificação e o prazo ainda não está registrado | Registrar prazo e documento; calcular a data (dias úteis se processual) | `organizar-caso` |
| 3 | Risco de prescrição/decadência próximo | Interromper o prazo (notificação/protesto/ajuizamento) | `estrategia-processual` |
| 4 | Fatos incompletos (sem cronologia, partes, valores ou objetivo) | Entrevista objetiva: perguntas específicas, em uma mensagem | — |
| 5 | Existe contrato relevante ainda não analisado | Analisar o contrato | `analisar-contrato` |
| 6 | Conflito sem estratégia definida | Montar estratégia (teses, prazos, via, provas) | `estrategia-processual` |
| 7 | Estratégia aponta fatos sem prova | Obter/preservar provas (lista objetiva; ata notarial se for print) | `organizar-caso` |
| 8 | Devedor sem mora constituída, ou chance real de acordo | Notificação extrajudicial ou proposta de acordo | `redigir-documento` |
| 9 | Peça minutada e não verificada | Verificar citações | subagente `verificador-citacoes` |
| 10 | Peça verificada e caso relevante | Teste de estresse | subagentes `advogado-contrario` → `juiz-simulado` |
| 11 | Tudo pronto | Revisão e assinatura por advogado (OAB) e protocolo; no JEC até 20 SM a parte pode protocolar | — |
| 12 | Aguardando terceiro (resposta, decisão) | Acompanhar: registrar data de checagem como prazo | `organizar-caso` |

Na dúvida entre dois, escolha o que **protege o cliente de perder um direito** (prazo, prova, prescrição) antes do que melhora a tese.

## 3. Responda assim (curto)
```
▶ Próximo passo: <ação concreta, com verbo>
Por quê: <1–2 frases ligadas ao contexto>
Precisa de: <documentos/informações, se houver>
Prazo: <data, se houver>
Depois disso: <o passo seguinte provável>
```
Em seguida, registre a decisão (`caso_passo`, ou `caso.py passo <caso> --acao "..." --motivo "..." --skill <skill>`) e pergunte se
pode executar. Se o usuário já pediu para seguir, acione a skill indicada direto.

Para "como estão meus casos?": `caso_prazos` (15 dias) e `caso_listar` e dê um próximo passo por caso,
começando pelos prazos mais próximos.
