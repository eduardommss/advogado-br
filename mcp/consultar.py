#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Linha de comando para a mesma base do servidor MCP (use quando o MCP não estiver disponível).
Rodar: uv run --script mcp/consultar.py <comando>   (ou python3 mcp/consultar.py <comando>)
Na primeira consulta baixa a base de leis (~1 min).

Leitura:
  consultar.py artigo CC 412                       consultar.py info "Lei 8.245/1991"
  consultar.py buscar "denúncia vazia" --lei "Lei do Inquilinato"
  consultar.py norma "proteção de dados pessoais"  consultar.py codigos
  consultar.py juris "dano moral pessoa jurídica" --tribunal STJ
  consultar.py precedente STJ sumula 227
  consultar.py verificar peticao.md                (ou - para ler do stdin)
  consultar.py acordaos "multa locação proporcional" [--tribunal TJRN]   # acórdãos já conferidos
  consultar.py biblioteca "cláusula penal"         # doutrina/pareceres próprios
  consultar.py lacunas [--limite 50]               # leis incompletas na base
  consultar.py status                              # versão da base, caminhos (cache, Jurídico, escritório)
  consultar.py atualizar [--forcar]                # baixa base nova da Release, se houver
Escrita:
  consultar.py registrar --tribunal STJ --classe REsp --numero 1.234.567 --uf SP --url https://... --ementa "..."
  consultar.py complementar "Lei 9.609/1998" --arquivo texto.md --fonte https://www.planalto.gov.br/...
  consultar.py baixar "Lei 9.609/1998" https://www.planalto.gov.br/ccivil_03/leis/l9609.htm   # texto oficial → complemento
  consultar.py reindexar
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base  # noqa: E402
import config  # noqa: E402
import nucleo  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Consulta à base de leis brasileiras")
    s = ap.add_subparsers(dest="cmd", required=True)
    p = s.add_parser("artigo"); p.add_argument("lei"); p.add_argument("artigo"); p.add_argument("--parte"); p.add_argument("--vizinhos", type=int, default=0)
    p = s.add_parser("buscar"); p.add_argument("consulta"); p.add_argument("--lei"); p.add_argument("--uf"); p.add_argument("--limite", type=int, default=10)
    p = s.add_parser("juris"); p.add_argument("consulta"); p.add_argument("--tribunal"); p.add_argument("--tipo"); p.add_argument("--limite", type=int, default=10)
    p = s.add_parser("precedente"); p.add_argument("tribunal"); p.add_argument("tipo"); p.add_argument("numero")
    p = s.add_parser("verificar"); p.add_argument("arquivo", help="arquivo de texto/markdown, ou - para stdin")
    p = s.add_parser("norma"); p.add_argument("consulta")
    p = s.add_parser("info"); p.add_argument("lei")
    s.add_parser("codigos")
    p = s.add_parser("acordaos"); p.add_argument("consulta", nargs="?", default=""); p.add_argument("--tribunal"); p.add_argument("--limite", type=int, default=10)
    p = s.add_parser("biblioteca"); p.add_argument("consulta"); p.add_argument("--limite", type=int, default=10)
    p = s.add_parser("lacunas"); p.add_argument("--limite", type=int, default=50)
    s.add_parser("status"); s.add_parser("config")
    p = s.add_parser("atualizar"); p.add_argument("--forcar", action="store_true")
    p = s.add_parser("registrar")
    for campo in ("tribunal", "classe", "numero", "url", "ementa"):
        p.add_argument("--" + campo, required=True)
    for campo in ("relator", "orgao", "data-julgamento", "tese", "uf", "caso"):
        p.add_argument("--" + campo, default="")
    p = s.add_parser("complementar"); p.add_argument("lei"); p.add_argument("--arquivo", required=True); p.add_argument("--fonte", required=True)
    p = s.add_parser("baixar"); p.add_argument("lei"); p.add_argument("url")
    s.add_parser("reindexar")
    x = ap.parse_args()

    precisa_base = x.cmd not in ("status", "config", "atualizar", "registrar", "acordaos")
    if precisa_base and base.caminho_trabalho() is None:
        print("Baixando a base de leis pela primeira vez (~1 min)...", file=sys.stderr)
        r = base.atualizar()
        if not r.get("ok"):
            print(json.dumps(r, ensure_ascii=False, indent=2))
            sys.exit(1)

    if x.cmd == "artigo":
        r = nucleo.ler_artigo(x.lei, x.artigo, parte=x.parte, vizinhos=x.vizinhos)
    elif x.cmd == "buscar":
        r = nucleo.buscar_legislacao(x.consulta, lei=x.lei, uf=x.uf, limite=x.limite)
    elif x.cmd == "juris":
        r = nucleo.buscar_jurisprudencia(x.consulta, tribunal=x.tribunal, tipo=x.tipo, limite=x.limite)
    elif x.cmd == "precedente":
        r = nucleo.ler_precedente(x.tribunal, x.tipo, x.numero)
    elif x.cmd == "verificar":
        texto = sys.stdin.read() if x.arquivo == "-" else Path(x.arquivo).read_text(encoding="utf-8")
        r = nucleo.verificar_citacoes(texto)
    elif x.cmd == "norma":
        r = nucleo.buscar_norma(x.consulta)
    elif x.cmd == "info":
        r = nucleo.info_norma(x.lei)
    elif x.cmd == "codigos":
        r = nucleo.listar_codigos()
    elif x.cmd == "acordaos":
        r = nucleo.buscar_precedentes_verificados(x.consulta, tribunal=x.tribunal, limite=x.limite)
    elif x.cmd == "biblioteca":
        r = nucleo.buscar_biblioteca(x.consulta, limite=x.limite)
    elif x.cmd == "lacunas":
        r = nucleo.lacunas(limite=x.limite)
    elif x.cmd in ("status", "config"):
        r = {"base": base.status(), "caminhos": config.tudo()}
    elif x.cmd == "atualizar":
        r = base.atualizar(x.forcar)
    elif x.cmd == "registrar":
        r = nucleo.registrar_precedente(x.tribunal, x.classe, x.numero, x.url, x.ementa, relator=x.relator,
                                        orgao=x.orgao, data_julgamento=x.data_julgamento, tese=x.tese, uf=x.uf, caso=x.caso)
    elif x.cmd == "complementar":
        r = nucleo.salvar_complemento(x.lei, Path(x.arquivo).read_text(encoding="utf-8"), x.fonte)
    elif x.cmd == "baixar":
        r = nucleo.baixar_oficial(x.lei, x.url)
    else:
        r = nucleo.reindexar()
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
