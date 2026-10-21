"""Storage persistente local para artefatos de ML.

O diretório é configurável por ``MODEL_STORAGE_DIR`` e deve apontar para um volume
persistente em produção. Na primeira inicialização, arquivos do caminho legado
``backend/models/trained`` são copiados preservando a estrutura.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import get_settings

_STORAGE_MARKER = ".migrated_from_backend_models_v1"


def legacy_models_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "trained"


class ModelArtifactStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            self.root = Path(__file__).resolve().parents[3] / self.root
        self.root.mkdir(parents=True, exist_ok=True)
        self.migrate_legacy()

    def _safe_path(self, key: str) -> Path:
        relative = Path(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Chave de artefato inválida: {key!r}")
        return self.root / relative

    def migrate_legacy(self) -> int:
        """Copia artefatos antigos apenas quando ainda não existem no storage novo."""
        legacy = legacy_models_dir()
        if legacy.resolve() == self.root.resolve() or not legacy.exists():
            return 0
        copied = 0
        for source in legacy.rglob("*"):
            if not source.is_file():
                continue
            target = self.root / source.relative_to(legacy)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied += 1
        marker = self.root / _STORAGE_MARKER
        if not marker.exists():
            marker.write_text("legacy artifacts migrated\n", encoding="utf-8")
        return copied

    def path(self, key: str) -> Path:
        target = self._safe_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def resolve(self, storage_path: str) -> Path:
        """Resolve caminhos novos, ``file://`` e caminhos absolutos legados."""
        parsed = urlparse(storage_path)
        raw = unquote(parsed.path) if parsed.scheme == "file" else storage_path
        candidate = Path(raw).expanduser()
        legacy = legacy_models_dir()
        try:
            relative = candidate.relative_to(legacy)
        except ValueError:
            relative = Path(raw.removeprefix("models/trained/") if raw.startswith("models/trained/") else raw)
        migrated = self.root / relative
        if migrated.exists():
            return migrated
        if candidate.exists():
            return candidate
        return migrated

    def uri(self, key: str) -> str:
        return self.path(key).resolve().as_uri()


def get_model_storage() -> ModelArtifactStorage:
    return ModelArtifactStorage(get_settings().model_storage_dir)
