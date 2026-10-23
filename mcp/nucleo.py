"""Núcleo de consulta à base ctresb/leis indexada (SQLite FTS5).

Usado pelo servidor MCP (servidor.py) e pela linha de comando (consultar.py).
Caminhos: ver config.py (variáveis de ambiente > ~/.config/advogado-br/config.json > padrões).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base  # noqa: E402
import config  # noqa: E402


class BaseIndisponivel(RuntimeError):
    """A base de leis ainda não está pronta (primeiro download em andamento, sem internet...)."""

AQUI = Path(__file__).resolve().parent
CODIGOS_YAML = AQUI / "codigos.yaml"

STOPWORDS = set("""a o as os e de da do das dos em no na nos nas um uma uns umas por para pelo pela pelos pelas
com sem ao aos à às que se ou como mais menos ser sao é foi ha há sobre entre ate até qual quais quando
onde este esta isso esse essa seu sua seus suas lei art artigo artigos""".split())


# ----------------------------------------------------------------------------- util

def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _chave(s: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(s).upper().strip())


@lru_cache(maxsize=1)
def conexao() -> sqlite3.Connection:
    caminho = base.caminho_trabalho()
    if caminho is None or not caminho.exists():
        raise BaseIndisponivel(base.mensagem_indisponivel())
    from urllib.parse import quote
    db = sqlite3.connect(f"file:{quote(caminho.as_posix(), safe='/:')}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def recarregar() -> None:
    """Reabre o índice (depois de uma reindexação)."""
    try:
        conexao().close()
    except Exception:
        pass
    conexao.cache_clear()


base.ao_trocar(recarregar)


@lru_cache(maxsize=1)
def codigos() -> dict[str, str]:
    out: dict[str, str] = {}
    if CODIGOS_YAML.exists():
        for linha in CODIGOS_YAML.read_text(encoding="utf-8").splitlines():
            linha = linha.split("#", 1)[0].strip()
            if ":" in linha:
                k, v = linha.split(":", 1)
                out[_chave(k)] = v.strip()
    return out


@lru_cache(maxsize=1)
def _caminhos_principais() -> set[str]:
    return set(codigos().values())


URL_MD = "https://github.com/ctresb/leis/blob/main/"


def _norma_dict(r: sqlite3.Row) -> dict:
    d = {k: r[k] for k in ("titulo", "tipo", "numero", "data", "ementa", "situacao", "versao_texto", "fonte",
                           "esfera", "uf", "tribunal", "caminho")}
    d["revogada"] = bool(r["revogada"])
    local = r["arquivo"] if "arquivo" in r.keys() and r["arquivo"] else None
    d["arquivo_local"] = local or (URL_MD + r["caminho"] if r["esfera"] != "biblioteca" else None)
    return d


def _avisos(norma: dict, revogado: bool = False) -> list[str]:
    av = []
    if norma.get("revogada"):
        av.append("NORMA REVOGADA segundo a fonte — não citar como vigente.")
    if revogado:
        av.append("DISPOSITIVO REVOGADO — não citar como vigente.")
    vt = (norma.get("versao_texto") or "").lower()
    if norma.get("esfera") not in ("jurisprudencia", "biblioteca") and vt and "compilad" not in vt and "atualizad" not in vt:
        av.append(f"Texto na versão '{norma.get('versao_texto')}' (pode não incluir alterações posteriores). Confira a fonte oficial.")
    return av


# ----------------------------------------------------------------------------- resolver lei

_TIPOS = [
    (r"decreto[\s-]*lei|\bdl\b|\bdel\b", "Decreto-Lei"),
    (r"lei\s+complementar|\blc\b|\blcp\b", "Lei Complementar"),
    (r"\blei\b", "Lei Ordinária"),
]


def resolver_lei(ref: str) -> dict | None:
    """Aceita apelido (CC, CPC, CDC, CLT, CF...), 'Lei 8.078/1990', 'Decreto-Lei 5.452', 'LC 123' ou caminho."""
    if not ref:
        return None
    db = conexao()
    ref = ref.strip()
    k = _chave(ref)
    k = re.sub(r"^(DO|DA|O|A)\s+", "", k)
    # 1) apelido
    alias = codigos().get(k) or codigos().get(k.replace("/", " ").strip())
    if alias:
        r = db.execute("SELECT * FROM normas WHERE caminho=?", (alias,)).fetchone()
        if r:
            return _norma_dict(r)
    # 2) caminho
    if ref.endswith(".md"):
        r = db.execute("SELECT * FROM normas WHERE caminho=? OR ? LIKE '%' || caminho", (ref, ref)).fetchone()
        if r:
            return _norma_dict(r)
    # 3) tipo + número (+ ano)
    m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:\s*[/,-]\s*|\s+de\s+(?:\d{1,2}\D+)?)?(\d{2,4})?", ref)
    if not m:
        return None
    numero = m.group(1).replace(".", "")
    ano = m.group(2)
    if ano and len(ano) == 2:
        ano = ("19" if int(ano) > 30 else "20") + ano
    tipo = None
    low = sem_acento(ref.lower())
    for padrao, t in _TIPOS:
        if re.search(padrao, low):
            tipo = t
            break
    sql = "SELECT * FROM normas WHERE numero=? AND esfera='federal'"
    params: list = [numero]
    if tipo:
        sql += " AND tipo=?"
        params.append(tipo)
    linhas = db.execute(sql, params).fetchall()
    if ano:
        com_ano = [r for r in linhas if (r["data"] or "").startswith(ano)]
        linhas = com_ano or linhas
    if not linhas:
        return None
    # preferir: não revogada, texto compilado, mais recente
    linhas.sort(key=lambda r: (r["revogada"], "compilad" not in (r["versao_texto"] or ""), -(int((r["data"] or "0")[:4] or 0))))
    return _norma_dict(linhas[0])


def _norma_id(caminho: str) -> int:
    return conexao().execute("SELECT id FROM normas WHERE caminho=?", (caminho,)).fetchone()[0]


# ----------------------------------------------------------------------------- artigos

def normalizar_artigo(a: str) -> str:
    a = sem_acento(str(a)).lower().strip()
    a = re.sub(r"^(art(igo)?s?\.?)\s*", "", a)
    if a.startswith("unic"):
        return "unico"
    m = re.match(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*[ºo°]?\s*(?:-\s*([a-z]{1,2})\b)?", a)
    if not m:
        return a
    n = m.group(1).replace(".", "").lstrip("0") or "0"
    return f"{n}-{m.group(2).upper()}" if m.group(2) else n


def ler_artigo(lei: str, artigo: str, parte: str | None = None, vizinhos: int = 0) -> dict:
    norma = resolver_lei(lei)
    if not norma:
        return {"encontrado": False, "erro": f"Lei não reconhecida: {lei!r}. Use buscar_legislacao ou listar_codigos."}
    db = conexao()
    nid = _norma_id(norma["caminho"])
    art = normalizar_artigo(artigo)
    linhas = db.execute("SELECT id, artigo, rotulo, parte, texto, revogado FROM dispositivos WHERE norma_id=? AND artigo=?",
                        (nid, art)).fetchall()
    if parte is not None:
        linhas = [r for r in linhas if (r["parte"] or "").upper() == parte.upper()] or linhas
    else:
        linhas = [r for r in linhas if not r["parte"]] or linhas
    if not linhas:
        n_art = db.execute("SELECT count(*) FROM dispositivos WHERE norma_id=? AND artigo IS NOT NULL", (nid,)).fetchone()[0]
        erro = f"Art. {artigo} não existe em {norma['titulo']} (na base indexada)."
        if n_art <= 1:
            erro += (" ATENÇÃO: o arquivo desta norma na base está incompleto (sem artigos — ex.: só retificação). "
                     "Isso NÃO prova que o artigo não existe: confira no texto oficial (planalto.gov.br) antes de concluir.")
        return {"encontrado": False, "erro": erro,
                "norma": {k: norma[k] for k in ("titulo", "ementa", "fonte", "versao_texto", "arquivo_local")}}
    alvo = linhas[0]
    resultado = {
        "encontrado": True,
        "norma": {k: norma[k] for k in ("titulo", "ementa", "fonte", "versao_texto", "revogada", "arquivo_local")},
        "artigo": alvo["rotulo"], "parte": alvo["parte"] or None, "texto": alvo["texto"],
        "avisos": _avisos(norma, bool(alvo["revogado"])),
    }
    if len(linhas) > 1:
        resultado["avisos"].append(f"Há {len(linhas)} artigos com esse número (ex.: ADCT). Use 'parte'.")
    if vizinhos:
        viz = db.execute("SELECT rotulo, texto FROM dispositivos WHERE norma_id=? AND id BETWEEN ? AND ? AND id<>? ORDER BY id",
                         (nid, alvo["id"] - vizinhos, alvo["id"] + vizinhos, alvo["id"])).fetchall()
        resultado["vizinhos"] = [{"artigo": v["rotulo"], "texto": v["texto"]} for v in viz]
    return resultado


def info_norma(lei: str) -> dict:
    norma = resolver_lei(lei)
    if not norma:
        return {"encontrado": False, "erro": f"Lei não reconhecida: {lei!r}"}
    n = conexao().execute("SELECT count(*), sum(revogado) FROM dispositivos WHERE norma_id=?",
                          (_norma_id(norma["caminho"]),)).fetchone()
    return {"encontrado": True, **norma, "artigos_indexados": n[0], "artigos_revogados": n[1] or 0,
            "avisos": _avisos(norma)}


# ----------------------------------------------------------------------------- busca

def _termos(consulta: str) -> list[str]:
    toks = re.findall(r"\w+", sem_acento(consulta).lower())
    return [t for t in toks if t not in STOPWORDS and (len(t) > 2 or t.isdigit())]


def _fts(termos: list[str], modo: str) -> str:
    partes = []
    for t in termos:
        if len(t) >= 7 and not t.isdigit():
            partes.append(f'"{t[:6]}"*')  # radical: prescricao/prescreve, abusividade/abusiva
        elif len(t) >= 5 and not t.isdigit():
            partes.append(f'"{t[:-1]}"*')  # plural/gênero: multas/multa, prazos/prazo
        else:
            partes.append(f'"{t}"')
    return f" {modo} ".join(partes)


def _trecho(texto: str, termos: list[str], tam: int = 320) -> str:
    plano = sem_acento(texto).lower()
    posicoes = sorted((m.start(), t) for t in termos for m in re.finditer(re.escape(t[:6]), plano))
    melhor, pos = -1, 0
    for p, _ in posicoes:  # janela que reúne mais termos distintos da consulta
        n = len({t for q, t in posicoes if p <= q < p + tam})
        if n > melhor:
            melhor, pos = n, p
    ini = max(0, pos - tam // 4)
    s = texto[ini:ini + tam].replace("\n", " ")
    return ("…" if ini else "") + s + ("…" if ini + tam < len(texto) else "")


def _buscar(consulta: str, filtros_sql: str, params: list, limite: int) -> list[dict]:
    termos = _termos(consulta)
    if not termos:
        return []
    db = conexao()
    principais = _caminhos_principais()
    vistos: dict[int, dict] = {}
    for modo in ("AND", "OR"):
        sql = f"""
            SELECT d.id, d.rotulo, d.parte, d.texto, d.revogado, n.*, bm25(dispositivos_fts, 1.0, 0.35) AS score
            FROM dispositivos_fts f JOIN trechos tr ON tr.id=f.rowid JOIN dispositivos d ON d.id=tr.disp_id
            JOIN normas n ON n.id=d.norma_id
            WHERE dispositivos_fts MATCH ? {filtros_sql}
            ORDER BY score LIMIT ?"""
        try:
            linhas = db.execute(sql, [_fts(termos, modo), *params, limite * 6]).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in linhas:
            if r["id"] in vistos:
                continue
            peso = r["score"] * (1.6 if r["caminho"] in principais else 1.0) * (1.0 if modo == "AND" else 0.6)
            norma = _norma_dict(r)
            vistos[r["id"]] = {
                "norma": r["titulo"], "ementa": (r["ementa"] or "")[:200], "dispositivo": r["rotulo"],
                "parte": r["parte"] or None, "trecho": _trecho(r["texto"], termos),
                "fonte": r["fonte"], "arquivo_local": norma["arquivo_local"],
                "avisos": _avisos(norma, bool(r["revogado"])), "_peso": peso,
                "ref": {"lei": r["caminho"], "artigo": r["rotulo"]} if r["esfera"] != "jurisprudencia"
                else {"tribunal": r["tribunal"], "tipo": r["tipo"], "numero": r["numero"]},
            }
    res = sorted(vistos.values(), key=lambda x: x["_peso"])[:limite]
    for x in res:
        x.pop("_peso")
    return res


def buscar_legislacao(consulta: str, lei: str | None = None, uf: str | None = None,
                      incluir_revogadas: bool = False, limite: int = 10) -> dict:
    filtros, params = ["n.esfera NOT IN ('jurisprudencia', 'biblioteca')"], []
    if lei:
        norma = resolver_lei(lei)
        if not norma:
            return {"resultados": [], "erro": f"Lei não reconhecida: {lei!r}"}
        filtros.append("n.caminho = ?")
        params.append(norma["caminho"])
    if uf:
        filtros.append("(n.uf = ? OR n.uf IS NULL)")
        params.append(uf.upper())
    if not incluir_revogadas:
        filtros.append("n.revogada = 0 AND d.revogado = 0")
    res = _buscar(consulta, " AND " + " AND ".join(filtros), params, limite)
    return {"consulta": consulta, "total": len(res), "resultados": res}


_TIPO_JURIS = {
    "sumula": "Súmula", "súmula": "Súmula",
    "sumula vinculante": "Súmula vinculante", "súmula vinculante": "Súmula vinculante", "sv": "Súmula vinculante",
    "repetitivo": "Tema repetitivo", "tema repetitivo": "Tema repetitivo",
    "repercussao geral": "Tema de repercussão geral", "repercussão geral": "Tema de repercussão geral",
    "rg": "Tema de repercussão geral", "oj": "Orientação Jurisprudencial",
    "adi": "ADI", "adc": "ADC", "adpf": "ADPF", "ado": "ADO", "puil": "PUIL",
}


def buscar_jurisprudencia(consulta: str, tribunal: str | None = None, tipo: str | None = None, limite: int = 10) -> dict:
    filtros, params = ["n.esfera = 'jurisprudencia'"], []
    if tribunal:
        filtros.append("n.tribunal = ?")
        params.append(tribunal.upper())
    if tipo:
        t = _TIPO_JURIS.get(tipo.lower().strip(), tipo)
        filtros.append("n.tipo = ?")
        params.append(t)
    res = _buscar(consulta, " AND " + " AND ".join(filtros), params, limite)
    for r in res:
        r["dispositivo"] = r.pop("norma")
    return {"consulta": consulta, "total": len(res), "resultados": res,
            "observacao": "A base cobre precedentes vinculantes/sumulados (súmulas, SV, repetitivos, RG, OJs, controle "
                          "concentrado). Acórdãos comuns de TJs/STJ não estão aqui: pesquise nos sites dos tribunais."}


def ler_precedente(tribunal: str, tipo: str, numero: str) -> dict:
    db = conexao()
    t = _TIPO_JURIS.get(sem_acento(tipo).lower().strip(), _TIPO_JURIS.get(tipo.lower().strip(), tipo))
    trib = tribunal.upper().strip()
    num = str(numero).strip().upper().replace("Nº", "").replace("N.", "").strip()
    r = db.execute("SELECT * FROM normas WHERE tribunal=? AND tipo=? AND upper(numero)=?", (trib, t, num)).fetchone()
    if not r and t == "Orientação Jurisprudencial" and "-" not in num:
        r = db.execute("SELECT * FROM normas WHERE tribunal=? AND tipo=? AND upper(numero) LIKE ?",
                       (trib, t, f"%-{num}")).fetchone()
    if not r:
        return {"encontrado": False, "erro": f"{t} {numero} do {trib} não encontrado(a) na base."}
    d = db.execute("SELECT texto FROM dispositivos WHERE norma_id=?", (r["id"],)).fetchone()
    norma = _norma_dict(r)
    av = []
    sit = (r["situacao"] or "").lower()
    if any(p in sit for p in ("cancelad", "revogad", "superad")) or "cancelad" in (d["texto"] or "")[:400].lower():
        av.append(f"Situação: {r['situacao'] or 'verificar'} — pode estar CANCELADA/SUPERADA. Confira antes de citar.")
    return {"encontrado": True, "titulo": r["titulo"], "situacao": r["situacao"], "data": r["data"],
            "texto": d["texto"], "fonte": r["fonte"], "arquivo_local": norma["arquivo_local"], "avisos": av}


# ----------------------------------------------------------------------------- verificação de citações

_ROMANOS = r"(?-i:[IVXLCDM]+)"   # incisos sempre em maiúsculas
_NUM_ART = r"(?:\d{1,3}(?:\.\d{3})+|\d+)\s*[ºo°]?(?:\s*-\s*[A-Z]{1,2}\b)?"
_LEIS_CIT = (
    r"(CF(?:/88)?|Constitui[cç][aã]o(?:\s+Federal)?|CC(?:/02)?|C[oó]digo\s+Civil|CPC(?:/15)?|C[oó]digo\s+de\s+Processo\s+Civil|"
    r"CDC|C[oó]digo\s+de\s+Defesa\s+do\s+Consumidor|CLT|CP|C[oó]digo\s+Penal|CPP|CTN|ECA|LINDB|CTB|LGPD|"
    r"(?:Lei(?:\s+Complementar)?|LC|Decreto[\s-]*Lei|DL)\s*(?:n[ºo°.]*\s*)?\d{1,3}(?:\.\d{3})*(?:\s*/\s*\d{2,4})?)\b")
_SUBDIV = (r"(?:§+\s*\d+\s*[ºo°]?|par[aá]grafo\s+[uú]nico|caput|(?:inc(?:iso)?s?\.?\s*)?" + _ROMANOS +
           r"\b|al[ií]nea\s+\"?[a-z]\"?|[a-z]\))")
_RE_ART_CIT = re.compile(
    r"\bart(?:igo)?s?\.?\s*(" + _NUM_ART + r")"
    r"((?:\s*(?:,|\be\b)?\s*" + _SUBDIV + r")*)"
    r"\s*,?\s*(?:d[oa]s?\s+|,\s*)?" + _LEIS_CIT, re.I)
# "arts. 186 e 927 do CC", "arts. 389, 395 e 404 do Código Civil"
_RE_ART_LISTA = re.compile(
    r"\barts?\.?\s*((?:" + _NUM_ART + r"\s*(?:,|\be\b)\s*)+" + _NUM_ART + r")\s*,?\s*d[oa]s?\s+" + _LEIS_CIT, re.I)
_RE_SUMULA = re.compile(
    r"S[uú]mula\s+(Vinculante\s+)?(?:n[ºo°.]*\s*)?(\d+)(?:\s*(?:,?\s*d[oa]\s+|/)\s*(STF|STJ|TST|TNU|TCU|TRF4|STM)\b)?", re.I)
_RE_SV = re.compile(r"\bSV\s*(?:n[ºo°.]*\s*)?(\d+)\b")
_RE_TEMA = re.compile(
    r"Tema\s+(?:repetitivo\s+|de\s+repercuss[aã]o\s+geral\s+)?(?:n[ºo°.]*\s*)?(\d+)\s*(?:,?\s*d[oa]\s+|/)?\s*(STF|STJ|repercuss[aã]o\s+geral)?",
    re.I)
_RE_OJ = re.compile(r"\bOJ\s*(?:n[ºo°.]*\s*)?(\d+)\s*(?:,?\s*d[ao]\s+)?(SBDI-?[12]|SDI-?[12]|SDC)?", re.I)


def _confere_subdivisoes(texto_artigo: str, subdiv: str) -> list[str]:
    """Verifica se §§, incisos e parágrafo único citados existem no texto do artigo."""
    problemas = []
    plano = sem_acento(texto_artigo)
    for p in re.findall(r"§\s*(\d+)", subdiv):
        if not re.search(rf"§\s*{p}\s*[ºo°]?\b", plano):
            problemas.append(f"§ {p}º não encontrado no artigo")
    if re.search(r"par[aá]grafo\s+[uú]nico", subdiv, re.I) and not re.search(r"par[aá]grafo\s+unico", plano, re.I):
        problemas.append("parágrafo único não encontrado no artigo")
    for inc in re.findall(r"(?:^|[\s,])(" + _ROMANOS + r")\b", subdiv):
        if not re.search(rf"(?m)^\s*(?:\*\*)?{inc}\s*(?:\*\*)?\s*[-–—]", plano):
            problemas.append(f"inciso {inc} não encontrado no artigo")
    return problemas


def verificar_citacoes(texto: str) -> dict:
    """Extrai citações (artigos de lei, súmulas, temas, OJs) de um texto e confere cada uma na base."""
    itens = []

    def checar_artigo(citacao: str, art: str, subdiv: str, lei: str):
        lei_ref = re.sub(r"(CF|CC|CPC)/\d+", r"\1", lei.strip(), flags=re.I)
        r = ler_artigo(lei_ref, art)
        item = {"citacao": citacao, "tipo": "artigo"}
        if not r.get("encontrado"):
            incompleta = "incompleto" in (r.get("erro") or "")
            item.update(status="NAO_VERIFICAVEL" if incompleta else "NAO_ENCONTRADO", detalhe=r.get("erro"))
        else:
            problemas = _confere_subdivisoes(r["texto"], subdiv)
            revog = any("REVOGAD" in a for a in r["avisos"])
            item.update(status="REVOGADO" if revog else ("DIVERGENTE" if problemas else "OK"),
                        norma=r["norma"]["titulo"], texto_oficial=r["texto"][:1500], fonte=r["norma"]["fonte"],
                        detalhe="; ".join(problemas + r["avisos"]) or None)
        itens.append(item)

    ocupado: list[tuple[int, int]] = []
    for m in _RE_ART_LISTA.finditer(texto):
        ocupado.append(m.span())
        for num in re.findall(_NUM_ART, m.group(1)):
            checar_artigo(f"art. {num.strip()} ({m.group(0).strip()})", num, "", m.group(2))
    for m in _RE_ART_CIT.finditer(texto):
        if any(a <= m.start() < b for a, b in ocupado):
            continue
        checar_artigo(m.group(0).strip(), m.group(1), m.group(2) or "", m.group(3))
    for m in _RE_SUMULA.finditer(texto):
        vinc, num, trib = m.group(1), m.group(2), (m.group(3) or "").upper()
        if vinc:
            trib, tipo = "STF", "Súmula vinculante"
        else:
            tipo = "Súmula"
        item = {"citacao": m.group(0).strip(), "tipo": tipo}
        if not trib:
            item.update(status="AMBIGUO", detalhe="Tribunal não indicado — cite 'do STF', 'do STJ', 'do TST'…")
        else:
            r = ler_precedente(trib, tipo, num)
            item.update(status=("ATENCAO" if r.get("avisos") else "OK") if r.get("encontrado") else "NAO_ENCONTRADO",
                        texto_oficial=(r.get("texto") or "")[:1200] or None, fonte=r.get("fonte"),
                        detalhe="; ".join(r.get("avisos", [])) or r.get("erro"))
        itens.append(item)
    for m in _RE_SV.finditer(texto):
        r = ler_precedente("STF", "Súmula vinculante", m.group(1))
        itens.append({"citacao": m.group(0), "tipo": "Súmula vinculante",
                      "status": "OK" if r.get("encontrado") else "NAO_ENCONTRADO",
                      "texto_oficial": (r.get("texto") or "")[:1200] or None, "detalhe": r.get("erro")})
    for m in _RE_TEMA.finditer(texto):
        num, orig = m.group(1), sem_acento((m.group(2) or "")).upper()
        cit = m.group(0).strip()
        if "STJ" in orig or "repetitivo" in cit.lower():
            cands = [("STJ", "Tema repetitivo")]
        elif "STF" in orig or "REPERCUSS" in orig or "repercuss" in sem_acento(cit).lower():
            cands = [("STF", "Tema de repercussão geral")]
        else:
            cands = []
        item = {"citacao": cit, "tipo": "Tema"}
        if not cands:
            item.update(status="AMBIGUO", detalhe="Indique se é Tema repetitivo do STJ ou de repercussão geral do STF.")
        else:
            r = ler_precedente(cands[0][0], cands[0][1], num)
            item.update(status="OK" if r.get("encontrado") else "NAO_ENCONTRADO",
                        texto_oficial=(r.get("texto") or "")[:1500] or None, fonte=r.get("fonte"),
                        detalhe=r.get("erro"))
        itens.append(item)
    for m in _RE_OJ.finditer(texto):
        secao = re.sub(r"[^A-Z0-9]", "", (m.group(2) or "").upper()).replace("SBDI", "SDI")
        r = ler_precedente("TST", "oj", f"{secao}-{m.group(1)}" if secao else m.group(1))
        itens.append({"citacao": m.group(0).strip(), "tipo": "OJ do TST",
                      "status": "OK" if r.get("encontrado") else "NAO_ENCONTRADO",
                      "texto_oficial": (r.get("texto") or "")[:1200] or None,
                      "detalhe": r.get("erro") or (None if m.group(2) else "Seção não indicada (SBDI-1/SBDI-2/SDC): confira se é a OJ certa.")})
    # Controle concentrado (está na base)
    for m in _RE_CONTROLE.finditer(texto):
        r = ler_precedente("STF", m.group(1).lower(), re.sub(r"\D", "", m.group(2)))
        itens.append({"citacao": m.group(0), "tipo": m.group(1), "status": "OK" if r.get("encontrado") else "NAO_ENCONTRADO",
                      "texto_oficial": (r.get("texto") or "")[:1200] or None, "fonte": r.get("fonte"),
                      "detalhe": r.get("erro")})
    # Acórdãos comuns: só OK se estiverem no cache de precedentes conferidos
    vistos_cnj = set()
    for m in _RE_ACORDAO.finditer(texto):
        classe, numero = m.group(1), m.group(2)
        if re.fullmatch(r"\d{4}", numero) and not re.search(r"\d{7}", numero):
            continue  # "RE 2002"? ano, não processo
        p = _precedente_cache(classe, numero)
        if len(re.sub(r"\D", "", numero)) == 20:
            vistos_cnj.add(re.sub(r"\D", "", numero))
        item = {"citacao": m.group(0).strip(), "tipo": "acórdão"}
        if p:
            item.update(status="OK", fonte=p["url"], texto_oficial=(p["ementa"] or "")[:1200],
                        detalhe=f"Conferido em {p['verificado_em'][:10]} ({p['tribunal']}).")
        else:
            item.update(status="NAO_VERIFICADO",
                        detalhe="Acórdão fora da base. Confira na página oficial do tribunal e registre com "
                                "registrar_precedente — ou remova. Nunca mantenha acórdão não conferido.")
        itens.append(item)
    for m in _RE_CNJ_SOLTO.finditer(texto):
        dig = re.sub(r"\D", "", m.group(1))
        if dig in vistos_cnj:
            continue
        p = _precedente_cache("", m.group(1))
        itens.append({"citacao": m.group(1), "tipo": "processo (nº CNJ)", "status": "OK" if p else "NAO_VERIFICADO",
                      "fonte": p["url"] if p else None,
                      "detalhe": None if p else "Número de processo não conferido: verifique na consulta processual do tribunal."})
    resumo: dict[str, int] = {}
    for i in itens:
        resumo[i["status"]] = resumo.get(i["status"], 0) + 1
    return {"total": len(itens), "resumo": resumo, "itens": itens,
            "regra": "Remova ou corrija toda citação que não esteja OK. NAO_VERIFICAVEL = conferir no Planalto antes de manter. NAO_VERIFICADO = acórdão/processo ainda não conferido na fonte. Acórdãos e doutrina não são verificáveis aqui."}


def listar_codigos() -> dict:
    inv: dict[str, list[str]] = {}
    for k, v in codigos().items():
        inv.setdefault(v, []).append(k)
    db = conexao()
    out = []
    for cam, apelidos in inv.items():
        r = db.execute("SELECT titulo, ementa FROM normas WHERE caminho=?", (cam,)).fetchone()
        if r:
            out.append({"apelidos": apelidos, "titulo": r["titulo"], "ementa": (r["ementa"] or "")[:120]})
    return {"codigos": out}


def buscar_norma(consulta: str, limite: int = 10) -> dict:
    """Encontra leis pelo nome/ementa (ex.: 'lei do inquilinato', 'locação de imóveis urbanos')."""
    termos = _termos(consulta)
    if not termos:
        return {"resultados": []}
    db = conexao()
    linhas = db.execute(
        "SELECT n.* FROM normas_fts f JOIN normas n ON n.id=f.rowid WHERE normas_fts MATCH ? AND n.esfera NOT IN ('jurisprudencia','biblioteca') "
        "ORDER BY n.revogada, bm25(normas_fts) LIMIT ?", (_fts(termos, "AND"), limite)).fetchall()
    return {"resultados": [{"titulo": r["titulo"], "ementa": (r["ementa"] or "")[:250], "revogada": bool(r["revogada"]),
                            "lei": r["caminho"]} for r in linhas]}


# ============================================================================= acórdãos verificados
# A base não traz acórdãos comuns (TJs, STJ fora de repetitivo). Toda decisão que o agente encontrar
# na web e CONFERIR na página oficial do tribunal é registrada aqui; o verificador de citações passa
# a reconhecê-la. O cache cresce com o uso e vira a "jurisprudência do escritório".

_CLASSES = (r"(?-i:AgInt\s+no\s+AREsp|AgInt\s+no\s+REsp|AgRg\s+no\s+AREsp|AgRg\s+no\s+REsp|EDcl\s+no\s+REsp|EREsp|AREsp|REsp|"
            r"ARE|RE|RHC|HC|RMS|MS|Rcl|AIRR|RR|AI)|"
            r"Apela[cç][aã]o\s+C[ií]vel|Apela[cç][aã]o\s+Criminal|Apela[cç][aã]o|Agravo\s+de\s+Instrumento|Agravo\s+Interno|"
            r"Recurso\s+Inominado|Recurso\s+Especial|Recurso\s+Extraordin[aá]rio|Mandado\s+de\s+Seguran[cç]a|"
            r"Conflito\s+de\s+Compet[eê]ncia")
_NUM_CNJ = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
_RE_ACORDAO = re.compile(
    r"\b(" + _CLASSES + r")\s*(?:n[ºo°.]*\s*)?(" + _NUM_CNJ + r"|\d{1,3}(?:\.\d{3})+|\d{3,})(?:\s*/\s*([A-Z]{2})\b)?", re.I)
_RE_CONTROLE = re.compile(r"\b(ADI|ADC|ADPF|ADO)\s*(?:n[ºo°.]*\s*)?(\d{1,3}(?:\.\d{3})*|\d+)\b")
_RE_CNJ_SOLTO = re.compile(r"(?<![\d.-])(" + _NUM_CNJ + r")(?![\d])")

_SCHEMA_PREC = """
CREATE TABLE IF NOT EXISTS precedentes(
    id INTEGER PRIMARY KEY, chave TEXT UNIQUE, tribunal TEXT, classe TEXT, numero TEXT, uf TEXT,
    orgao TEXT, relator TEXT, data_julgamento TEXT, ementa TEXT, tese TEXT, url TEXT,
    verificado_em TEXT, caso TEXT, observacao TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS precedentes_fts USING fts5(
    ementa, tese, classe, tribunal, content='precedentes', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS prec_ai AFTER INSERT ON precedentes BEGIN
  INSERT INTO precedentes_fts(rowid, ementa, tese, classe, tribunal) VALUES (new.id, new.ementa, new.tese, new.classe, new.tribunal);
END;
CREATE TRIGGER IF NOT EXISTS prec_ad AFTER DELETE ON precedentes BEGIN
  INSERT INTO precedentes_fts(precedentes_fts, rowid, ementa, tese, classe, tribunal)
  VALUES ('delete', old.id, old.ementa, old.tese, old.classe, old.tribunal);
END;
"""


def _db_prec() -> sqlite3.Connection:
    caminho = config.obter("precedentes_db")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(caminho)
    db.row_factory = sqlite3.Row
    db.executescript(_SCHEMA_PREC)
    return db


def _classe_norm(classe: str) -> str:
    c = re.sub(r"\s+", " ", sem_acento(classe)).strip().upper()
    return {"APELACAO CIVEL": "APELACAO", "APELACAO CRIMINAL": "APELACAO"}.get(c, c)


def _chave_acordao(classe: str, numero: str) -> str:
    digitos = re.sub(r"\D", "", numero)
    # número CNJ identifica o processo sozinho; nos demais a classe faz parte da identidade
    return digitos if len(digitos) == 20 else f"{_classe_norm(classe)}:{digitos}"


def registrar_precedente(tribunal: str, classe: str, numero: str, url: str, ementa: str,
                         relator: str = "", orgao: str = "", data_julgamento: str = "", tese: str = "",
                         uf: str = "", caso: str = "", observacao: str = "") -> dict:
    """Grava um acórdão que FOI CONFERIDO na página oficial (url) — número, ementa e dados batendo."""
    if not re.match(r"^https?://", url or ""):
        return {"ok": False, "erro": "Informe a URL da página oficial onde o acórdão foi conferido."}
    if len(re.sub(r"\D", "", numero or "")) < 3:
        return {"ok": False, "erro": "Número do processo inválido."}
    if len((ementa or "").strip()) < 40:
        return {"ok": False, "erro": "Transcreva a ementa (ou o trecho decisivo) conferida na fonte."}
    chave = _chave_acordao(classe, numero)
    db = _db_prec()
    with db:
        db.execute("DELETE FROM precedentes WHERE chave=?", (chave,))
        db.execute("""INSERT INTO precedentes(chave,tribunal,classe,numero,uf,orgao,relator,data_julgamento,ementa,tese,url,
                      verificado_em,caso,observacao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (chave, tribunal.upper().strip(), classe.strip(), numero.strip(), uf.upper().strip(), orgao, relator,
                    data_julgamento, ementa.strip(), tese.strip(), url.strip(), dt.datetime.now().isoformat(timespec="seconds"),
                    caso, observacao))
    return {"ok": True, "chave": chave, "banco": str(config.obter("precedentes_db"))}


def buscar_precedentes_verificados(consulta: str = "", tribunal: str | None = None, limite: int = 10) -> dict:
    db = _db_prec()
    if consulta.strip():
        termos = _termos(consulta)
        if not termos:
            return {"resultados": []}
        sql = ("SELECT p.* FROM precedentes_fts f JOIN precedentes p ON p.id=f.rowid WHERE precedentes_fts MATCH ?"
               + (" AND p.tribunal=?" if tribunal else "") + " ORDER BY bm25(precedentes_fts) LIMIT ?")
        params = [_fts(termos, "OR"), *([tribunal.upper()] if tribunal else []), limite]
    else:
        sql = "SELECT * FROM precedentes" + (" WHERE tribunal=?" if tribunal else "") + " ORDER BY verificado_em DESC LIMIT ?"
        params = [*([tribunal.upper()] if tribunal else []), limite]
    linhas = db.execute(sql, params).fetchall()
    return {"total": len(linhas), "resultados": [
        {k: r[k] for k in ("tribunal", "classe", "numero", "uf", "orgao", "relator", "data_julgamento", "url", "verificado_em")}
        | {"ementa": (r["ementa"] or "")[:1200], "tese": r["tese"] or None} for r in linhas]}


def _precedente_cache(classe: str, numero: str):
    db = _db_prec()
    return db.execute("SELECT * FROM precedentes WHERE chave=?", (_chave_acordao(classe, numero),)).fetchone()


# ============================================================================= biblioteca própria (doutrina, pareceres)

def buscar_biblioteca(consulta: str, limite: int = 10) -> dict:
    """Busca nos textos que o usuário colocou na biblioteca (livros, artigos, pareceres em .md/.txt)."""
    res = _buscar(consulta, " AND n.esfera = 'biblioteca'", [], limite)
    for r in res:
        r["obra"] = r.pop("norma")
        r.pop("ref", None)
    vazio = conexao().execute("SELECT count(*) FROM normas WHERE esfera='biblioteca'").fetchone()[0] == 0
    return {"consulta": consulta, "total": len(res), "resultados": res,
            "observacao": ("A biblioteca está vazia. Coloque .md/.txt em " + str(config.obter("biblioteca")) +
                           " e use a ferramenta reindexar (ou reinicie o Claude).") if vazio else
                          "Cite a obra pelo título/autor do arquivo. Trechos de doutrina não são verificados pela base."}


# ============================================================================= complementos (corrigir lacunas)

def reindexar() -> dict:
    """Reaplica complementos e biblioteca do usuário sobre a base baixada (segundos) e reabre a conexão."""
    try:
        return base.montar_trabalho()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": str(e)}


def salvar_complemento(lei: str, texto: str, fonte: str, reindexar_agora: bool = True) -> dict:
    """Grava o texto oficial completo de uma norma que está incompleta na base (ex.: obtido no planalto.gov.br).

    O arquivo vai para a pasta de complementos com o mesmo caminho do repositório e passa a valer no lugar
    do original na próxima indexação. Use só texto copiado da fonte oficial, com a URL em 'fonte'.
    """
    if not re.match(r"^(https?|file)://", fonte or ""):
        return {"ok": False, "erro": "Informe a URL oficial de onde o texto foi copiado."}
    if not re.search(r"(?mi)^\s*(?:\*\*)?\s*Art", texto or ""):
        return {"ok": False, "erro": "O texto não contém artigos ('Art. 1º ...'). Cole o texto integral da norma."}
    norma = resolver_lei(lei)
    if not norma:
        return {"ok": False, "erro": f"Lei não reconhecida: {lei!r}. Use o caminho do arquivo (federal/...md)."}
    destino = config.obter("complementos") / norma["caminho"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    cab = {"titulo": norma["titulo"], "tipo": norma["tipo"], "numero": norma["numero"], "data": norma["data"] or "",
           "ementa": norma["ementa"] or "", "revogada": "false",
           "versao_texto": f"complemento manual ({dt.date.today().isoformat()})", "fonte": fonte}
    linhas = ["---"] + [f'{k}: {json.dumps(v, ensure_ascii=False)}' if k not in ("data",) else f"{k}: {v}" for k, v in cab.items()]
    linhas += ["---", f"# {norma['titulo']}", "", texto.strip(), ""]
    destino.write_text("\n".join(linhas), encoding="utf-8")
    out = {"ok": True, "arquivo": str(destino),
           "dica": "Este complemento vale só nesta pasta Jurídico. Para todos os usuários, envie o arquivo para "
                   f"dados/complementos/{norma['caminho']} no repositório {config.repo_base()} (pull request)."}
    if reindexar_agora:
        out["reindexacao"] = reindexar()
    return out


def lacunas(limite: int = 50) -> dict:
    """Normas federais sem nenhum artigo reconhecido na base (candidatas a complemento)."""
    db = conexao()
    linhas = db.execute("""SELECT n.titulo, n.ementa, n.caminho, n.fonte FROM normas n
        WHERE n.esfera='federal' AND NOT EXISTS (SELECT 1 FROM dispositivos d WHERE d.norma_id=n.id AND d.artigo IS NOT NULL)
        ORDER BY n.data DESC LIMIT ?""", (limite,)).fetchall()
    total = db.execute("""SELECT count(*) FROM normas n WHERE n.esfera='federal' AND NOT EXISTS
        (SELECT 1 FROM dispositivos d WHERE d.norma_id=n.id AND d.artigo IS NOT NULL)""").fetchone()[0]
    return {"total": total, "mostrando": len(linhas),
            "normas": [{"titulo": r["titulo"], "ementa": (r["ementa"] or "")[:150], "lei": r["caminho"], "fonte": r["fonte"]}
                       for r in linhas]}


_DOMINIOS_OFICIAIS = re.compile(r"^https://([a-z0-9-]+\.)*(planalto\.gov\.br|leg\.br|gov\.br|jus\.br)(/|$)", re.I)


def baixar_oficial(lei: str, url: str) -> dict:
    """Baixa o texto oficial de uma norma (Planalto, normas.leg.br, Câmara/Senado, *.gov.br, *.jus.br),
    converte para Markdown com o mesmo conversor do ctresb/leis (tira o texto tachado/revogado) e grava
    como complemento, reindexando a base. Também aceita file:///caminho/pagina.htm (página salva à mão).
    """
    if not (_DOMINIOS_OFICIAIS.match(url or "") or (url or "").startswith("file://")):
        return {"ok": False, "erro": "Use uma URL https de fonte oficial (planalto.gov.br, *.leg.br, *.gov.br, *.jus.br)."}
    from html2md import convert, decodificar  # conversor do ctresb/leis (MIT), incluído no plugin
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (advogado-br; consulta pontual)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            dados, ctype = resp.read(), resp.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": f"Falha ao baixar {url}: {e}"}
    texto = convert(decodificar(dados, ctype), exclude_struck=True)
    n_art = len(re.findall(r"(?m)^\s*\*\*Art", texto))
    if n_art == 0:
        return {"ok": False, "erro": "A página não tem artigos reconhecíveis (é a página certa? tem o texto compilado?)."}
    r = salvar_complemento(lei, texto, url if not url.startswith("file://") else f"{url} (cópia local)")
    r["artigos_convertidos"] = n_art
    return r
