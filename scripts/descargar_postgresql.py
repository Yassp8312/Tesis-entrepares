"""Distribución privada de PostgreSQL para Windows, sin instalador ni servicio."""

import concurrent.futures
import hashlib
import http.client
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def ensure_runtime():
    spec = json.loads((REPO / "scripts/postgresql-runtime.json").read_text(encoding="utf-8"))
    root = REPO / ".tools" / "postgresql" / spec["version"]
    root.mkdir(parents=True, exist_ok=True)
    bin_dir = root / "pgsql" / "bin"
    ready = root / "runtime-ready.json"
    if ready.exists() and json.loads(ready.read_text())["sha256"] == spec["sha256"]:
        if all((bin_dir / name).exists() for name in ["postgres.exe", "pg_ctl.exe", "initdb.exe"]):
            return spec, root, bin_dir

    archive = root / spec["filename"]
    archive_valid = False
    if archive.exists():
        with archive.open("rb") as source:
            archive_valid = hashlib.file_digest(source, "sha256").hexdigest() == spec["sha256"]
    if not archive_valid:
        part_size = 4 * 1024 * 1024
        parts = root / "download-parts"
        parts.mkdir(exist_ok=True)

        def download_part(number):
            start = number * part_size
            end = min(spec["bytes"], start + part_size) - 1
            path = parts / f"{number:04}.part"
            if path.exists() and path.stat().st_size == end - start + 1:
                return path
            content = b""
            for _ in range(8):
                offset = start + len(content)
                request = urllib.request.Request(
                    spec["url"] + f"?entrepares_part={number}&offset={offset}",
                    headers={"Range": f"bytes={offset}-{end}", "User-Agent": "Entrepares setup"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=45) as response:
                        if response.status != 206 or not response.headers.get(
                            "Content-Range", ""
                        ).startswith(f"bytes {offset}-"):
                            raise RuntimeError(
                                "El servidor no devuelve el rango de descarga solicitado."
                            )
                        try:
                            chunk = response.read()
                        except http.client.IncompleteRead as error:
                            chunk = error.partial
                except (OSError, urllib.error.URLError, http.client.HTTPException):
                    continue
                content += chunk
                if len(content) == end - start + 1:
                    path.write_bytes(content)
                    return path
                if len(content) > end - start + 1:
                    raise RuntimeError("La descarga supera el tamaño previsto.")
            raise RuntimeError("No se pudo completar una parte de PostgreSQL.")

        count = (spec["bytes"] + part_size - 1) // part_size
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(download_part, range(count)))
        with archive.open("wb") as output:
            for number in range(count):
                with (parts / f"{number:04}.part").open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)

    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if archive.stat().st_size != spec["bytes"] or digest != spec["sha256"]:
        raise RuntimeError("El archivo de PostgreSQL no coincide con la huella fijada.")
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise RuntimeError("Falló la integridad del archivo ZIP de PostgreSQL.")
        for name in package.namelist():
            if name.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                if not (root / name).resolve().is_relative_to(root.resolve()):
                    raise RuntimeError("El paquete contiene una ruta fuera de su destino.")
                package.extract(name, root)
    ready.write_text(json.dumps({"version": spec["version"], "sha256": digest}) + "\n")
    return spec, root, bin_dir
