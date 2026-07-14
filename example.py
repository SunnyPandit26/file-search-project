import time
import logging
from pathlib import Path
from src.modules.file_search import FileSearchManager

# Configure basic logging to see the background indexer actions
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    print("=" * 60)
    print("File Search & Open Assistant Module - Interactive Simulator")
    print("=" * 60)
    print("Starting FileSearchManager...")
    
    # Initialize the manager. It will read/generate config in ~/.file_search_config.json
    manager = FileSearchManager()
    
    # Start the background indexer thread
    manager.start()
    
    print("\nForce-running an initial index scan...")
    # Trigger an immediate scan on the current thread so we have files indexed for the demo
    manager.indexer.update_index()
    
    print("\nSystem ready! Type your voice commands. Type 'exit' to quit.")
    print("Try commands like:")
    print(" - 'Open resume'")
    print(" - 'Find my notes'")
    print(" - 'Search python'")
    print("-" * 60)

    try:
        while True:
            user_input = input("\nUser: ").strip()
            if not user_input or user_input.lower() == 'exit':
                break
            
            # 1. The assistant router/planner checks if this input matches a file search intent
            # or if we are already in the middle of a selection conversation flow.
            if manager.is_file_search_intent(user_input):
                # 2. Hand it over to the manager to get the speech response
                response = manager.handle_command(user_input)
                print(f"Assistant: {response}")
            else:
                # Other assistant modules handle this
                print("Assistant: (Intent not routed to File Search. Try saying 'Open ...' or 'Find ...')")
                
    finally:
        print("\nStopping background indexer...")
        # Make sure to call stop to cleanly shut down the background thread
        manager.stop()
        print("Goodbye!")

if __name__ == "__main__":
    main()
