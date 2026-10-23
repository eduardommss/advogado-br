#!/usr/bin/env python3
"""Indexa o repositório ctresb/leis num SQLite FTS5, dispositivo por dispositivo.

Usado em dois lugares: pela GitHub Action (gera a base completa publicada na Release) e pelo servidor, para
aplicar localmente os complementos e a biblioteca do usuário sobre a base baixada.

Uso (gerar a base completa):
    python3 mcp/indexador.py --repo leis/ --saida leis.db --complementos dados/complementos --origem <commit>

- Leis: cada artigo vira um registro (texto do artigo com parágrafos e incisos); artigos longos são fatiados.
- Jurisprudência: cada súmula/tema/OJ vira um registro (enunciado/tese).
- Complementos: arquivo com o mesmo caminho relativo do repositório substitui o original (corrige normas incompletas).
- Biblioteca: .md/.txt próprios (doutrina, artigos, pareceres), indexados por blocos de parágrafos.
"""
import argparse
import os
import re
import sqlite3
import sys
import time
import unicodedata

PASTAS_PADRAO = ["constituicao.md", "federal", "jurisprudencia", "reguladores", "estaduais", "tratados"]

RE_ART = re.compile(
    r"^\s*(?:\*\*|_)?\s*Art(?:igo)?\s*(?:\*\*)?\s*\.?\s*(?:\*\*)?\s*"
    r"(\d+(?:\.\d{3})*|[UÚ]NICO)\s*(º|°|o)?\s*(?:-\s*([A-Z]{1,2})\b)?\s*\.?\s*(?:\*\*)?", re.I)
RE_ADCT = re.compile(r"^#+\s*ATO DAS DISPOSI[ÇC][ÕO]ES CONSTITUCIONAIS TRANSIT[ÓO]RIAS", re.I)
RE_JSON_BLOCK = re.compile(r"## Registro original do CNJ.*", re.S)


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalizar_artigo(num: str, sufixo: str | None) -> str:
    """'1.000' -> '1000'; '5' + 'A' -> '5-A'."""
    if not num[0].isdigit():
        return "unico"
    n = num.replace(".", "").lstrip("0") or "0"
    return f"{n}-{sufixo.upper()}" if sufixo else n


def ler_frontmatter(texto: str):
    meta = {}
    if not texto.startswith("---"):
        return meta, texto
    fim = texto.find("\n---", 3)
    if fim == -1:
        return meta, texto
    for linha in texto[3:fim].splitlines():
        m = re.match(r'^([a-z_]+):\s*(.*)$', linha)
        if m:
            v = m.group(2).strip().strip('"')
            meta[m.group(1)] = v
    return meta, texto[fim + 4:]


def classificar(caminho: str):
    """Retorna (esfera, uf, tribunal, tipo_juris) a partir do caminho."""
    partes = caminho.split("/")
    if partes[0] == "jurisprudencia":
        tribunal = partes[1].upper() if partes[1] != "outros-tribunais" else partes[2].upper()
        return "jurisprudencia", None, tribunal
    if partes[0] == "estaduais":
        return "estadual", partes[1].upper(), None
    if partes[0] == "constituicao.md":
        return "federal", None, None
    return partes[0], None, None


def dividir_artigos(corpo: str, constituicao: bool):
    """Gera (artigo_normalizado, rotulo, parte, texto)."""
    atual = None
    parte = ""
    buf = []
    for linha in corpo.splitlines():
        if constituicao and RE_ADCT.match(linha):
            if atual:
                yield (*atual, "\n".join(buf).strip())
            atual, buf = None, []
            parte = "ADCT"
            continue
        m = RE_ART.match(linha)
        if m:
            if atual:
                yield (*atual, "\n".join(buf).strip())
            art = normalizar_artigo(m.group(1), m.group(3))
            rotulo = "Art. " + m.group(1) + ("º" if m.group(2) else "") + (f"-{m.group(3).upper()}" if m.group(3) else "")
            atual = (art, rotulo, parte)
            buf = [linha]
        elif atual:
            if linha.startswith("#"):
                # título/capítulo novo: fecha o artigo, mas não começa outro
                yield (*atual, "\n".join(buf).strip())
                atual, buf = None, []
            else:
                buf.append(linha)
    if atual:
        yield (*atual, "\n".join(buf).strip())


