import sys
import logging
from src.modules.file_search import FileSearchManager

# Keep console output clean
logging.basicConfig(level=logging.WARNING)

def main():
    if len(sys.argv) < 2:
        print("Usage: python search.py <query_here>")
        print("Example: python search.py resume")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    manager = FileSearchManager()
    
    # Check if index is empty. If it is, run the initial scan
    indexed_files = manager.indexer.get_all_files()
    if not indexed_files:
        print("First-time setup: Indexing your files (Desktop, Documents, Downloads, Pictures, etc.)...")
        manager.indexer.update_index()
        print("Indexing completed.\n")
        
    # Run search query
    response = manager.handle_command(query)
    print(response)
    
    # Handle multi-turn selection flow (e.g. if multiple matches found, or drive fallback)
    try:
        while manager.intent_handler.state != manager.intent_handler.state.IDLE:
            user_reply = input("\nAnswer: ").strip()
            response = manager.handle_command(user_reply)
            print(response)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")

if __name__ == "__main__":
    main()
