#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Organiza assuntos jurídicos em pastas: documentos, provas, peças, pesquisa, comunicações, decisões e links.

Raiz: JURIDICO_DIR > "juridico_dir" no config.json do advogado-br > Documentos/Juridico. Sem dependências externas.

  caso.py novo "Locação apto Centro" --tipo contrato --area imobiliario --papel locatario --parte "João Silva:locador"
  caso.py arquivar 2026-001 ~/Downloads/contrato.pdf --categoria documentos --descricao "contrato assinado" --data 2026-01-10
  caso.py link 2026-001 https://... --descricao "anúncio do imóvel"
  caso.py evento 2026-001 --data 2026-09-01 --descricao "locador pediu o imóvel por WhatsApp"
  caso.py prazo 2026-001 --data 2026-11-05 --descricao "responder notificação"
  caso.py fase 2026-001 negociacao
  caso.py passo 2026-001 --acao "enviar contranotificação" --motivo "..." --skill redigir-documento
  caso.py status 2026-001        caso.py listar        caso.py prazos [--dias 30]
  caso.py entrada                # lista arquivos soltos em _ENTRADA para classificar
  caso.py indice                 # regenera _INDICE.md e os RESUMO.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

CATEGORIAS = {
    "documentos": "01-documentos",     # contratos, aditivos, procurações, documentos pessoais/societários
    "provas": "02-provas",             # fotos, prints, áudios, vídeos, laudos, comprovantes, extratos
    "pecas": "03-pecas",               # petições, notificações, minutas, contratos redigidos
    "pesquisa": "04-pesquisa",         # análises, estratégias, pareceres, legislação/precedentes salvos
    "comunicacoes": "05-comunicacoes", # e-mails, conversas, notificações recebidas
    "decisoes": "06-decisoes",         # decisões, sentenças, atas de audiência, acordos homologados
}
TIPOS = ["contrato", "processo", "consulta", "negociacao", "cobranca", "outro"]
FASES = ["intake", "analise", "negociacao", "notificacao", "pre-processual", "judicial", "recurso", "execucao",
         "acompanhamento", "encerrado"]


def _config():
    """Mesmo config.py do servidor (pasta mcp/ do plugin), para os dois concordarem sobre onde ficam os casos."""
    import importlib.util
    cam = Path(__file__).resolve().parents[3] / "mcp" / "config.py"
    spec = importlib.util.spec_from_file_location("config_advogado_br", cam)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raiz() -> Path:
    r = _config().juridico_dir()
    r.mkdir(parents=True, exist_ok=True)
    (r / "_ENTRADA").mkdir(exist_ok=True)
    return r


def hoje() -> str:
    return dt.date.today().isoformat()


def agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def slug(s: str, n: int = 50) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-") or "sem-nome"


def data_valida(s: str | None) -> str:
    if not s:
        return hoje()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    sys.exit(f"Data inválida: {s} (use AAAA-MM-DD ou DD/MM/AAAA)")


def casos() -> list[Path]:
    return sorted(p.parent for p in raiz().glob("*/caso.json"))


def achar(ref: str) -> Path:
    cands = [p for p in casos() if p.name == ref or p.name.startswith(ref + "-") or p.name.startswith(ref)]
    if not cands:
        cands = [p for p in casos() if slug(ref) in p.name]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        sys.exit(f"Caso não encontrado: {ref}. Use 'caso.py listar'.")
    sys.exit("Referência ambígua: " + ", ".join(p.name for p in cands))


def carregar(pasta: Path) -> dict:
    return json.loads((pasta / "caso.json").read_text(encoding="utf-8"))


def salvar(pasta: Path, c: dict) -> None:
    c["atualizado_em"] = agora()
    tmp = pasta / "caso.json.tmp"
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(pasta / "caso.json")
    escrever_resumo(pasta, c)
    escrever_indice()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# --------------------------------------------------------------------------- relatórios