def texto_jurisprudencia(corpo: str) -> str:
    corpo = RE_JSON_BLOCK.sub("", corpo)
    # Repetitivos do STJ: guarda só os campos úteis
    if "### teseFirmada" in corpo:
        campos = {}
        for bloco in re.split(r"^### ", corpo, flags=re.M)[1:]:
            nome, _, valor = bloco.partition("\n")
            campos[nome.strip()] = valor.strip()
        uteis = ["situacao", "questaoSubmetidaAJulgamento", "teseFirmada", "delimitacaoJulgado",
                 "referenciaSumular", "orgaoJulgador", "dataJulgamento", "Assuntos"]
        return "\n\n".join(f"{k}: {campos[k]}" for k in uteis if campos.get(k))
    return corpo.strip()


def esquema(db):
    db.executescript("""
    DROP TABLE IF EXISTS normas; DROP TABLE IF EXISTS dispositivos;
    DROP TABLE IF EXISTS dispositivos_fts; DROP TABLE IF EXISTS normas_fts;
    CREATE TABLE normas(
        id INTEGER PRIMARY KEY, caminho TEXT UNIQUE, titulo TEXT, tipo TEXT, numero TEXT,
        data TEXT, ementa TEXT, revogada INTEGER, situacao TEXT, versao_texto TEXT,
        fonte TEXT, esfera TEXT, uf TEXT, tribunal TEXT, arquivo TEXT);
    CREATE TABLE dispositivos(
        id INTEGER PRIMARY KEY, norma_id INTEGER, artigo TEXT, rotulo TEXT, parte TEXT,
        texto TEXT, revogado INTEGER);
    CREATE INDEX ix_disp ON dispositivos(norma_id, artigo);
    DROP TABLE IF EXISTS trechos;
    CREATE TABLE trechos(id INTEGER PRIMARY KEY, disp_id INTEGER);
    CREATE INDEX ix_norma_num ON normas(numero, tipo);
    CREATE INDEX ix_norma_trib ON normas(tribunal, tipo, numero);
    CREATE VIRTUAL TABLE dispositivos_fts USING fts5(
        texto, contexto, content='', tokenize='unicode61 remove_diacritics 2');
    CREATE VIRTUAL TABLE normas_fts USING fts5(
        titulo, ementa, content='', tokenize='unicode61 remove_diacritics 2');
    """)


TAM_TRECHO = 1200


def fatiar(texto: str):
    """Artigos longos viram vários trechos; cada trecho leva o caput junto, para manter o contexto."""
    if len(texto) <= TAM_TRECHO:
        return [texto]
    blocos = [b for b in re.split(r"\n\s*\n", texto) if b.strip()]
    caput = blocos[0][:300]
    out, atual = [texto[:TAM_TRECHO]], ""
    for b in blocos[1:]:
        if len(atual) + len(b) > TAM_TRECHO and atual:
            out.append(caput + "\n" + atual)
            atual = ""
        atual += "\n" + b
    if atual:
        out.append(caput + "\n" + atual)
    return out


def inserir(db, nid, art, rotulo, parte, texto, revogado, contexto):
    c = db.execute("INSERT INTO dispositivos(norma_id,artigo,rotulo,parte,texto,revogado) VALUES(?,?,?,?,?,?)",
                   (nid, art, rotulo, parte, texto, revogado))
    did = c.lastrowid
    for pedaco in fatiar(texto):
        tid = db.execute("INSERT INTO trechos(disp_id) VALUES(?)", (did,)).lastrowid
        db.execute("INSERT INTO dispositivos_fts(rowid,texto,contexto) VALUES(?,?,?)", (tid, pedaco, contexto))


RE_REVOGADO = re.compile(r"^\s*(?:\*\*)?Art[^\n]{0,30}?\(?\s*(?:\*)?\s*\(?Revogad", re.I)


