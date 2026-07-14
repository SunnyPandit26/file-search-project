import ctypes
import logging
import os
import string
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from .config import FileSearchConfig
from .indexer import FileIndexer, IndexedFile
from .matcher import FileMatcher

logger = logging.getLogger("FileSearch.SearchEngine")

def get_drive_letters() -> List[str]:
    """Retrieve all active logical drive letters on Windows."""
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(f"{letter}:\\")
        bitmask >>= 1
    return drives

class SearchEngine:
    def __init__(self, config: FileSearchConfig, indexer: FileIndexer, matcher: FileMatcher):
        self.config = config
        self.indexer = indexer
        self.matcher = matcher

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the indexed files for the given query."""
        start_time = time.time()
        query_clean = query.strip()
        if not query_clean:
            return []

        logger.info(f"Searching index for query: '{query_clean}'")
        all_files = self.indexer.get_all_files()
        results = []
        current_time = time.time()

        for f in all_files:
            # First level check: pre-filter to reject obvious mismatches quickly
            if not self.matcher.pre_filter(query_clean, f.filename):
                continue

            score = self.matcher.score_match(
                query=query_clean,
                filename=f.filename,
                ext=f.extension,
                mtime=f.modified_time,
                current_time=current_time
            )

            if score >= self.matcher.threshold:
                results.append({
                    "path": f.path,
                    "filename": f.filename,
                    "extension": f.extension,
                    "modified_time": f.modified_time,
                    "size": f.size,
                    "score": score
                })

        # Rank matches: higher score first. If scores are identical, sort by modification time (newer first)
        results.sort(key=lambda x: (-x["score"], -x["modified_time"]))
        
        time_taken = time.time() - start_time
        logger.info(f"Search for '{query_clean}' returned {len(results)} matches in {time_taken:.4f}s")
        return results

    def search_full_drive(self, query: str) -> List[Dict[str, Any]]:
        """Walks all logical drives to search for the file, bypassing index."""
        start_time = time.time()
        query_clean = query.strip()
        if not query_clean:
            return []

        logger.info(f"Starting full drive search for: '{query_clean}'")
        drives = get_drive_letters()
        results = []
        query_lower = query_clean.lower()
        excluded_names = {name.lower() for name in self.config.excluded_paths}
        current_time = time.time()

        for drive in drives:
            logger.info(f"Scanning drive: {drive}")
            for root, dirs, files in os.walk(drive, topdown=True):
                # Prune excluded directories
                pruned_dirs = []
                for d in dirs:
                    d_lower = d.lower()
                    if d_lower in excluded_names or d.startswith('.'):
                        continue
                    pruned_dirs.append(d)
                dirs[:] = pruned_dirs

                for file in files:
                    if query_lower in file.lower():
                        file_path = Path(root) / file
                        ext = file_path.suffix.lower().lstrip('.')
                        try:
                            stat = file_path.stat()
                            mtime = stat.st_mtime
                            size = stat.st_size
                        except Exception:
                            # Skip permission-denied or locked files
                            continue

                        score = self.matcher.score_match(
                            query=query_clean,
                            filename=file,
                            ext=ext,
                            mtime=mtime,
                            current_time=current_time
                        )

                        results.append({
                            "path": str(file_path.resolve()),
                            "filename": file,
                            "extension": ext,
                            "modified_time": mtime,
                            "size": size,
                            "score": score
                        })

                        # Stop if we hit a high limit to prevent scanning entire system indefinitely
                        if len(results) >= 50:
                            break
                if len(results) >= 50:
                    break

        results.sort(key=lambda x: (-x["score"], -x["modified_time"]))
        time_taken = time.time() - start_time
        logger.info(f"Full drive search completed in {time_taken:.2f}s, found {len(results)} matches.")
        return results
