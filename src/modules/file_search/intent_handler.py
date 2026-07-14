import logging
import re
from enum import Enum, auto
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from .search_engine import SearchEngine
from .file_opener import FileOpener

logger = logging.getLogger("FileSearch.IntentHandler")

class InteractionState(Enum):
    IDLE = auto()
    AWAITING_SELECTION = auto()
    AWAITING_FULL_DRIVE_SEARCH = auto()

class FileSearchIntentHandler:
    def __init__(self, search_engine: SearchEngine):
        self.search_engine = search_engine
        self.state = InteractionState.IDLE
        self.pending_candidates: List[Dict[str, Any]] = []
        self.pending_query: str = ""

        # Precompiled regex for intents
        # Match verbs like open, find, search, locate, optionally followed by helper words like "file named", "my", "the"
        self.intent_regex = re.compile(
            r"^(?:open\s+the\s+file\s+named|open\s+file|open\s+my|open\s+the|open|"
            r"find\s+the\s+file\s+named|find\s+file|find\s+my|find\s+the|find|"
            r"search\s+for\s+the\s+file\s+named|search\s+for\s+image|search\s+for|search\s+my|search|"
            r"locate\s+the\s+file\s+named|locate\s+file|locate)\s+(.+)$",
            re.IGNORECASE
        )

    def is_file_search_intent(self, text: str) -> bool:
        """Determines if the text contains a file search command."""
        text_clean = text.strip()
        # If we are not idle, we are in a conversation flow and must intercept the input
        if self.state != InteractionState.IDLE:
            return True
        return bool(self.intent_regex.match(text_clean))

    def handle_command(self, user_input: str) -> str:
        """Processes user voice commands and returns the assistant's voice/text response."""
        user_input_clean = user_input.strip()
        logger.info(f"Processing command in state {self.state.name}: '{user_input_clean}'")

        if self.state == InteractionState.AWAITING_SELECTION:
            return self._handle_selection(user_input_clean)
        
        elif self.state == InteractionState.AWAITING_FULL_DRIVE_SEARCH:
            return self._handle_full_drive_search_confirmation(user_input_clean)
            
        else: # IDLE state
            match = self.intent_regex.match(user_input_clean)
            if match:
                query = match.group(1).strip()
            else:
                # If it doesn't match the verb pattern, but the router routed it here, search the whole input
                query = user_input_clean

            if not query:
                return "What file would you like me to find?"

            return self._execute_search(query)

    def _execute_search(self, query: str) -> str:
        self.pending_query = query
        try:
            results = self.search_engine.search(query)
        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            return f"An error occurred while searching for the file: {e}"

        if not results:
            self.state = InteractionState.AWAITING_FULL_DRIVE_SEARCH
            return "I couldn't find that file. Would you like me to search the entire drive?"

        if len(results) == 1:
            # Single match - open immediately
            candidate = results[0]
            try:
                FileOpener.open_file(candidate["path"])
                logger.info(f"Opened single match: {candidate['path']}")
                return f"I found {candidate['filename']}. Opening it."
            except Exception as e:
                return f"I found {candidate['filename']}, but couldn't open it: {e}"

        # Multiple matches - ask for confirmation
        # Keep up to 5 best matches
        self.pending_candidates = results[:5]
        self.state = InteractionState.AWAITING_SELECTION
        
        response_lines = [f"I found {len(results)} files."]
        for idx, item in enumerate(self.pending_candidates, 1):
            response_lines.append(f"{idx}. {item['filename']}")
        response_lines.append("Which one should I open?")
        
        return "\n".join(response_lines)

    def _handle_selection(self, user_input: str) -> str:
        # Check for cancel keywords
        if user_input.lower() in ["cancel", "none", "neither", "no", "stop", "exit"]:
            self._reset_state()
            return "Okay, cancelled."

        # Parse index
        idx = self._parse_ordinal_or_number(user_input, len(self.pending_candidates))
        if idx is not None:
            chosen = self.pending_candidates[idx]
            try:
                FileOpener.open_file(chosen["path"])
                logger.info(f"Opened chosen file: {chosen['path']}")
                self._reset_state()
                return f"Opening {chosen['filename']}."
            except Exception as e:
                self._reset_state()
                return f"Could not open {chosen['filename']}: {e}"

        # If user typed or spoke a filename, we can try to matches against the candidate list
        # E.g. "Resume Final.pdf" matching "Resume Final.pdf"
        best_candidate = None
        best_match_len = 0
        user_input_lower = user_input.lower()
        for candidate in self.pending_candidates:
            cand_name_lower = candidate["filename"].lower()
            if user_input_lower == cand_name_lower or user_input_lower == Path(cand_name_lower).stem:
                best_candidate = candidate
                break
            # substring check as fallback
            if user_input_lower in cand_name_lower:
                if len(user_input_lower) > best_match_len:
                    best_candidate = candidate
                    best_match_len = len(user_input_lower)

        if best_candidate:
            try:
                FileOpener.open_file(best_candidate["path"])
                logger.info(f"Opened best candidate by name match: {best_candidate['path']}")
                self._reset_state()
                return f"Opening {best_candidate['filename']}."
            except Exception as e:
                self._reset_state()
                return f"Could not open {best_candidate['filename']}: {e}"

        # If we couldn't match, ask again
        return f"I couldn't understand that choice. Please say the number (1 to {len(self.pending_candidates)}) or say cancel."

    def _handle_full_drive_search_confirmation(self, user_input: str) -> str:
        user_input_lower = user_input.lower()
        if user_input_lower in ["yes", "yeah", "y", "sure", "ok", "please", "do it"]:
            # Run full drive search
            logger.info(f"Executing full drive search for '{self.pending_query}'")
            try:
                results = self.search_engine.search_full_drive(self.pending_query)
            except Exception as e:
                logger.error(f"Error during full drive search: {e}", exc_info=True)
                self._reset_state()
                return f"An error occurred during full drive search: {e}"

            if not results:
                self._reset_state()
                return "I still couldn't find any matching files on the drive."

            if len(results) == 1:
                candidate = results[0]
                try:
                    FileOpener.open_file(candidate["path"])
                    self._reset_state()
                    return f"I found {candidate['filename']} on the drive. Opening it."
                except Exception as e:
                    self._reset_state()
                    return f"I found {candidate['filename']}, but couldn't open it: {e}"

            self.pending_candidates = results[:5]
            self.state = InteractionState.AWAITING_SELECTION
            
            response_lines = [f"I found {len(results)} files on the drive."]
            for idx, item in enumerate(self.pending_candidates, 1):
                response_lines.append(f"{idx}. {item['filename']}")
            response_lines.append("Which one should I open?")
            return "\n".join(response_lines)
            
        else:
            self._reset_state()
            return "Okay, search cancelled."

    def _parse_ordinal_or_number(self, text: str, num_candidates: int) -> Optional[int]:
        text_lower = text.strip().lower()
        
        # Word mappings
        mapping = {
            "first": 0, "1st": 0, "one": 0, "number one": 0,
            "second": 1, "2nd": 1, "two": 1, "number two": 1, "second one": 1,
            "third": 2, "3rd": 2, "three": 2, "number three": 2, "third one": 2,
            "fourth": 3, "4th": 3, "four": 3, "number four": 3,
            "fifth": 4, "5th": 4, "five": 4, "number five": 4,
            "last": num_candidates - 1, "last one": num_candidates - 1
        }
        
        if text_lower in mapping:
            val = mapping[text_lower]
            if 0 <= val < num_candidates:
                return val

        # Try to find digits
        match = re.search(r"\b\d+\b", text_lower)
        if match:
            val = int(match.group(0)) - 1
            if 0 <= val < num_candidates:
                return val

        return None

    def _reset_state(self):
        self.state = InteractionState.IDLE
        self.pending_candidates.clear()
        self.pending_query = ""
