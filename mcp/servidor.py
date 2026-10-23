#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<3", "pypdf>=4"]
# ///
"""Servidor MCP "advogado-br": legislação e precedentes brasileiros (base ctresb/leis), acórdãos conferidos e as
pastas de casos do usuário.

Rodar (o uv instala Python e dependências sozinho, em Windows, macOS e Linux):
    uv run --script mcp/servidor.py
Remoto, só leitura (conector do claude.ai / equipe):
    uv run --script mcp/servidor.py --http --host 0.0.0.0 --port 8000 --somente-leitura
Na primeira execução baixa a base de leis (~1 min) em segundo plano; depois confere atualização semanalmente.
Funciona com o SDK MCP 1.x (FastMCP) e 2.x (MCPServer).
"""
import argparse
import functools
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import config  # noqa: E402

try:
    import mcp  # noqa: F401
except ImportError:
    sys.exit("SDK MCP não encontrado. Rode com o uv: 'uv run --script mcp/servidor.py' "
             "(instale o uv: https://docs.astral.sh/uv/ — no Windows, 'winget install astral-sh.uv').")

import base  # noqa: E402
import nucleo  # noqa: E402
import casos  # noqa: E402

try:  # SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
    _SDK2 = True
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    _SDK2 = False

INSTRUCOES = """advogado-br — agente jurídico de direito brasileiro. Este servidor tem (a) a base oficial: legislação
federal (CF, códigos, leis, decretos-lei), precedentes vinculantes/sumulados (súmulas STF/STJ/TST, SV, repetitivos,
repercussão geral, OJs, ADI/ADC/ADPF) e os acórdãos que o escritório já conferiu; e (b) as pastas de casos do usuário
(ferramentas caso_*), na máquina dele.

Regras inegociáveis:
1. Nenhuma base legal da memória: leia com ler_artigo / ler_precedente antes de afirmar. Busque com 2-3 variações.
2. Acórdão comum só depois de conferido na página oficial do tribunal (*.jus.br) e gravado com registrar_precedente.
3. Antes de entregar análise, peça, parecer ou contrato, rode verificar_citacoes no texto final; corrija ou remova
   tudo que não for OK (NAO_VERIFICAVEL: baixar_oficial com a URL do Planalto; NAO_VERIFICADO: conferir ou remover).
4. Cite o link 'fonte'. Termine com "▶ Próximo passo:" e registre-o no caso (caso_passo).
5. Assunto que vai durar → abra um caso (caso_novo) e arquive os documentos (caso_arquivar, caso_salvar_texto).
   Leia documentos do caso com caso_ler_documento. Prazos com caso_prazo. Comece por caso_listar / caso_prazos.
6. Agressivo dentro da lei: teses principais e subsidiárias, preliminares, distinção de precedentes; sinalize risco
   de má-fé (art. 80 do CPC). A assinatura de peças cabe a advogado inscrito na OAB.
Se uma ferramenta avisar "base_indisponivel", a base de leis está sendo baixada (1ª vez, ~1 min): avise o usuário e
tente de novo; se persistir, rode diagnostico. Nunca substitua a base por conhecimento de memória."""


# ----------------------------------------------------------------------------- leitura

def buscar_legislacao(consulta: str, lei: str | None = None, uf: str | None = None,
                      incluir_revogadas: bool = False, limite: int = 10) -> dict:
    """Busca artigos de lei por palavras-chave (busca textual, não semântica).

    Use vocabulário jurídico e faça 2-3 variações ('cláusula penal', 'multa contratual', 'pena convencional').
    lei: restringe a uma norma (apelido como 'CC', 'CDC', 'CPC', 'CLT', 'Lei do Inquilinato', ou 'Lei 8.245/1991').
    uf: inclui legislação estadual dessa UF, se indexada.
    """
    return nucleo.buscar_legislacao(consulta, lei=lei, uf=uf, incluir_revogadas=incluir_revogadas, limite=min(limite, 30))


def ler_artigo(lei: str, artigo: str, parte: str | None = None, vizinhos: int = 0) -> dict:
    """Lê o texto integral e vigente de um artigo. Ex.: lei='CC', artigo='412'; lei='Lei 8.245/1991', artigo='57'.

    parte='ADCT' para o Ato das Disposições Constitucionais Transitórias. vizinhos=N traz N artigos antes/depois.
    """
    return nucleo.ler_artigo(lei, artigo, parte=parte, vizinhos=min(vizinhos, 5))


def info_norma(lei: str) -> dict:
    """Metadados de uma norma: título, ementa, se está revogada, versão do texto, fonte oficial, nº de artigos."""
    return nucleo.info_norma(lei)


