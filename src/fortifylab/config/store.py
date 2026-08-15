"""File-backed .env store with backups and rollback support."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

from .envfile import EnvDocument, EnvUpdate, apply_updates, parse_env_text


@dataclass(frozen=True)
class ConfigStore:
    env_file: Path
    backup_dir: Path | None = None
    rollback_file: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "env_file", Path(self.env_file))
        root = self.env_file.parent
        object.__setattr__(self, "backup_dir", Path(self.backup_dir) if self.backup_dir else root / ".env.backups")
        object.__setattr__(self, "rollback_file", Path(self.rollback_file) if self.rollback_file else root / ".env.rollback")

    def load(self) -> EnvDocument:
        return parse_env_text(self.env_file.read_text(encoding="utf-8"))

    def prepare_backup(self, reason: str) -> Path:
        assert self.backup_dir is not None
        assert self.rollback_file is not None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.backup_dir / f".env.{timestamp}.{reason}.bak"
        meta = self.backup_dir / f".env.{timestamp}.{reason}.meta"
        shutil.copy2(self.env_file, backup)
        meta.write_text(
            f"created_by=fortifylab-python\ncreated_at={timestamp}\nreason={reason}\n",
            encoding="utf-8",
        )
        self.rollback_file.write_text(f"{backup}\n", encoding="utf-8")
        return backup

    def apply(self, reason: str, updates: tuple[EnvUpdate, ...]) -> Path | None:
        if not updates:
            return None
        backup = self.prepare_backup(reason)
        document = apply_updates(self.load(), updates)
        self.env_file.write_text(document.render(), encoding="utf-8")
        self._append_changed_keys(backup, tuple(update.key for update in updates))
        return backup

    def rollback_last(self) -> Path:
        assert self.rollback_file is not None
        if self.rollback_file.exists():
            backup = Path(self.rollback_file.read_text(encoding="utf-8").strip())
        else:
            backup = next(iter(self.backups()), None)
            if backup is None:
                raise FileNotFoundError("No .env backups are available.")
        if not backup.exists():
            raise FileNotFoundError(f"Backup not found: {backup}")
        self.prepare_backup("before-rollback-last")
        shutil.copy2(backup, self.env_file)
        return backup

    def backups(self) -> tuple[Path, ...]:
        assert self.backup_dir is not None
        if not self.backup_dir.exists():
            return ()
        return tuple(sorted(self.backup_dir.glob(".env.*.bak"), reverse=True))

    def _append_changed_keys(self, backup: Path, keys: tuple[str, ...]) -> None:
        meta = backup.with_suffix(".meta")
        with meta.open("a", encoding="utf-8") as handle:
            handle.write(f"changed_keys={','.join(keys)}\n")
