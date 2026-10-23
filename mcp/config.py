"""Onde o advogado-br guarda cada coisa — igual em Windows, Linux, macOS e WSL, sem instalador.

Dois lugares, com papéis opostos:

* **Cache (descartável)** — a base de leis indexada, baixada da Release do GitHub. Apagou? Baixa de novo.
    Windows: %LOCALAPPDATA%\\advogado-br   ·   macOS: ~/Library/Caches/advogado-br   ·   Linux: ~/.cache/advogado-br
* **Pasta Jurídico (seus dados — faça backup)** — casos e, em `_escritorio/`, acórdãos conferidos, complementos de
  leis e biblioteca. Padrão: `Documentos/Juridico` (no Windows, a pasta Documentos real, inclusive se estiver no
  OneDrive).

Precedência: variável de ambiente > config.json > padrão. O config.json é opcional
(Windows: %APPDATA%\\advogado-br\\config.json; demais: ~/.config/advogado-br/config.json).

Chaves do config.json: juridico_dir, repo_base ("dono/repo" de onde baixar a base), verificar_dias.
Variáveis: JURIDICO_DIR, ADVOGADO_BR_CACHE, ADVOGADO_BR_CONFIG, ADVOGADO_BR_REPO, PRECEDENTES_DB e
LEIS_DB (usa um índice pronto, sem baixar nada — servidor remoto e testes).
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

REPO_PADRAO = "eduardommss/advogado-br"
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"


def _arquivo_config() -> Path:
    if os.environ.get("ADVOGADO_BR_CONFIG"):
        return Path(os.path.expanduser(os.environ["ADVOGADO_BR_CONFIG"]))
    if WINDOWS and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "advogado-br" / "config.json"
    return Path(os.path.expanduser(os.environ.get("XDG_CONFIG_HOME") or "~/.config")) / "advogado-br" / "config.json"


ARQUIVO = _arquivo_config()


@lru_cache(maxsize=1)
def _lido() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def _documentos() -> Path:
    """Pasta Documentos do usuário. No Windows lê a pasta real (pode ter sido movida para o OneDrive)."""
    if WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                valor, _ = winreg.QueryValueEx(k, "Personal")
            return Path(os.path.expandvars(valor))
        except OSError:
            return Path.home() / "Documents"
    for nome in ("Documents", "Documentos"):
        if (Path.home() / nome).is_dir():
            return Path.home() / nome
    return Path.home()


def cache_dir() -> Path:
    if os.environ.get("ADVOGADO_BR_CACHE"):
        return Path(os.path.expanduser(os.environ["ADVOGADO_BR_CACHE"]))
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "advogado-br"
    if MACOS:
        return Path.home() / "Library" / "Caches" / "advogado-br"
    return Path(os.path.expanduser(os.environ.get("XDG_CACHE_HOME") or "~/.cache")) / "advogado-br"


def juridico_dir() -> Path:
    valor = os.environ.get("JURIDICO_DIR") or _lido().get("juridico_dir")
    return Path(os.path.expanduser(str(valor))) if valor else _documentos() / "Juridico"


def escritorio_dir() -> Path:
    """Dados do escritório que valem para todos os casos (ficam junto dos casos, no mesmo backup)."""
    return juridico_dir() / "_escritorio"


def repo_base() -> str:
    return os.environ.get("ADVOGADO_BR_REPO") or _lido().get("repo_base") or REPO_PADRAO


def verificar_dias() -> int:
    try:
        return int(_lido().get("verificar_dias", 7))
    except (TypeError, ValueError):
        return 7


def leis_db_fixo() -> Path | None:
    return Path(os.path.expanduser(os.environ["LEIS_DB"])) if os.environ.get("LEIS_DB") else None


def obter(chave: str) -> Path:
    if chave == "juridico_dir":
        return juridico_dir()
    if chave == "precedentes_db":
        if os.environ.get("PRECEDENTES_DB"):
            return Path(os.path.expanduser(os.environ["PRECEDENTES_DB"]))
        return escritorio_dir() / "precedentes.db"
    if chave == "complementos":
        return escritorio_dir() / "complementos"
    if chave == "biblioteca":
        return escritorio_dir() / "biblioteca"
    if chave == "cache":
        return cache_dir()
    raise KeyError(chave)


def tudo() -> dict:
    return {
        "config": str(ARQUIVO), "cache_base": str(cache_dir()), "juridico_dir": str(juridico_dir()),
        "escritorio": str(escritorio_dir()), "precedentes_db": str(obter("precedentes_db")),
        "complementos": str(obter("complementos")), "biblioteca": str(obter("biblioteca")),
        "repo_base": repo_base(), "leis_db_fixo": str(leis_db_fixo()) if leis_db_fixo() else None,
    }


def salvar(**valores) -> Path:
    atual = _lido().copy()
    atual.update({k: str(v) for k, v in valores.items() if v})
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
    _lido.cache_clear()
    return ARQUIVO
