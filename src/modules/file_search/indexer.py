import sqlite3
import threading
import time
import logging
import os
from pathlib import Path
from typing import List, Set, Generator, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from .config import FileSearchConfig

logger = logging.getLogger("FileSearch.Indexer")

@dataclass
class IndexedFile:
    path: str
    filename: str
    extension: str
    modified_time: float
    size: int

class FileIndexer:
    def __init__(self, config: FileSearchConfig):
        self.config = config
        self.db_path = config.index_db_path
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # SQLite is fine with concurrent reads. Use WAL mode to avoid database locking.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS file_index (
                        path TEXT PRIMARY KEY,
                        filename TEXT,
                        extension TEXT,
                        modified_time REAL,
                        size INTEGER
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_filename ON file_index(filename)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_extension ON file_index(extension)")
                conn.commit()
            finally:
                conn.close()

    def start_background_updater(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.info("Background indexer is already running.")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("Background indexer started.")

    def stop_background_updater(self):
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=5)
            self._thread = None
            logger.info("Background indexer stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            logger.info("Starting background index refresh...")
            start_time = time.time()
            try:
                self.update_index()
                elapsed = time.time() - start_time
                logger.info(f"Index refresh completed in {elapsed:.2f} seconds.")
            except Exception as e:
                logger.error(f"Error during background index update: {e}", exc_info=True)
            
            # Sleep in small increments to be responsive to stop events
            sleep_needed = self.config.index_refresh_minutes * 60
            sleep_step = 1.0
            elapsed_sleep = 0.0
            while elapsed_sleep < sleep_needed and not self._stop_event.is_set():
                time.sleep(sleep_step)
                elapsed_sleep += sleep_step

    def update_index(self):
        """Scans configured paths and updates the database."""
        logger.info("Scanning directories to update index...")
        seen_paths: Set[str] = set()
        
        # We process files in batches to keep memory usage low and insert efficiently
        batch: List[Tuple[str, str, str, float, int]] = []
        batch_size = 1000

        supported_exts = {ext.lower().lstrip('.') for ext in self.config.supported_extensions}
        excluded_names = {name.lower() for name in self.config.excluded_paths}

        # Convert excluded paths to Path objects for relative checking
        excluded_absolute_paths: List[Path] = []
        for ep in self.config.excluded_paths:
            try:
                ep_path = Path(ep)
                if ep_path.is_absolute():
                    excluded_absolute_paths.append(ep_path.resolve())
            except Exception:
                pass

        def is_excluded(path: Path) -> bool:
            try:
                resolved_path = path.resolve()
            except Exception:
                resolved_path = path

            # Check absolute exclusions
            for ep in excluded_absolute_paths:
                try:
                    if resolved_path.is_relative_to(ep):
                        return True
                except Exception:
                    pass

            # Check component names
            for part in path.parts:
                part_lower = part.lower()
                if part_lower in excluded_names:
                    return True
                # Exclude hidden folders starting with dot
                if part != Path(path.anchor).name and part.startswith('.'):
                    return True
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        
        for search_path_str in self.config.search_paths:
            search_path = Path(search_path_str)
            if not search_path.exists():
                logger.warning(f"Configured search path does not exist: {search_path}")
                continue

            # Walk using os.walk to handle directories and files safely
            for root, dirs, files in os.walk(search_path, topdown=True):
                # Prune excluded directories in-place
                pruned_dirs = []
                for d in dirs:
                    d_path = Path(root) / d
                    if is_excluded(d_path):
                        continue
                    pruned_dirs.append(d)
                dirs[:] = pruned_dirs

                for file in files:
                    file_path = Path(root) / file
                    if is_excluded(file_path):
                        continue

                    # Process extension
                    ext = file_path.suffix.lower().lstrip('.')
                    if supported_exts and ext not in supported_exts:
                        continue

                    # Resolve path
                    try:
                        abs_path = str(file_path.resolve())
                    except Exception as e:
                        logger.warning(f"Could not resolve path for {file_path}: {e}")
                        continue
                    
                    seen_paths.add(abs_path)

                    # Get metadata
                    try:
                        stat = file_path.stat()
                        mtime = stat.st_mtime
                        size = stat.st_size
                    except Exception as e:
                        logger.debug(f"Could not read stats for {file_path}: {e}")
                        continue

                    batch.append((abs_path, file, ext, mtime, size))

                    if len(batch) >= batch_size:
                        self._upsert_batch(cursor, batch)
                        batch.clear()

        if batch:
            self._upsert_batch(cursor, batch)
            batch.clear()

        # Clean up database: remove files that were not seen in this scan
        logger.info("Cleaning up deleted files from index...")
        
        cursor.execute("SELECT path FROM file_index")
        db_paths = [row['path'] for row in cursor.fetchall()]
        
        paths_to_delete = []
        for path_str in db_paths:
            if path_str not in seen_paths:
                try:
                    p = Path(path_str)
                    # Only delete if it belongs to a path we scanned and is truly missing
                    belongs_to_search_paths = any(
                        p.is_relative_to(Path(sp)) for sp in self.config.search_paths
                    )
                    if belongs_to_search_paths and not p.exists():
                        paths_to_delete.append((path_str,))
                except Exception:
                    paths_to_delete.append((path_str,))

        if paths_to_delete:
            cursor.executemany("DELETE FROM file_index WHERE path = ?", paths_to_delete)
            logger.info(f"Removed {len(paths_to_delete)} stale files from index.")

        conn.commit()
        conn.close()

    def _upsert_batch(self, cursor: sqlite3.Cursor, batch: List[Tuple[str, str, str, float, int]]):
        cursor.executemany("""
            INSERT INTO file_index (path, filename, extension, modified_time, size)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                filename = excluded.filename,
                extension = excluded.extension,
                modified_time = excluded.modified_time,
                size = excluded.size
        """, batch)

    def get_all_files(self) -> List[IndexedFile]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT path, filename, extension, modified_time, size FROM file_index")
            rows = cursor.fetchall()
            return [
                IndexedFile(
                    path=row['path'],
                    filename=row['filename'],
                    extension=row['extension'],
                    modified_time=row['modified_time'],
                    size=row['size']
                ) for row in rows
            ]
        finally:
            conn.close()
