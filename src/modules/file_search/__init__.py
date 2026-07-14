from pathlib import Path
from typing import Optional

from .config import FileSearchConfig
from .indexer import FileIndexer, IndexedFile
from .matcher import FileMatcher
from .search_engine import SearchEngine
from .file_opener import FileOpener
from .intent_handler import FileSearchIntentHandler, InteractionState

class FileSearchManager:
    def __init__(self, config_file_path: Optional[Path] = None):
        if config_file_path is None:
            config_file_path = Path.home() / ".file_search_config.json"
        
        self.config_file_path = config_file_path
        self.config = FileSearchConfig.load(config_file_path)
        # Save config back to write defaults if file didn't exist
        self.config.save(config_file_path)

        self.indexer = FileIndexer(self.config)
        self.matcher = FileMatcher()
        self.search_engine = SearchEngine(self.config, self.indexer, self.matcher)
        self.intent_handler = FileSearchIntentHandler(self.search_engine)

    def start(self) -> None:
        """Start the background index refresh thread."""
        self.indexer.start_background_updater()

    def stop(self) -> None:
        """Stop the background index refresh thread."""
        self.indexer.stop_background_updater()

    def handle_command(self, text: str) -> str:
        """Handle a user voice assistant command."""
        return self.intent_handler.handle_command(text)

    def is_file_search_intent(self, text: str) -> bool:
        """Determine if a user command is a file search intent or part of a running conversation flow."""
        return self.intent_handler.is_file_search_intent(text)
