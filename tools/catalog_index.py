"""Índice de projetos (web/public/assets/catalog/index.json) — a página usa para listar e abrir projetos."""

from __future__ import annotations

import json
from pathlib import Path


def update_index(catalog_dir: Path, project_id: str, name: str, make_default: bool = False,
                 listed: bool = True) -> Path:
    """Registra o projeto no índice. listed=False tira do menu (continua acessível por ?project=id)."""
    path = catalog_dir / "index.json"
    data = {"default": project_id, "projects": []}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    projects = [p for p in data.get("projects", []) if p.get("id") != project_id]
    if listed:
        projects.append({"id": project_id, "name": name, "catalog": f"assets/catalog/{project_id}.json"})
    projects.sort(key=lambda p: p["id"])
    data["projects"] = projects
    ids = {p["id"] for p in projects}
    if listed and (make_default or not data.get("default") or data["default"] not in ids):
        data["default"] = project_id
    elif data.get("default") not in ids:
        data["default"] = projects[0]["id"] if projects else project_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
