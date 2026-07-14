import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Set, Optional
import os

logger = logging.getLogger("FileSearch.Config")

DEFAULT_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "csv", "json",
    "xml", "html", "css", "js", "ts", "py", "cpp", "c", "java", "sql", "zip",
    "rar", "7z", "png", "jpg", "jpeg", "gif", "bmp", "mp3", "wav", "mp4",
    "mkv", "avi", "exe"
}

DEFAULT_EXCLUSIONS = {
    # System folders
    "Windows", "Program Files", "Program Files (x86)", "AppData", "System32",
    # Cache / metadata
    "__pycache__", ".git", ".svn", ".idea", ".vscode", "node_modules",
    # Recycler
    "$RECYCLE.BIN", "System Volume Information"
}

@dataclass
class FileSearchConfig:
    search_paths: List[str] = field(default_factory=list)
    excluded_paths: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUSIONS))
    supported_extensions: List[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    index_refresh_minutes: int = 10
    index_db_path: str = ""

    def __post_init__(self):
        # Resolve search paths if empty
        if not self.search_paths:
            self.search_paths = self._detect_default_search_paths()
        
        # Resolve index DB path
        if not self.index_db_path:
            self.index_db_path = str(Path.home() / ".file_search_index.db")

    def _detect_default_search_paths(self) -> List[str]:
        paths = []
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            )
            mapping = {
                "desktop": "Desktop",
                "documents": "Personal",
                "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
                "pictures": "My Pictures",
                "videos": "My Video",
                "music": "My Music"
            }
            for name, reg_key in mapping.items():
                try:
                    val, _ = winreg.QueryValueEx(key, reg_key)
                    val_expanded = os.path.expandvars(val)
                    p = Path(val_expanded)
                    if p.exists():
                        paths.append(str(p.resolve()))
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.warning(f"Failed to query registry for shell folders: {e}")
            
        # Fallback to standard folders if registry didn't work or returned nothing
        if not paths:
            home = Path.home()
            fallbacks = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]
            for f in fallbacks:
                p = home / f
                if p.exists():
                    paths.append(str(p.resolve()))
                    
        return paths

    @classmethod
    def load(cls, config_path: Path) -> "FileSearchConfig":
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                logger.error(f"Failed to load config from {config_path}: {e}. Using defaults.")
        return cls()

    def save(self, config_path: Path) -> None:
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config to {config_path}: {e}")