def buscar_norma(consulta: str, limite: int = 10) -> dict:
    """Encontra leis pelo nome ou assunto da ementa (ex.: 'locação de imóveis urbanos', 'proteção de dados')."""
    return nucleo.buscar_norma(consulta, limite=min(limite, 30))


def buscar_jurisprudencia(consulta: str, tribunal: str | None = None, tipo: str | None = None, limite: int = 10) -> dict:
    """Busca súmulas, súmulas vinculantes, temas repetitivos (STJ), repercussão geral (STF), OJs (TST),
    PUIL (TNU) e controle concentrado (ADI/ADC/ADPF/ADO).

    tribunal: STF, STJ, TST, TNU, TRF4, TCU, STM.  tipo: 'sumula', 'sumula vinculante', 'repetitivo',
    'repercussao geral', 'oj', 'adi', 'adpf', 'puil'. Acórdãos comuns: use buscar_precedentes_verificados.
    """
    return nucleo.buscar_jurisprudencia(consulta, tribunal=tribunal, tipo=tipo, limite=min(limite, 30))


def ler_precedente(tribunal: str, tipo: str, numero: str) -> dict:
    """Lê um precedente pelo número. Ex.: ('STJ','sumula','297'), ('STF','sumula vinculante','10'),
    ('STJ','repetitivo','1000'), ('STF','repercussao geral','69'), ('TST','oj','SDI1-191'), ('STF','adi','4277')."""
    return nucleo.ler_precedente(tribunal, tipo, numero)


def buscar_precedentes_verificados(consulta: str = "", tribunal: str | None = None, limite: int = 10) -> dict:
    """Busca nos acórdãos que já foram conferidos na fonte oficial e registrados (jurisprudência do escritório).
    Sem consulta, lista os mais recentes."""
    return nucleo.buscar_precedentes_verificados(consulta, tribunal=tribunal, limite=min(limite, 30))


def buscar_biblioteca(consulta: str, limite: int = 10) -> dict:
    """Busca na biblioteca própria: doutrina, artigos e pareceres em .md/.txt que o usuário adicionou."""
    return nucleo.buscar_biblioteca(consulta, limite=min(limite, 30))


def verificar_citacoes(texto: str) -> dict:
    """Confere TODAS as citações de um texto (artigos com §/incisos, súmulas, temas, OJs, ADI/ADPF, acórdãos e nº CNJ).

    Status: OK, NAO_ENCONTRADO (não existe — remover), DIVERGENTE (§/inciso inexistente), REVOGADO,
    ATENCAO (súmula possivelmente cancelada), AMBIGUO (falta tribunal/seção), NAO_VERIFICAVEL (lei incompleta na
    base — conferir no Planalto) e NAO_VERIFICADO (acórdão ainda não conferido). Rode sempre antes de entregar.
    """
    return nucleo.verificar_citacoes(texto)


def listar_codigos() -> dict:
    """Lista os apelidos de leis aceitos (CC, CPC, CDC, CLT, CF, LGPD, Inquilinato…)."""
    return nucleo.listar_codigos()


def lacunas(limite: int = 50) -> dict:
    """Lista normas federais que estão sem artigos na base (incompletas na fonte) — candidatas a salvar_complemento."""
    return nucleo.lacunas(limite=min(limite, 500))


# ----------------------------------------------------------------------------- escrita (só no modo local)

def registrar_precedente(tribunal: str, classe: str, numero: str, url: str, ementa: str, relator: str = "",
                         orgao: str = "", data_julgamento: str = "", tese: str = "", uf: str = "", caso: str = "") -> dict:
    """Grava um acórdão DEPOIS de conferi-lo na página oficial do tribunal (número, ementa e dados batendo).

    url: página oficial onde foi conferido (stj.jus.br, stf.jus.br, tjrn.jus.br…). ementa: transcrita da fonte.
    Exemplo: tribunal='STJ', classe='REsp', numero='1.234.567', uf='SP'. A partir daí o verificador aceita a citação.
    """
    return nucleo.registrar_precedente(tribunal, classe, numero, url, ementa, relator=relator, orgao=orgao,
                                       data_julgamento=data_julgamento, tese=tese, uf=uf, caso=caso)


def salvar_complemento(lei: str, texto: str, fonte: str) -> dict:
    """Corrige uma lei incompleta na base: grava o texto oficial integral (copiado de planalto.gov.br ou outra fonte
    oficial, com a URL em 'fonte') e reindexa (~30 s). Só use com texto copiado da fonte, nunca reescrito."""
    return nucleo.salvar_complemento(lei, texto, fonte)


