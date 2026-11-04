"""Separa HTML y recursos públicos de un build Vite completo antes de publicarlo."""

import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

ASSET_PREFIX = "/static/entrepares/"
VERSIONED_NAME = re.compile(r"^assets/[^/]+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")


class DocumentResources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        key = "src" if tag == "script" else "href" if tag == "link" else None
        if key and attrs.get(key):
            self.urls.append(attrs[key])


def build_file(source, name):
    relative = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or relative.is_absolute()
        or any(part in {".", ".."} or part.startswith(".") for part in name.split("/"))
    ):
        raise ValueError("El build contiene una ruta no permitida.")
    path = source / relative
    if not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
        raise ValueError("El build está incompleto o contiene un recurso externo.")
    return path


def prepare_frontend(source: Path, target: Path):
    source, target = source.resolve(), target.resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("El origen y el destino del build deben estar separados.")
    content = (source / "index.html").read_bytes()
    manifest = json.loads((source / ".vite/manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest.get("index.html", {}).get("isEntry"):
        raise ValueError("No se encontró la entrada HTML de Vite.")
    versioned = set()
    for entry in manifest.values():
        if not isinstance(entry, dict):
            raise ValueError("El manifiesto de Vite no es válido.")
        for name in [entry.get("file", ""), *entry.get("css", []), *entry.get("assets", [])]:
            build_file(source, name)
            if not VERSIONED_NAME.fullmatch(name):
                raise ValueError("Los recursos de Vite deben tener un nombre versionado.")
            versioned.add(name)
        for key in [*entry.get("imports", []), *entry.get("dynamicImports", [])]:
            if key not in manifest:
                raise ValueError("Falta un módulo referenciado en el manifiesto.")
    parser = DocumentResources()
    parser.feed(content.decode("utf-8"))
    if not parser.urls:
        raise ValueError("El documento no contiene recursos compilados.")
    for url in parser.urls:
        if not url.startswith(ASSET_PREFIX):
            raise ValueError("El documento debe usar recursos del mismo origen bajo /static/.")
        build_file(source, url.removeprefix(ASSET_PREFIX))
    files = []
    for file in source.rglob("*"):
        name = file.relative_to(source).as_posix()
        if file.is_symlink():
            raise ValueError("El build no debe contener enlaces simbólicos.")
        if (
            not file.is_file()
            or name == "index.html"
            or any(part.startswith(".") for part in file.relative_to(source).parts)
        ):
            continue
        build_file(source, name)
        files.append((file, name))
    # Publicar el HTML al final: un fallo de validación no sustituye el documento anterior.
    for file, name in files:
        destination = target / "static" / "entrepares" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, destination)
    target.mkdir(parents=True, exist_ok=True)
    urls = [ASSET_PREFIX + name for name in sorted(versioned)]
    for name, data in [
        ("versioned-assets.json", (json.dumps(urls, indent=2) + "\n").encode()),
        ("index.html", content),
    ]:
        temporary = target / (name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target / name)
    return {"public_files": len(files), "versioned_assets": len(urls)}