def indexar_biblioteca(db, pasta: str) -> int:
    """Cada .md/.txt vira uma 'obra' (esfera biblioteca), fatiada por blocos de parágrafos."""
    pasta = os.path.abspath(os.path.expanduser(pasta))
    if not os.path.isdir(pasta):
        return 0
    n = 0
    for raiz, _, nomes in os.walk(pasta):
        for nome in sorted(nomes):
            if not nome.lower().endswith((".md", ".txt")):
                continue
            cam = os.path.join(raiz, nome)
            texto = open(cam, encoding="utf-8", errors="replace").read()
            meta, corpo = ler_frontmatter(texto)
            titulo = meta.get("titulo") or os.path.splitext(nome)[0].replace("-", " ").replace("_", " ")
            autor = meta.get("autor", "")
            rel = "biblioteca/" + os.path.relpath(cam, pasta).replace(os.sep, "/")
            remover_norma(db, rel)
            nid = db.execute(
                "INSERT INTO normas(caminho,titulo,tipo,ementa,revogada,versao_texto,fonte,esfera,arquivo) VALUES(?,?,?,?,?,?,?,?,?)",
                (rel, titulo, "Biblioteca", autor, 0, "biblioteca própria", meta.get("fonte"), "biblioteca", cam)).lastrowid
            db.execute("INSERT INTO normas_fts(rowid,titulo,ementa) VALUES(?,?,?)", (nid, titulo, autor))
            blocos, atual = [], ""
            for par in re.split(r"\n\s*\n", corpo):
                if len(atual) + len(par) > TAM_TRECHO and atual:
                    blocos.append(atual.strip())
                    atual = ""
                atual += "\n\n" + par
            if atual.strip():
                blocos.append(atual.strip())
            for k, b in enumerate(blocos, 1):
                inserir(db, nid, None, f"{titulo} — trecho {k}", "", b, 0, f"{titulo} {autor}")
            n += 1
    return n


def indexar_texto(db, rel: str, texto: str, arquivo: str | None = None) -> int:
    """Indexa uma norma/precedente (conteúdo de um .md no layout do ctresb/leis). Devolve nº de dispositivos."""
    meta, corpo = ler_frontmatter(texto)
    esfera, uf, tribunal = classificar(rel)
    constituicao = rel == "constituicao.md"
    if constituicao:
        meta = {"titulo": "Constituição da República Federativa do Brasil de 1988", "tipo": "Constituição",
                "numero": "1988", "data": "1988-10-05", "ementa": "Constituição Federal",
                "revogada": "false", "versao_texto": "compilada (texto vigente)",
                "fonte": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm"}
    cur = db.execute(
        "INSERT INTO normas(caminho,titulo,tipo,numero,data,ementa,revogada,situacao,versao_texto,fonte,esfera,uf,tribunal,arquivo)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rel, meta.get("titulo"), meta.get("tipo"), meta.get("numero"), meta.get("data"), meta.get("ementa"),
         1 if meta.get("revogada") == "true" else 0, meta.get("situacao"), meta.get("versao_texto"),
         meta.get("fonte"), esfera, uf, tribunal, arquivo))
    nid = cur.lastrowid
    db.execute("INSERT INTO normas_fts(rowid,titulo,ementa) VALUES(?,?,?)",
               (nid, meta.get("titulo") or "", meta.get("ementa") or ""))
    contexto = f"{meta.get('titulo','')} {meta.get('ementa','')}"
    n = 0
    if esfera == "jurisprudencia":
        inserir(db, nid, None, meta.get("titulo"), "", texto_jurisprudencia(corpo)[:20000], 0, contexto)
        return 1
    for art, rotulo, parte, t in dividir_artigos(corpo, constituicao):
        rev = 1 if RE_REVOGADO.match(t[:300]) and len(t) < 400 else 0
        inserir(db, nid, art, rotulo, parte, t, rev, contexto)
        n += 1
    if not n:  # norma sem artigos reconhecíveis: indexa o corpo inteiro
        inserir(db, nid, None, "texto integral", "", corpo.strip()[:20000], 0, contexto)
        n = 1
    return n