def baixar_oficial(lei: str, url: str) -> dict:
    """Corrige uma lei incompleta baixando o texto oficial direto da fonte (ex.: a página compilada no
    planalto.gov.br), convertendo-o com o conversor do próprio ctresb/leis (sem texto revogado) e reindexando.
    Prefira isto a salvar_complemento: o texto não passa por você, então não há risco de alteração."""
    return nucleo.baixar_oficial(lei, url)


def reindexar() -> dict:
    """Reconstrói o índice (repositório + complementos + biblioteca). Use depois de adicionar arquivos à biblioteca."""
    return nucleo.reindexar()


def diagnostico() -> dict:
    """Confere a instalação: versão da base de leis, se está pronta (ou baixando), onde ficam a base (cache), a pasta de
    casos e os dados do escritório. Rode primeiro quando algo falhar e mostre os caminhos ao usuário."""
    out = {"base": base.status(), "caminhos": config.tudo()}
    try:
        n = nucleo.conexao().execute("SELECT count(*) FROM normas").fetchone()[0]
        out.update(base_ok=bool(nucleo.ler_artigo("CC", "412").get("encontrado")), normas_indexadas=n)
    except Exception as e:  # noqa: BLE001
        out.update(base_ok=False, aviso=str(e))
    out["pasta_casos"] = casos.raiz()
    out["pasta_casos_windows"] = casos.caminho_windows(casos.raiz())
    return out


def atualizar_base(forcar: bool = False) -> dict:
    """Confere se há base de leis nova na Release do GitHub e baixa (≈1 min); remonta a cópia local com os
    complementos e a biblioteca do usuário. Normalmente é automático (na 1ª vez e a cada 7 dias)."""
    return base.atualizar(forcar)


# ----------------------------------------------------------------------------- casos (pastas do usuário)

def caso_listar(todos: bool = False) -> dict:
    """Lista os casos (abertos; todos=True inclui encerrados) com fase e próximo passo, e a pasta raiz."""
    return casos.listar(todos)


def caso_status(caso: str) -> dict:
    """Tudo de um caso: partes, fase, prazos, eventos, documentos por categoria, links e próximo passo.
    caso: id (2026-001) ou parte do nome da pasta."""
    return casos.status(caso)


def caso_prazos(dias: int = 30) -> dict:
    """Prazos abertos de todos os casos nos próximos N dias, do mais próximo ao mais distante."""
    return casos.prazos(dias)


def caso_entrada() -> dict:
    """Arquivos soltos na pasta _ENTRADA, esperando classificação."""
    return casos.entrada()


def caso_ler_documento(caminho: str, caso: str | None = None, inicio: int = 0) -> dict:
    """Texto de um documento da pasta de casos (.md, .txt, .pdf, .docx, .eml). caminho: o 'arquivo' que caso_status /
    caso_arquivar devolvem (informe também 'caso'), um caminho absoluto ou do Windows (C:\\Users\\...).
    Textos longos vêm em partes: chame de novo com inicio='proximo_inicio'."""
    return casos.ler_documento(caminho, inicio, caso)


def caso_novo(titulo: str, tipo: str = "outro", area: str | None = None, papel: str | None = None,
              partes: list[str] | None = None, processo: str | None = None, tribunal: str | None = None,
              notas: str | None = None) -> dict:
    """Abre um caso com as pastas 01-documentos … 06-decisoes. tipo: contrato, processo, consulta, negociacao,
    cobranca, outro. papel: lado do cliente (comprador, locatário, autor, réu…). partes: ["Nome:papel", ...]."""
    return casos.novo(titulo, tipo, area, papel, partes, processo, tribunal, notas)


def caso_arquivar(caso: str, arquivo: str, categoria: str, descricao: str, data: str | None = None,
                  nota: str | None = None, mover: bool = False) -> dict:
    """Guarda um arquivo no caso, renomeado AAAA-MM-DD_descricao, com SHA-256. arquivo: caminho na máquina do usuário
    (aceita C:\\Users\\...\\Downloads\\x.pdf). categoria: documentos, provas, pecas, pesquisa, comunicacoes,
    decisoes. data: do documento/fato. Da _ENTRADA move; de outro lugar copia (mover=True para mover)."""
    return casos.arquivar(caso, arquivo, categoria, descricao, data, nota, mover)


