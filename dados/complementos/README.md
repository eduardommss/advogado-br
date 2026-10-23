# Complementos da base

Textos oficiais que corrigem normas **incompletas** no [ctresb/leis](https://github.com/ctresb/leis) (ex.: a fonte só
tem a retificação da lei). Cada arquivo usa o **mesmo caminho** do repositório de origem
(`federal/leis-ordinarias/1998/lei-9609-1998-02-19.md`) e o mesmo cabeçalho YAML, com `fonte:` apontando para a página
oficial de onde o texto foi copiado.

Na próxima geração da base (Action `Base de leis`), o complemento substitui o arquivo de origem para todos os usuários.
Para gerar um: no Claude, peça para "baixar o texto oficial" da lei (ferramenta `baixar_oficial`) — o arquivo é salvo em
`<Juridico>/_escritorio/complementos/` — e envie-o para cá num pull request.
