"""Ferramentas de caso expostas pelo servidor MCP.

Reaproveita o skills/organizar-caso/scripts/caso.py (fonte única da lógica) para que um cliente remoto — o app do
Claude no Windows, que roda o raciocínio na nuvem — organize as pastas de casos da máquina onde o servidor roda,
sem precisar de terminal. Também converte caminhos do Windows (C:\\...) quando o servidor roda no WSL e lê o texto de
documentos dos casos (.md, .txt, .pdf, .docx).
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import re
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_CASO_PY = AQUI.parent / "skills" / "organizar-caso" / "scripts" / "caso.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("caso_advogado_br", _CASO_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _em_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def caminho_local(p: str) -> str:
    """'C:\\Users\\eu\\Downloads\\x.pdf' -> '/mnt/c/Users/eu/Downloads/x.pdf' quando o servidor roda no WSL."""
    p = (p or "").strip().strip('"')
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if m and _em_wsl():
        return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")
    return os.path.expanduser(p)


def caminho_windows(p: str) -> str | None:
    """Inverso, para mostrar ao usuário onde o arquivo está no Explorer."""
    m = re.match(r"^/mnt/([a-z])/(.*)$", str(p))
    return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\") if m else None


def _rodar(cmd: str, **kwargs) -> dict:
    mod = _modulo()
    ns = argparse.Namespace(cmd=cmd, **kwargs)
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            getattr(mod, "cmd_" + cmd)(ns)
    except SystemExit as e:
        return {"ok": False, "erro": str(e.code) if e.code not in (None, 0) else saida.getvalue().strip()}
    texto = saida.getvalue().strip()
    try:
        r = json.loads(texto)
    except ValueError:
        return {"ok": True, "saida": texto}
    return _anotar(r)


def _anotar(r):
    """Acrescenta o caminho do Windows ao lado de cada 'pasta' (útil para abrir no Explorer)."""
    if isinstance(r, dict):
        if isinstance(r.get("pasta"), str) and caminho_windows(r["pasta"]):
            r["pasta_windows"] = caminho_windows(r["pasta"])
        return {k: _anotar(v) if isinstance(v, (dict, list)) else v for k, v in r.items()}
    if isinstance(r, list):
        return [_anotar(x) for x in r]
    return r


def raiz() -> str:
    return str(_modulo().raiz())


# ----------------------------------------------------------------------------- operações

def listar(todos: bool = False) -> dict:
    r = _rodar("listar", todos=todos)
    return {"raiz": raiz(), "raiz_windows": caminho_windows(raiz()), "casos": r if isinstance(r, list) else r}


def status(caso: str) -> dict:
    return _rodar("status", caso=caso)


def novo(titulo: str, tipo: str = "outro", area: str | None = None, papel: str | None = None,
         partes: list[str] | None = None, processo: str | None = None, tribunal: str | None = None,
         notas: str | None = None) -> dict:
    return _rodar("novo", titulo=titulo, tipo=tipo, area=area, papel=papel, parte=partes or [], processo=processo,
                  tribunal=tribunal, notas=notas)


def _pasta_caso(caso: str) -> Path | None:
    mod = _modulo()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return mod.achar(caso)
    except SystemExit:
        return None


def arquivar(caso: str, arquivo: str, categoria: str, descricao: str, data: str | None = None,
             nota: str | None = None, mover: bool = False) -> dict:
    r = _rodar("arquivar", caso=caso, arquivo=caminho_local(arquivo), categoria=categoria, descricao=descricao,
               data=data, nota=nota, mover=mover)
    pasta = _pasta_caso(caso)
    if r.get("ok") and pasta and r.get("arquivo"):
        completo = pasta / r["arquivo"]
        r["arquivo_completo"] = str(completo)
        r["arquivo_windows"] = caminho_windows(completo)
    return r


def link(caso: str, url: str, descricao: str = "") -> dict:
    return _rodar("link", caso=caso, url=url, descricao=descricao)


def evento(caso: str, descricao: str, data: str | None = None) -> dict:
    return _rodar("evento", caso=caso, data=data, descricao=descricao)


def prazo(caso: str, descricao: str, data: str | None = None, cumprido: bool = False) -> dict:
    return _rodar("prazo", caso=caso, data=data, descricao=descricao, cumprido=cumprido)


def fase(caso: str, fase_nova: str) -> dict:
    return _rodar("fase", caso=caso, fase=fase_nova)


def passo(caso: str, acao: str, motivo: str | None = None, skill: str | None = None) -> dict:
    return _rodar("passo", caso=caso, acao=acao, motivo=motivo, skill=skill)


def atualizar(caso: str, **campos) -> dict:
    base = {k: None for k in ("titulo", "area", "papel_cliente", "numero_processo", "tribunal", "notas", "status")}
    base.update({k: v for k, v in campos.items() if k in base})
    return _rodar("atualizar", caso=caso, parte=campos.get("partes") or [], **base)


def prazos(dias: int = 30) -> dict:
    r = _rodar("prazos", dias=dias)
    return {"prazos": r} if isinstance(r, list) else r


def entrada() -> dict:
    return _rodar("entrada")


def indice() -> dict:
    return _rodar("indice")


def salvar_texto(caso: str, categoria: str, descricao: str, conteudo: str, extensao: str = "md",
                 data: str | None = None) -> dict:
    """Grava um texto produzido na conversa (análise, minuta, estratégia) como arquivo do caso."""
    import tempfile
    ext = re.sub(r"[^a-z0-9]", "", (extensao or "md").lower()) or "md"
    with tempfile.NamedTemporaryFile("w", suffix="." + ext, delete=False, encoding="utf-8") as f:
        f.write(conteudo)
        tmp = f.name
    try:
        return arquivar(caso, tmp, categoria, descricao, data=data)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


# ----------------------------------------------------------------------------- leitura de documentos

_LIMITE = 200_000


def _texto_docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    texto = re.sub(r"<[^>]+>", "", xml)
    import html
    return html.unescape(texto)


def _texto_pdf(p: Path) -> str:
    try:
        from pypdf import PdfReader  # dependência declarada no servidor.py (uv instala)
    except ImportError:
        import shutil
        import subprocess
        if shutil.which("pdftotext"):
            return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
        raise RuntimeError("Sem leitor de PDF: rode o servidor pelo uv (instala o pypdf).")
    leitor = PdfReader(str(p))
    paginas = [f"--- página {i} ---\n{(pg.extract_text() or '').strip()}" for i, pg in enumerate(leitor.pages, 1)]
    return "\n\n".join(paginas)


def ler_documento(caminho: str, inicio: int = 0, caso: str | None = None) -> dict:
    """Texto de um documento dentro da pasta de casos (ou da _ENTRADA). Aceita caminho do Windows.
    Caminho relativo: à pasta do caso (se 'caso' for informado) ou à raiz dos casos."""
    raiz_casos = Path(raiz()).resolve()
    p = Path(caminho_local(caminho))
    if not p.is_absolute():
        base = _pasta_caso(caso) if caso else None
        p = (base or raiz_casos) / p
    p = p.resolve()
    if raiz_casos not in p.parents and p != raiz_casos:
        return {"ok": False, "erro": f"Só leio arquivos dentro da pasta de casos ({raiz_casos}). Arquive o arquivo no "
                                     "caso (ou coloque na _ENTRADA) primeiro."}
    if not p.is_file():
        return {"ok": False, "erro": f"Arquivo não encontrado: {p}"}
    ext = p.suffix.lower()
    try:
        if ext in (".md", ".txt", ".json", ".csv", ".eml", ".html", ".htm", ".xml"):
            texto = p.read_text(encoding="utf-8", errors="replace")
        elif ext == ".pdf":
            texto = _texto_pdf(p)
        elif ext == ".docx":
            texto = _texto_docx(p)
        else:
            return {"ok": False, "erro": f"Formato {ext} não é texto (imagem/áudio/vídeo). Peça ao usuário para anexar "
                                         "o arquivo na conversa ou conectar a pasta para você vê-lo."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": f"Falha ao ler {p.name}: {e}"}
    if ext == ".pdf" and len(texto.replace("--- página", "").strip()) < 50 * max(1, texto.count("--- página")):
        aviso = "PDF parece escaneado (pouco texto extraído). Peça o arquivo anexado na conversa para ler as imagens."
    else:
        aviso = None
    trecho = texto[inicio:inicio + _LIMITE]
    return {"ok": True, "arquivo": str(p), "arquivo_windows": caminho_windows(p), "caracteres": len(texto),
            "inicio": inicio, "proximo_inicio": inicio + _LIMITE if inicio + _LIMITE < len(texto) else None,
            "aviso": aviso, "texto": trecho}