def caso_salvar_texto(caso: str, categoria: str, descricao: str, conteudo: str, extensao: str = "md",
                      data: str | None = None) -> dict:
    """Grava no caso um texto produzido na conversa (análise de contrato, estratégia, minuta, notificação) como
    arquivo .md (ou outra extensão de texto). Use categoria 'pesquisa' para análises e 'pecas' para minutas."""
    return casos.salvar_texto(caso, categoria, descricao, conteudo, extensao, data)


def caso_evento(caso: str, descricao: str, data: str | None = None) -> dict:
    """Registra um fato na linha do tempo do caso (data do fato, AAAA-MM-DD ou DD/MM/AAAA)."""
    return casos.evento(caso, descricao, data)


def caso_prazo(caso: str, descricao: str, data: str | None = None, cumprido: bool = False) -> dict:
    """Registra um prazo (data limite). cumprido=True marca como cumprido o prazo cuja descrição contém o texto."""
    return casos.prazo(caso, descricao, data, cumprido)


def caso_fase(caso: str, fase: str) -> dict:
    """Muda a fase: intake, analise, negociacao, notificacao, pre-processual, judicial, recurso, execucao,
    acompanhamento, encerrado."""
    return casos.fase(caso, fase)


def caso_passo(caso: str, acao: str, motivo: str | None = None, skill: str | None = None) -> dict:
    """Registra o próximo passo do caso (aparece no RESUMO.md e no _INDICE.md)."""
    return casos.passo(caso, acao, motivo, skill)


def caso_link(caso: str, url: str, descricao: str = "") -> dict:
    """Guarda um link no caso (anúncio, processo eletrônico, lei, matrícula online…)."""
    return casos.link(caso, url, descricao)


def caso_atualizar(caso: str, titulo: str | None = None, area: str | None = None, papel_cliente: str | None = None,
                   numero_processo: str | None = None, tribunal: str | None = None, notas: str | None = None,
                   status: str | None = None, partes: list[str] | None = None) -> dict:
    """Corrige dados do caso ou acrescenta partes (["Nome:papel"])."""
    return casos.atualizar(caso, titulo=titulo, area=area, papel_cliente=papel_cliente, numero_processo=numero_processo,
                           tribunal=tribunal, notas=notas, status=status, partes=partes)


LEITURA = [buscar_legislacao, ler_artigo, info_norma, buscar_norma, buscar_jurisprudencia, ler_precedente,
           buscar_precedentes_verificados, buscar_biblioteca, verificar_citacoes, listar_codigos, lacunas]
ESCRITA = [registrar_precedente, baixar_oficial, salvar_complemento, reindexar, atualizar_base]
# Casos ficam na máquina do usuário: só no modo local (stdio), nunca no servidor HTTP público.
CASOS = [diagnostico, caso_listar, caso_status, caso_prazos, caso_entrada, caso_ler_documento, caso_novo, caso_arquivar,
         caso_salvar_texto, caso_evento, caso_prazo, caso_fase, caso_passo, caso_link, caso_atualizar]


def criar_app(somente_leitura: bool):
    app = _Server("advogado-br", instructions=INSTRUCOES)
    for fn in LEITURA + ([] if somente_leitura else ESCRITA + CASOS):
        app.tool()(_amigavel(fn))
    return app


def _amigavel(fn):
    """Enquanto a base baixa (ou sem internet na 1ª vez), devolve um aviso útil em vez de um erro técnico."""
    @functools.wraps(fn)
    def envolvida(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except nucleo.BaseIndisponivel as e:
            return {"ok": False, "base_indisponivel": True, "aviso": str(e), "status": base.status()}
    return envolvida


def main():
    ap = argparse.ArgumentParser(description="Servidor MCP leis-br")
    ap.add_argument("--http", action="store_true", help="servir por HTTP (Streamable HTTP) em vez de stdio")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--somente-leitura", action="store_true",
                    help="não expõe ferramentas de escrita (obrigatório em servidor público)")
    a = ap.parse_args()
    app = criar_app(a.somente_leitura or (a.http and os.environ.get("LEIS_ESCRITA_HTTP") != "1"))
    base.iniciar_em_segundo_plano()
    if not a.http:
        app.run()
        return
    if _SDK2:
        kwargs = {"host": a.host, "port": a.port, "stateless_http": True}
        if a.host not in ("127.0.0.1", "localhost"):
            try:  # atrás de proxy/domínio próprio: não restringir o Host aceito
                from mcp.server.transport_security import TransportSecuritySettings
                kwargs["transport_security"] = TransportSecuritySettings(enable_dns_rebinding_protection=False)
            except ImportError:
                pass
        app.run("streamable-http", **kwargs)
    else:
        app.settings.host, app.settings.port = a.host, a.port
        app.settings.stateless_http = True
        app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