def remover_norma(db, rel: str) -> None:
    """Tira uma norma do índice (as entradas órfãs do FTS sem conteúdo deixam de casar no JOIN)."""
    for (nid,) in db.execute("SELECT id FROM normas WHERE caminho=?", (rel,)).fetchall():
        db.execute("DELETE FROM trechos WHERE disp_id IN (SELECT id FROM dispositivos WHERE norma_id=?)", (nid,))
        db.execute("DELETE FROM dispositivos WHERE norma_id=?", (nid,))
        db.execute("DELETE FROM normas WHERE id=?", (nid,))


def aplicar_complementos(db, pasta: str) -> int:
    """Cada .md da pasta (mesmo layout do ctresb/leis) substitui a norma de mesmo caminho, ou entra como nova."""
    pasta = os.path.abspath(os.path.expanduser(pasta))
    if not os.path.isdir(pasta):
        return 0
    n = 0
    for raiz, _, nomes in os.walk(pasta):
        for nome in sorted(nomes):
            if not nome.endswith(".md") or nome.upper() == "README.MD":
                continue
            cam = os.path.join(raiz, nome)
            rel = os.path.relpath(cam, pasta).replace(os.sep, "/")
            remover_norma(db, rel)
            indexar_texto(db, rel, open(cam, encoding="utf-8", errors="replace").read(), cam)
            n += 1
    return n


def remover_biblioteca(db) -> None:
    for (rel,) in db.execute("SELECT caminho FROM normas WHERE esfera='biblioteca'").fetchall():
        remover_norma(db, rel)


def main():
    """Gera o índice completo a partir de um clone do ctresb/leis (usado pela GitHub Action)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="clone (parcial) do ctresb/leis")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--pastas", nargs="*", default=PASTAS_PADRAO)
    ap.add_argument("--complementos", help="pasta de complementos (mesmo layout do repositório)")
    ap.add_argument("--biblioteca", help="pasta com .md/.txt de doutrina/pareceres")
    ap.add_argument("--origem", default="", help="identificação da origem (ex.: commit do ctresb/leis)")
    a = ap.parse_args()

    repo = os.path.abspath(os.path.expanduser(a.repo))
    tmp = a.saida + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    esquema(db)

    arquivos = []
    for p in a.pastas:
        alvo = os.path.join(repo, p)
        if os.path.isfile(alvo):
            arquivos.append(alvo)
        elif os.path.isdir(alvo):
            for raiz, _, nomes in os.walk(alvo):
                arquivos += [os.path.join(raiz, n) for n in nomes if n.endswith(".md")]
    print(f"{len(arquivos)} arquivos", file=sys.stderr)

    t0 = time.time()
    n_disp = 0
    for i, caminho_abs in enumerate(sorted(arquivos), 1):
        try:
            texto = open(caminho_abs, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        n_disp += indexar_texto(db, os.path.relpath(caminho_abs, repo).replace(os.sep, "/"), texto)
        if i % 5000 == 0:
            db.commit()
            print(f"  {i}/{len(arquivos)} arquivos, {n_disp} dispositivos, {time.time()-t0:.0f}s", file=sys.stderr)

    n_comp = aplicar_complementos(db, a.complementos) if a.complementos else 0
    n_bib = indexar_biblioteca(db, a.biblioteca) if a.biblioteca else 0
    db.execute("CREATE TABLE meta(chave TEXT PRIMARY KEY, valor TEXT)")
    db.executemany("INSERT INTO meta VALUES(?, ?)", [
        ("origem", a.origem), ("indexado_em", time.strftime("%Y-%m-%d %H:%M")), ("complementos", str(n_comp)),
        ("esquema", "2")])
    db.commit()
    db.execute("INSERT INTO dispositivos_fts(dispositivos_fts) VALUES('optimize')")
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, a.saida)
    print(f"OK: {len(arquivos)} normas (+{n_comp} complementos, {n_bib} obras), {n_disp} dispositivos "
          f"em {time.time()-t0:.0f}s -> {a.saida}", file=sys.stderr)


if __name__ == "__main__":
    main()
