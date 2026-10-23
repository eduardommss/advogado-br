#!/usr/bin/env python3
"""Gera a base de leis que vai para a Release do GitHub (usado pela Action .github/workflows/base.yml).

    python3 scripts/gerar_base.py --leis /caminho/clone-ctresb-leis --saida dist/

Produz em dist/: leis.db.gz, manifest.json e leis.db.gz.sha256. Antes de aceitar a base, roda testes de fumaça:
artigos-chave existem, jurisprudência presente e toda citação dos playbooks/skills continua válida (se uma lei mudar
de número ou for revogada, o build falha e alguém revê o playbook).
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "mcp"))


def sh(*cmd, cwd=None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def testes(db_path: Path) -> list[str]:
    os.environ["LEIS_DB"] = str(db_path)
    os.environ.setdefault("PRECEDENTES_DB", str(db_path.parent / "precedentes-teste.db"))
    import nucleo  # noqa: PLC0415
    falhas = []
    for lei, art, trecho in [("CC", "412", "cláusula penal"), ("CPC", "300", "tutela de urgência"),
                             ("CDC", "51", "nulas de pleno direito"), ("CF", "5", "iguais perante a lei"),
                             ("CLT", "482", "justa causa"), ("Lei 8.245/1991", "4", "multa")]:
        r = nucleo.ler_artigo(lei, art)
        if not r.get("encontrado") or trecho.lower() not in r["texto"].lower():
            falhas.append(f"artigo-chave ausente/alterado: {lei} art. {art}")
    for trib, tipo, num in [("STJ", "sumula", "297"), ("STF", "sumula vinculante", "10"), ("STJ", "repetitivo", "1000")]:
        if not nucleo.ler_precedente(trib, tipo, num).get("encontrado"):
            falhas.append(f"precedente ausente: {trib} {tipo} {num}")
    ruins = {"NAO_ENCONTRADO", "DIVERGENTE", "REVOGADO"}
    for md in sorted((RAIZ / "skills").rglob("*.md")):
        r = nucleo.verificar_citacoes(md.read_text(encoding="utf-8"))
        for item in r["itens"]:
            if item["status"] in ruins:
                falhas.append(f"{md.relative_to(RAIZ)}: {item['citacao']} → {item['status']} ({item.get('detalhe')})")
    return falhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leis", required=True, help="clone (parcial) do ctresb/leis")
    ap.add_argument("--saida", default="dist")
    a = ap.parse_args()
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    db = saida / "leis.db"

    origem = sh("git", "rev-parse", "HEAD", cwd=a.leis)
    subprocess.run([sys.executable, str(RAIZ / "mcp" / "indexador.py"), "--repo", a.leis, "--saida", str(db),
                    "--complementos", str(RAIZ / "dados" / "complementos"),
                    "--origem", f"ctresb/leis@{origem}"], check=True)

    falhas = testes(db)
    if falhas:
        print("TESTES FALHARAM:\n  " + "\n  ".join(falhas), file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(db)
    normas = con.execute("SELECT count(*) FROM normas").fetchone()[0]
    disp = con.execute("SELECT count(*) FROM dispositivos").fetchone()[0]
    por_esfera = dict(con.execute("SELECT esfera, count(*) FROM normas GROUP BY esfera").fetchall())
    con.close()

    gz = saida / "leis.db.gz"
    with open(db, "rb") as src, gzip.open(gz, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    h = hashlib.sha256(gz.read_bytes()).hexdigest()
    (saida / "leis.db.gz.sha256").write_text(f"{h}  leis.db.gz\n", encoding="utf-8")
    tag = os.environ.get("TAG") or time.strftime("base-%Y%m%d")
    manifesto = {
        "tag": tag, "gerado_em": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "origem": f"https://github.com/ctresb/leis/commit/{origem}", "normas": normas, "dispositivos": disp,
        "por_esfera": por_esfera, "sha256_gz": h, "tamanho_gz": gz.stat().st_size, "tamanho_db": db.stat().st_size,
        "esquema": 2,
    }
    (saida / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    db.unlink()
    print(json.dumps(manifesto, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
