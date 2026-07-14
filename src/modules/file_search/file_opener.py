import os
import logging
from pathlib import Path

logger = logging.getLogger("FileSearch.FileOpener")

class FileOpener:
    @staticmethod
    def open_file(file_path_str: str) -> bool:
        """Opens a file using the Windows default application, resolving shortcuts and long paths."""
        logger.info(f"Attempting to open file: {file_path_str}")
        try:
            path = Path(file_path_str)
            
            # Check if file exists
            if not path.exists():
                logger.error(f"Failed to open file: File does not exist at {file_path_str}")
                raise FileNotFoundError(f"File not found: {file_path_str}")

            # Resolve to absolute path and normalize slashes to backslashes
            abs_path = path.resolve()
            abs_path_str = str(abs_path).replace('/', '\\')

            # Support very long paths in Windows (prefix with \\?\)
            if not abs_path_str.startswith("\\\\?\\"):
                abs_path_str = "\\\\?\\" + abs_path_str

            # os.startfile triggers the OS shell default associated application
            os.startfile(abs_path_str)
            logger.info(f"Successfully opened file: {abs_path_str}")
            return True

        except PermissionError as e:
            logger.error(f"Permission denied while trying to open {file_path_str}: {e}")
            raise PermissionError(f"Permission denied: {file_path_str}") from e
        except FileNotFoundError as e:
            logger.error(f"File not found: {file_path_str}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error opening file {file_path_str}: {e}")
            raise OSError(f"Failed to open file due to system error: {e}") from e
