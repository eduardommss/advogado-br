"""Base de leis: baixa da Release do GitHub, mantém atualizada e aplica os dados do usuário por cima.

Layout no cache (descartável — config.cache_dir()):
    base/leis-base.db        índice publicado pela GitHub Action (intocado)
    base/manifest.json       versão baixada (tag, data, sha256, origem)
    trabalho/leis-<n>.db     cópia de trabalho = base + complementos + biblioteca do usuário
    atual.json               qual cópia de trabalho está em uso e com que "impressão digital" de dados do usuário
    estado.json              última verificação, progresso, erro

Nada aqui é dado do usuário: complementos, biblioteca e acórdãos conferidos ficam em <Juridico>/_escritorio.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

ASSET = "leis.db.gz"
_lock = threading.RLock()
_ouvintes = []           # funções chamadas quando a cópia de trabalho muda (nucleo.recarregar)
_estado = {"fase": "parado", "progresso": None, "erro": None, "mensagem": None}


# ----------------------------------------------------------------------------- caminhos e estado

def _dir() -> Path:
    d = config.cache_dir()
    (d / "base").mkdir(parents=True, exist_ok=True)
    (d / "trabalho").mkdir(parents=True, exist_ok=True)
    return d


def _ler(nome: str) -> dict:
    try:
        return json.loads((config.cache_dir() / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar(nome: str, dados: dict) -> None:
    p = _dir() / nome
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _set(**kw) -> None:
    _estado.update(kw)


def ao_trocar(fn) -> None:
    _ouvintes.append(fn)


def caminho_trabalho() -> Path | None:
    fixo = config.leis_db_fixo()
    if fixo:
        return fixo
    nome = _ler("atual.json").get("arquivo")
    p = config.cache_dir() / "trabalho" / nome if nome else None
    return p if p and p.exists() else None


def status() -> dict:
    manifesto = _ler("base/manifest.json")
    atual = _ler("atual.json")
    return {
        "pronta": caminho_trabalho() is not None,
        "fase": _estado["fase"], "progresso": _estado["progresso"], "erro": _estado["erro"],
        "mensagem": _estado["mensagem"],
        "versao_base": manifesto.get("tag"), "gerada_em": manifesto.get("gerado_em"),
        "origem": manifesto.get("origem"), "normas": manifesto.get("normas"),
        "complementos_locais": atual.get("complementos"), "obras_biblioteca": atual.get("biblioteca"),
        "ultima_verificacao": _ler("estado.json").get("ultima_verificacao"),
        "cache": str(config.cache_dir()), "fonte": f"https://github.com/{config.repo_base()}/releases",
    }


def mensagem_indisponivel() -> str:
    if _estado["fase"] == "baixando":
        pct = _estado["progresso"]
        return (f"A base de leis está sendo baixada pela primeira vez ({pct:.0%} concluído). Leva cerca de 1 minuto: "
                "avise o usuário e tente de novo em instantes.") if pct is not None else \
               "A base de leis está sendo baixada pela primeira vez. Tente de novo em instantes."
    if _estado["fase"] in ("montando", "verificando"):
        return "A base de leis está sendo preparada. Tente de novo em alguns segundos."
    if _estado["erro"]:
        return (f"Não foi possível obter a base de leis: {_estado['erro']}. Verifique a internet e use a ferramenta "
                "atualizar_base (ou 'consultar.py atualizar').")
    return "A base de leis ainda não foi baixada. Use a ferramenta atualizar_base (ou 'consultar.py atualizar')."


# ----------------------------------------------------------------------------- download

def _url(nome: str) -> str:
    espelho = os.environ.get("ADVOGADO_BR_URL_BASE")  # testes / espelho próprio
    if espelho:
        return f"{espelho.rstrip('/')}/{nome}"
    return f"https://github.com/{config.repo_base()}/releases/latest/download/{nome}"


def _abrir(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "advogado-br"})
    return urllib.request.urlopen(req, timeout=timeout)


def manifesto_remoto() -> dict:
    with _abrir(_url("manifest.json"), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _baixar(remoto: dict) -> None:
    d = _dir() / "base"
    gz_tmp, db_tmp = d / "leis.db.gz.parte", d / "leis-base.db.parte"
    _set(fase="baixando", progresso=0.0, erro=None, mensagem=f"baixando base {remoto.get('tag')}")
    h = hashlib.sha256()
    with _abrir(_url(ASSET), timeout=120) as r, open(gz_tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or remoto.get("tamanho_gz") or 0)
        lido = 0
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
            h.update(bloco)
            lido += len(bloco)
            if total:
                _set(progresso=min(lido / total, 0.99))
    esperado = remoto.get("sha256_gz")
    if esperado and h.hexdigest() != esperado:
        gz_tmp.unlink(missing_ok=True)
        raise RuntimeError("download corrompido (sha256 não confere) — tente de novo")
    _set(fase="montando", mensagem="descompactando")
    with gzip.open(gz_tmp, "rb") as src, open(db_tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    gz_tmp.unlink(missing_ok=True)
    con = sqlite3.connect(db_tmp)
    try:
        n = con.execute("SELECT count(*) FROM normas").fetchone()[0]
    finally:
        con.close()
    if n < 1000:
        raise RuntimeError(f"base baixada parece incompleta ({n} normas)")
    os.replace(db_tmp, d / "leis-base.db")
    _gravar("base/manifest.json", remoto)


# ----------------------------------------------------------------------------- dados do usuário por cima

def _impressao_usuario() -> str:
    h = hashlib.sha256()
    for pasta in (config.obter("complementos"), config.obter("biblioteca")):
        if pasta.is_dir():
            for p in sorted(pasta.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    h.update(f"{p.relative_to(pasta)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()


def montar_trabalho() -> dict:
    """Cópia de trabalho = base baixada + complementos + biblioteca do usuário. Troca atômica, sem derrubar leituras."""
    import indexador  # noqa: PLC0415
    with _lock:
        base_db = config.cache_dir() / "base" / "leis-base.db"
        if not base_db.exists():
            raise RuntimeError("base ainda não baixada")
        _set(fase="montando", mensagem="aplicando seus complementos e biblioteca")
        d = _dir() / "trabalho"
        novo = d / f"leis-{int(time.time() * 1000)}.db"
        shutil.copyfile(base_db, novo)
        con = sqlite3.connect(novo)
        try:
            n_comp = indexador.aplicar_complementos(con, str(config.obter("complementos")))
            indexador.remover_biblioteca(con)
            n_bib = indexador.indexar_biblioteca(con, str(config.obter("biblioteca")))
            con.execute("INSERT OR REPLACE INTO meta VALUES('montado_em', ?)", (time.strftime("%Y-%m-%d %H:%M"),))
            con.commit()
        finally:
            con.close()
        anterior = _ler("atual.json").get("arquivo")
        _gravar("atual.json", {"arquivo": novo.name, "impressao": _impressao_usuario(),
                               "complementos": n_comp, "biblioteca": n_bib,
                               "base": _ler("base/manifest.json").get("tag")})
        for fn in _ouvintes:
            fn()
        for velho in d.glob("leis-*.db"):  # no Windows um arquivo aberto não sai; tenta de novo na próxima vez
            if velho.name not in (novo.name, anterior):
                try:
                    velho.unlink()
                except OSError:
                    pass
        _set(fase="pronto", progresso=None, mensagem=None)
        return {"ok": True, "complementos": n_comp, "biblioteca": n_bib, "arquivo": str(novo)}


# ----------------------------------------------------------------------------- orquestração

def atualizar(forcar: bool = False) -> dict:
    """Confere a Release e baixa se houver base nova (ou se ainda não houver nenhuma); depois remonta a cópia de
    trabalho se a base ou os dados do usuário mudaram. Síncrono."""
    if config.leis_db_fixo():
        return {"ok": True, "mensagem": "LEIS_DB definido: usando índice fixo, nada a baixar."}
    with _lock:
        try:
            local = _ler("base/manifest.json")
            tem_base = (config.cache_dir() / "base" / "leis-base.db").exists()
            _set(fase="verificando", erro=None)
            remoto = manifesto_remoto()
            baixou = False
            if forcar or not tem_base or remoto.get("sha256_gz") != local.get("sha256_gz"):
                _baixar(remoto)
                baixou = True
            _gravar("estado.json", {"ultima_verificacao": time.strftime("%Y-%m-%d %H:%M")})
            precisa = baixou or caminho_trabalho() is None or \
                _ler("atual.json").get("impressao") != _impressao_usuario()
            r = montar_trabalho() if precisa else {"ok": True}
            _set(fase="pronto", progresso=None, mensagem=None)
            return {**r, "baixou": baixou, "versao_base": remoto.get("tag")}
        except Exception as e:  # noqa: BLE001
            # sem internet mas com base local: segue usando a que tem
            _set(fase="pronto" if caminho_trabalho() else "erro", progresso=None, erro=str(e))
            return {"ok": caminho_trabalho() is not None, "erro": str(e)}


def _verificacao_vencida() -> bool:
    ultima = _ler("estado.json").get("ultima_verificacao")
    if not ultima:
        return True
    try:
        t = time.mktime(time.strptime(ultima, "%Y-%m-%d %H:%M"))
    except ValueError:
        return True
    return time.time() - t > config.verificar_dias() * 86400


def iniciar_em_segundo_plano() -> None:
    """Chamado quando o servidor sobe: baixa na primeira vez, confere atualização a cada N dias e remonta a cópia de
    trabalho se o usuário mexeu em complementos/biblioteca — sem travar as ferramentas."""
    if config.leis_db_fixo():
        return

    def tarefa():
        try:
            if caminho_trabalho() is None or _verificacao_vencida():
                atualizar()
            elif _ler("atual.json").get("impressao") != _impressao_usuario():
                montar_trabalho()
        except Exception as e:  # noqa: BLE001
            _set(fase="erro" if caminho_trabalho() is None else "pronto", erro=str(e))

    threading.Thread(target=tarefa, name="advogado-br-base", daemon=True).start()
