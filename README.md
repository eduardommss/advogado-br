# advogado-br

Agente jurídico de direito brasileiro para o Claude: analisa e redige contratos, monta estratégia processual, testa a
tese contra um advogado contrário e um juiz simulado, **confere toda citação** (artigo, §, inciso, súmula, tema,
acórdão) contra a base oficial e organiza cada assunto em pastas no seu computador.

A base é o [ctresb/leis](https://github.com/ctresb/leis) — legislação federal, Constituição, súmulas, súmulas
vinculantes, temas repetitivos, repercussão geral, OJs e controle concentrado — indexada por artigo. Uma GitHub Action
gera o índice toda semana e publica na [Release](https://github.com/eduardommss/advogado-br/releases); o plugin baixa e
atualiza sozinho. **Não há instalador nem banco para montar à mão.**

> ⚖️ Ferramenta de apoio. Não substitui advogado: peças devem ser revisadas e assinadas por profissional inscrito na
> OAB (exceto no Juizado Especial Cível até 20 salários mínimos, art. 9º da Lei 9.099/1995).

## Instalação (uma vez por computador)

**1. Instale o [uv](https://docs.astral.sh/uv/)** — ele cuida do Python e das dependências:

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `winget install astral-sh.uv` |
| macOS / Linux / WSL | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

**2. Instale o plugin** no Claude (app ou Claude Code), digitando no campo de mensagem:

```
/plugin marketplace add eduardommss/advogado-br
/plugin install advogado-br@advogado-br
```

(Também está no marketplace [`eduardommss/ai-development-docs`](https://github.com/eduardommss/ai-development-docs):
`/plugin install advogado-br@ai-development-docs`.)

**3. Reinicie o Claude** (no Windows: ícone na bandeja → Sair, e abra de novo).

Pronto. Na primeira pergunta jurídica o plugin baixa a base (~100 MB, cerca de 1 minuto) e cria a pasta
`Documentos\Juridico`. Para conferir: *"rode o diagnóstico do advogado-br"*.

## Uso — lembre só disto

```
/advogado-br:advogado                  menu + confere a instalação
/advogado-br:advogado <o que precisa>  ex.: "analisa esse contrato, meu sogro é o comprador"
/advogado-br:advogado casos            retoma de onde parou: casos, prazos e próximo passo de cada um
```

Ou fale normalmente — as skills disparam pelo assunto:

| Você diz | O que acontece |
|---|---|
| "Abre um caso: o contrato está em `C:\Users\eu\Downloads\contrato.pdf`, sou o comprador" | cria a pasta do caso, arquiva o PDF, lê e analisa |
| "Organiza minha entrada" (depois de jogar arquivos em `Juridico\_ENTRADA`) | classifica cada arquivo no caso certo |
| "Analisa esse contrato, sou o contratado" | veredito, matriz de risco, top 5 ajustes com redação pronta |
| "Quero processar a empresa X" | prescrição, via, foro, teses, matriz fato × prova, precedentes, riscos |
| "Testa essa tese" | advogado contrário ataca → juiz simulado decide |
| "Redige a notificação" | minuta com citações verificadas antes da entrega |
| "Confere as citações dessa minuta" / "o que diz o art. 413 do CC?" | lê na base, corrige ou remove o que não confere |
| "E agora?" / "Como estão meus casos?" | uma próxima ação por caso, prazos mais próximos primeiro |

Toda resposta termina com **"▶ Próximo passo"**, gravado no caso — você não precisa lembrar onde parou.

## Onde ficam as coisas (e o que fazer backup)

| O quê | Onde | Backup? |
|---|---|---|
| **Casos** | `Documentos\Juridico\2026-001-…` (documentos, provas, peças, pesquisa, comunicações, decisões) | **Sim** |
| **Dados do escritório** — acórdãos conferidos, complementos de leis, biblioteca | `Documentos\Juridico\_escritorio\` | **Sim** |
| Base de leis (cache) | Windows `%LOCALAPPDATA%\advogado-br` · macOS `~/Library/Caches/advogado-br` · Linux `~/.cache/advogado-br` | Não — baixa de novo sozinha |
| Plugin | gerenciado pelo Claude | Não — reinstale |

Tudo o que é seu fica em **uma pasta**. Se `Documentos` estiver no OneDrive/Google Drive, formatar o computador não
perde nada: instale o uv e o plugin e continue. Outra pasta? Crie o `config.json` (Windows:
`%APPDATA%\advogado-br\config.json`; demais: `~/.config/advogado-br/config.json`):

```json
{ "juridico_dir": "D:\\Drive\\Juridico" }
```

## Como o agente evita erro de lei

- **Nada de memória:** todo artigo e precedente é lido na base durante a conversa; o texto final passa pelo
  `verificar_citacoes`, que acusa artigo inexistente, § ou inciso inventado, dispositivo revogado e súmula ambígua.
- **Acórdão só conferido:** decisões fora das súmulas/temas entram depois de abertas na página oficial do tribunal
  (`*.jus.br`) pelo subagente `pesquisador-jurisprudencia` e gravadas em `_escritorio\precedentes.db`. O resto aparece
  como `NAO_VERIFICADO`.
- **Lacuna da fonte se corrige na base:** se uma lei está incompleta no ctresb/leis (`NAO_VERIFICAVEL`), o agente baixa
  o texto oficial do Planalto (`baixar_oficial`) e grava em `_escritorio\complementos\`. Para valer para todos, envie o
  arquivo para [`dados/complementos/`](dados/complementos/) num pull request.
- **Doutrina só a sua:** coloque livros, artigos e pareceres em `.md`/`.txt` em `_escritorio\biblioteca\`; o agente
  cita pelo título/autor do arquivo.

## Componentes

| Tipo | Nome | O que faz |
|---|---|---|
| Comando | [`/advogado-br:advogado`](commands/advogado.md) | Porta de entrada: menu, diagnóstico e encaminhamento |
| Skill | [`direito-br`](skills/direito-br/SKILL.md) | Base de qualquer assunto jurídico: lê na base, verifica antes de entregar |
| Skill | [`analisar-contrato`](skills/analisar-contrato/SKILL.md) | Matriz de risco, cláusulas atacáveis, redação alternativa |
| Skill | [`estrategia-processual`](skills/estrategia-processual/SKILL.md) | Prescrição, via, foro, teses, matriz fato × prova, riscos, plano B |
| Skill | [`redigir-documento`](skills/redigir-documento/SKILL.md) | Contratos, notificações, acordos e petições com citações verificadas |
| Skill | [`proximo-passo`](skills/proximo-passo/SKILL.md) | Decide **uma** próxima ação e a skill que a executa |
| Skill | [`organizar-caso`](skills/organizar-caso/SKILL.md) | Pastas por assunto, prazos, linha do tempo, SHA-256 das provas |
| Agente | [`verificador-citacoes`](agents/verificador-citacoes.md) | Confere cada citação e aponta o que corrigir |
| Agente | [`pesquisador-jurisprudencia`](agents/pesquisador-jurisprudencia.md) | Acha acórdãos, confere na fonte oficial e registra |
| Agente | [`advogado-contrario`](agents/advogado-contrario.md) | Ataca a tese como o adversário faria |
| Agente | [`juiz-simulado`](agents/juiz-simulado.md) | Decide com base em prova, lei e precedentes obrigatórios |
| MCP | `advogado-br` ([`mcp/servidor.py`](mcp/servidor.py)) | 31 ferramentas: leis, precedentes, verificador, acórdãos, biblioteca, casos |

## Linha de comando (opcional)

A mesma base, sem o Claude — útil para conferir algo rápido:

```bash
uv run --script mcp/consultar.py artigo CC 413
uv run --script mcp/consultar.py buscar "denúncia vazia locação" --lei "Lei do Inquilinato"
uv run --script mcp/consultar.py juris "dano moral pessoa jurídica" --tribunal STJ
uv run --script mcp/consultar.py verificar minha-minuta.md
uv run --script mcp/consultar.py status          # versão da base e caminhos
uv run --script mcp/consultar.py atualizar       # força a busca de base nova
```

## Atualizações

- **Base de leis:** automática — o plugin confere a Release a cada 7 dias (`verificar_dias` no config.json) e troca a
  base sem perder seus complementos e biblioteca.
- **Plugin:** `/plugin update advogado-br@advogado-br` (ou pelo gerenciador de plugins do app).

## Servidor remoto (opcional)

Para consultar a base com o computador desligado (celular, equipe), publique o servidor HTTP somente leitura — sem
acesso a casos:

```bash
docker build -f deploy/Dockerfile -t advogado-br . && docker run -p 8000:8000 advogado-br
```

Publique atrás de HTTPS e adicione `https://<seu-domínio>/mcp` como conector personalizado no Claude.

## Solução de problemas

| Sintoma | Solução |
|---|---|
| Ferramentas do `advogado-br` não aparecem | O servidor não subiu: instale o `uv` e reinicie o Claude por completo |
| "A base de leis está sendo baixada…" | Primeira execução: aguarde ~1 minuto |
| "Não foi possível obter a base de leis" | Sem internet ou GitHub bloqueado na rede; peça "atualize a base do advogado-br" depois |
| `NAO_VERIFICAVEL` | Lei incompleta na fonte: peça para baixar o texto oficial do Planalto |
| `NAO_VERIFICADO` | Acórdão não conferido: peça para conferir na fonte oficial, ou remova |
| Imagem ou PDF escaneado | Anexe o arquivo na conversa (o servidor só extrai texto) |

## Limites

- Busca textual (com radicais), não semântica — o agente faz 2–3 variações de termos.
- A base cobre o que o ctresb/leis já coletou: legislação federal e jurisprudência vinculante. Decretos federais
  numerados, leis estaduais e municipais ainda não entram no índice publicado.
- Textos vêm de conversão automática/OCR e não substituem o Diário Oficial — cada resultado traz o link `fonte`.
- Prazos em dias úteis sem feriados forenses locais: confira no calendário do tribunal.

## Para desenvolvedores

- [`mcp/`](mcp/) — servidor ([`servidor.py`](mcp/servidor.py)), núcleo de busca e verificação ([`nucleo.py`](mcp/nucleo.py)),
  download/atualização da base ([`base.py`](mcp/base.py)), casos ([`casos.py`](mcp/casos.py)), caminhos
  ([`config.py`](mcp/config.py)), indexador ([`indexador.py`](mcp/indexador.py)).
- [`scripts/gerar_base.py`](scripts/gerar_base.py) + [`.github/workflows/base.yml`](.github/workflows/base.yml) —
  geram e testam a base e publicam a Release (semanal, manual ou a cada complemento novo).
- Convenções de manutenção em [`CLAUDE.md`](CLAUDE.md).

Licença MIT. O conversor HTML→Markdown e os textos normativos vêm do [ctresb/leis](https://github.com/ctresb/leis) —
ver [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