def escrever_resumo(pasta: Path, c: dict) -> None:
    L = [f"# {c['titulo']}", "",
         f"**Caso:** {c['id']} · **Tipo:** {c['tipo']} · **Área:** {c.get('area') or '—'} · "
         f"**Fase:** {c['fase']} · **Status:** {c['status']}"]
    if c.get("papel_cliente"):
        L.append(f"**Cliente é:** {c['papel_cliente']}")
    if c.get("partes"):
        L.append("**Partes:** " + "; ".join(f"{p['nome']} ({p.get('papel') or '—'})" for p in c["partes"]))
    if c.get("numero_processo"):
        L.append(f"**Processo:** {c['numero_processo']} {c.get('tribunal') or ''}")
    pp = c.get("proximo_passo")
    if pp:
        L += ["", "## ▶ Próximo passo", f"**{pp['acao']}**" + (f" — {pp['motivo']}" if pp.get("motivo") else ""),
              f"_(definido em {pp['definido_em'][:10]}{', skill: ' + pp['skill'] if pp.get('skill') else ''})_"]
    abertos = sorted([p for p in c.get("prazos", []) if not p.get("cumprido")], key=lambda p: p["data"])
    if abertos:
        L += ["", "## ⏰ Prazos abertos"]
        for p in abertos:
            dias = (dt.date.fromisoformat(p["data"]) - dt.date.today()).days
            alerta = "🔴" if dias <= 3 else "🟠" if dias <= 10 else "🟢"
            L.append(f"- {alerta} {p['data']} ({dias:+d} dias) — {p['descricao']}")
    eventos = sorted(c.get("eventos", []) + [{"data": d["data"], "descricao": f"📎 {d['descricao']} ({d['arquivo']})"}
                                            for d in c.get("documentos", [])], key=lambda e: e["data"])
    if eventos:
        L += ["", "## Linha do tempo"] + [f"- **{e['data']}** — {e['descricao']}" for e in eventos]
    for cat, pasta_cat in CATEGORIAS.items():
        docs = [d for d in c.get("documentos", []) if d["categoria"] == cat]
        if docs:
            L += ["", f"## {pasta_cat}"]
            L += [f"- [{d['descricao']}]({d['arquivo']}) · {d['data']} · sha256 `{d['sha256'][:12]}…`" for d in docs]
    if c.get("links"):
        L += ["", "## Links"] + [f"- [{l['descricao'] or l['url']}]({l['url']}) · {l['adicionado_em'][:10]}" for l in c["links"]]
    if c.get("notas"):
        L += ["", "## Notas", c["notas"]]
    L += ["", f"_Atualizado em {c['atualizado_em']} — gerado por caso.py; edite o caso.json ou use os comandos._"]
    (pasta / "RESUMO.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def escrever_indice() -> None:
    linhas = ["# Índice de casos", "", "| Caso | Título | Tipo | Fase | Próximo prazo | Próximo passo |", "|---|---|---|---|---|---|"]
    todos_prazos = []
    for p in casos():
        c = carregar(p)
        abertos = sorted([x for x in c.get("prazos", []) if not x.get("cumprido")], key=lambda x: x["data"])
        prox = f"{abertos[0]['data']} {abertos[0]['descricao']}" if abertos else "—"
        passo = (c.get("proximo_passo") or {}).get("acao", "—")
        linhas.append(f"| [{c['id']}]({p.name}/RESUMO.md) | {c['titulo']} | {c['tipo']} | {c['fase']} | {prox} | {passo} |")
        todos_prazos += [(x["data"], c["id"], x["descricao"]) for x in abertos]
    if todos_prazos:
        linhas += ["", "## Prazos (todos os casos)"] + [f"- {d} · {i} · {t}" for d, i, t in sorted(todos_prazos)]
    linhas += ["", "Arquivos soltos para classificar: pasta `_ENTRADA/`."]
    (raiz() / "_INDICE.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- comandos

def cmd_novo(a):
    ano = dt.date.today().year
    seq = 1 + max([int(m.group(1)) for p in casos() if (m := re.match(rf"{ano}-(\d+)", p.name))] or [0])
    cid = f"{ano}-{seq:03d}"
    pasta = raiz() / f"{cid}-{slug(a.titulo)}"
    pasta.mkdir()
    for sub in CATEGORIAS.values():
        (pasta / sub).mkdir()
    partes = []
    for p in a.parte or []:
        nome, _, papel = p.partition(":")
        partes.append({"nome": nome.strip(), "papel": papel.strip() or None})
    c = {"id": cid, "titulo": a.titulo, "tipo": a.tipo, "area": a.area, "papel_cliente": a.papel, "partes": partes,
         "status": "aberto", "fase": "intake", "numero_processo": a.processo, "tribunal": a.tribunal,
         "criado_em": agora(), "atualizado_em": agora(), "prazos": [], "eventos": [], "documentos": [], "links": [],
         "proximo_passo": None, "notas": a.notas or ""}
    salvar(pasta, c)
    print(json.dumps({"ok": True, "id": cid, "pasta": str(pasta)}, ensure_ascii=False))


def cmd_arquivar(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    orig = Path(a.arquivo).expanduser()
    if not orig.is_file():
        sys.exit(f"Arquivo não encontrado: {orig}")
    if a.categoria not in CATEGORIAS:
        sys.exit(f"Categoria inválida. Use: {', '.join(CATEGORIAS)}")
    data = data_valida(a.data)
    hash_ = sha256(orig)
    if any(d["sha256"] == hash_ for d in c["documentos"]):
        print(json.dumps({"ok": False, "motivo": "arquivo idêntico já está no caso"}, ensure_ascii=False))
        return
    destino_dir = pasta / CATEGORIAS[a.categoria]
    base = f"{data}_{slug(a.descricao, 60)}"
    destino = destino_dir / f"{base}{orig.suffix.lower()}"
    n = 2
    while destino.exists():
        destino = destino_dir / f"{base}-{n}{orig.suffix.lower()}"
        n += 1
    mover = a.mover or (raiz() / "_ENTRADA") in orig.resolve().parents
    (shutil.move if mover else shutil.copy2)(str(orig), str(destino))
    doc = {"arquivo": str(destino.relative_to(pasta)), "categoria": a.categoria, "descricao": a.descricao,
           "data": data, "sha256": hash_, "origem": str(orig.resolve()), "adicionado_em": agora(),
           "operacao": "movido" if mover else "copiado"}
    if a.nota:
        doc["nota"] = a.nota
    c["documentos"].append(doc)
    salvar(pasta, c)
    print(json.dumps({"ok": True, **doc}, ensure_ascii=False))


def cmd_link(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    if any(l["url"] == a.url for l in c["links"]):
        print(json.dumps({"ok": False, "motivo": "link já registrado"}, ensure_ascii=False))
        return
    c["links"].append({"url": a.url, "descricao": a.descricao, "adicionado_em": agora()})
    salvar(pasta, c)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_evento(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    c["eventos"].append({"data": data_valida(a.data), "descricao": a.descricao})
    salvar(pasta, c)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_prazo(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    if a.cumprido:
        alvo = [p for p in c["prazos"] if a.descricao.lower() in p["descricao"].lower() and not p.get("cumprido")]
        if not alvo:
            sys.exit("Prazo não encontrado")
        alvo[0]["cumprido"] = True
        alvo[0]["cumprido_em"] = agora()
    else:
        c["prazos"].append({"data": data_valida(a.data), "descricao": a.descricao, "cumprido": False})
    salvar(pasta, c)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_fase(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    if a.fase not in FASES:
        sys.exit(f"Fase inválida. Use: {', '.join(FASES)}")
    c["eventos"].append({"data": hoje(), "descricao": f"Fase: {c['fase']} → {a.fase}"})
    c["fase"] = a.fase
    c["status"] = "encerrado" if a.fase == "encerrado" else c["status"]
    salvar(pasta, c)
    print(json.dumps({"ok": True, "fase": a.fase}, ensure_ascii=False))


def cmd_passo(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    c["proximo_passo"] = {"acao": a.acao, "motivo": a.motivo, "skill": a.skill, "definido_em": agora()}
    salvar(pasta, c)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_atualizar(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    for campo in ("titulo", "area", "papel_cliente", "numero_processo", "tribunal", "notas", "status"):
        v = getattr(a, campo, None)
        if v is not None:
            c[campo] = v
    for p in a.parte or []:
        nome, _, papel = p.partition(":")
        c["partes"].append({"nome": nome.strip(), "papel": papel.strip() or None})
    salvar(pasta, c)
    print(json.dumps({"ok": True}, ensure_ascii=False))


def cmd_status(a):
    pasta = achar(a.caso)
    c = carregar(pasta)
    contagem = {cat: sum(1 for d in c["documentos"] if d["categoria"] == cat) for cat in CATEGORIAS}
    print(json.dumps({"pasta": str(pasta), **c, "contagem_por_categoria": contagem}, ensure_ascii=False, indent=2))


def cmd_listar(a):
    out = []
    for p in casos():
        c = carregar(p)
        if a.todos or c["status"] != "encerrado":
            out.append({"id": c["id"], "titulo": c["titulo"], "tipo": c["tipo"], "fase": c["fase"],
                        "status": c["status"], "pasta": str(p),
                        "proximo_passo": (c.get("proximo_passo") or {}).get("acao")})
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_prazos(a):
    limite = dt.date.today() + dt.timedelta(days=a.dias)
    out = []
    for p in casos():
        c = carregar(p)
        for x in c["prazos"]:
            if not x.get("cumprido") and dt.date.fromisoformat(x["data"]) <= limite:
                out.append({"data": x["data"], "dias": (dt.date.fromisoformat(x["data"]) - dt.date.today()).days,
                            "caso": c["id"], "titulo": c["titulo"], "prazo": x["descricao"]})
    print(json.dumps(sorted(out, key=lambda x: x["data"]), ensure_ascii=False, indent=2))


def cmd_entrada(a):
    e = raiz() / "_ENTRADA"
    arquivos = [str(p) for p in sorted(e.rglob("*")) if p.is_file() and not p.name.startswith(".")]
    print(json.dumps({"pasta": str(e), "arquivos": arquivos}, ensure_ascii=False, indent=2))


def cmd_indice(a):
    for p in casos():
        escrever_resumo(p, carregar(p))
    escrever_indice()
    print(json.dumps({"ok": True, "indice": str(raiz() / "_INDICE.md"), "casos": len(casos())}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Organizador de casos jurídicos")
    s = ap.add_subparsers(dest="cmd", required=True)
    p = s.add_parser("novo"); p.add_argument("titulo"); p.add_argument("--tipo", choices=TIPOS, default="outro")
    p.add_argument("--area"); p.add_argument("--papel", help="papel do cliente: locatário, contratante, autor, réu…")
    p.add_argument("--parte", action="append", help='"Nome:papel" (repita)'); p.add_argument("--processo")
    p.add_argument("--tribunal"); p.add_argument("--notas")
    p = s.add_parser("arquivar"); p.add_argument("caso"); p.add_argument("arquivo")
    p.add_argument("--categoria", required=True, choices=list(CATEGORIAS)); p.add_argument("--descricao", required=True)
    p.add_argument("--data", help="data do documento/fato (não a de hoje)"); p.add_argument("--nota")
    p.add_argument("--mover", action="store_true", help="move em vez de copiar (padrão: copia; da _ENTRADA, move)")
    p = s.add_parser("link"); p.add_argument("caso"); p.add_argument("url"); p.add_argument("--descricao", default="")
    p = s.add_parser("evento"); p.add_argument("caso"); p.add_argument("--data"); p.add_argument("--descricao", required=True)
    p = s.add_parser("prazo"); p.add_argument("caso"); p.add_argument("--data"); p.add_argument("--descricao", required=True)
    p.add_argument("--cumprido", action="store_true", help="marca como cumprido o prazo cuja descrição contém o texto")
    p = s.add_parser("fase"); p.add_argument("caso"); p.add_argument("fase", choices=FASES)
    p = s.add_parser("passo"); p.add_argument("caso"); p.add_argument("--acao", required=True)
    p.add_argument("--motivo"); p.add_argument("--skill")
    p = s.add_parser("atualizar"); p.add_argument("caso")
    for campo in ("titulo", "area", "papel_cliente", "numero_processo", "tribunal", "notas", "status"):
        p.add_argument("--" + campo.replace("_", "-"), dest=campo)
    p.add_argument("--parte", action="append")
    p = s.add_parser("status"); p.add_argument("caso")
    p = s.add_parser("listar"); p.add_argument("--todos", action="store_true")
    p = s.add_parser("prazos"); p.add_argument("--dias", type=int, default=30)
    s.add_parser("entrada"); s.add_parser("indice")
    a = ap.parse_args()
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
