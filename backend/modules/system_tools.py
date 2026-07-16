import os
import subprocess
import webbrowser
import logging
from pathlib import Path
import urllib.parse

logger = logging.getLogger("AION.SystemTools")

def get_desktop_path() -> str:
    """Returns the correct Desktop path, checking for OneDrive sync."""
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        return str(onedrive_desktop)
    return str(Path.home() / "Desktop")

def play_youtube_video(query: str) -> str:
    """
    Searches for a video on YouTube and opens it in the default browser.
    Use this when the user wants to play a song, watch a video, or search YouTube.
    
    Args:
        query: The name of the video, song, or topic to search for.
    """
    try:
        logger.info(f"Executing play_youtube_video for: {query}")
        # Use pywhatkit for instant video playing if possible, otherwise construct a search URL.
        # Since we might not have pywhatkit installed, we'll just open a YouTube search URL.
        # Actually, YouTube has a 'results?search_query=' which is very reliable.
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        webbrowser.open(url)
        return f"I have opened YouTube and searched for '{query}'."
    except Exception as e:
        logger.error(f"Error in play_youtube_video: {e}")
        return f"Failed to play YouTube video. Error: {e}"

def google_search(query: str) -> str:
    """
    Performs a Google search in the default web browser.
    
    Args:
        query: The search term or question.
    """
    try:
        logger.info(f"Executing google_search for: {query}")
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        webbrowser.open(url)
        return f"I have searched Google for '{query}'."
    except Exception as e:
        return f"Failed to search Google. Error: {e}"

def open_website(url: str) -> str:
    """
    Opens a specific URL or website in the default web browser.
    
    Args:
        url: The website URL (e.g., 'github.com', 'https://chat.openai.com').
    """
    try:
        logger.info(f"Executing open_website for: {url}")
        if not url.startswith('http'):
            url = 'https://' + url
        webbrowser.open(url)
        return f"I have opened the website {url}."
    except Exception as e:
        return f"Failed to open website. Error: {e}"

def create_code_file(filename: str, content: str, folder_path: str = "") -> str:
    """
    Creates a new file with the specified code or text content.
    Use this when the user asks you to write code, create a script, or make a text file.
    
    Args:
        filename: The name of the file (e.g., 'script.py', 'index.html').
        content: The full code or text content to write into the file.
        folder_path: The absolute path to the folder. If empty, saves to the user's Desktop.
    """
    try:
        # Validate folder_path — Ollama sometimes hallucinates fake paths
        # like "C:\Users\username\Desktop". If the path doesn't exist or
        # contains generic placeholders, fall back to the real Desktop.
        if not folder_path or not Path(folder_path).exists():
            folder_path = get_desktop_path()
            
        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)
        
        file_path = folder / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.info(f"Created file at: {file_path}")
        return f"I have successfully created the file {filename} at {folder_path}."
    except Exception as e:
        logger.error(f"Error creating file: {e}")
        return f"Failed to create the file. Error: {e}"

def open_vscode(folder_path: str = "") -> str:
    """
    Opens Visual Studio Code.
    
    Args:
        folder_path: The absolute path to the folder to open in VS Code. If empty, opens VS Code generically or in the Desktop.
    """
    try:
        if not folder_path:
            folder_path = get_desktop_path()
            
        logger.info(f"Opening VS Code in: {folder_path}")
        # Command 'code' opens VS Code
        subprocess.Popen(["code", folder_path], shell=True)
        return f"I have opened Visual Studio Code in {folder_path}."
    except Exception as e:
        logger.error(f"Error opening VS Code: {e}")
        return f"Failed to open VS Code. Make sure 'code' is in the system PATH. Error: {e}"

def open_application(app_name: str) -> str:
    """
    Attempts to open a standard Windows application by its common executable name.
    Use this when the user says "Open Notepad", "Open Calculator", etc.
    
    Args:
        app_name: The name of the application (e.g., 'notepad', 'calc', 'mspaint', 'explorer').
    """
    try:
        logger.info(f"Executing open_application for: {app_name}")
        # Sanitize app_name to prevent command injection
        import re
        sanitized_app = re.sub(r'[^a-zA-Z0-9_\-\.]', '', app_name)
        if not sanitized_app:
            return "Failed to launch application. Invalid name format."
            
        # Try running it via powershell Start-Process
        subprocess.Popen(["powershell.exe", "-Command", f"Start-Process {sanitized_app}"], shell=True)
        return f"I have launched {sanitized_app}."
    except Exception as e:
        return f"Failed to launch {app_name}. Error: {e}"

# Export the list of tools to pass to Gemini (automatic function calling)
aion_tools = [
    play_youtube_video,
    google_search,
    open_website,
    create_code_file,
    open_vscode,
    open_application
]

# Map of function name -> callable for Ollama tool execution
aion_tool_map = {
    "play_youtube_video": play_youtube_video,
    "google_search": google_search,
    "open_website": open_website,
    "create_code_file": create_code_file,
    "open_vscode": open_vscode,
    "open_application": open_application,
}

# Ollama-compatible tool definitions (JSON Schema format)
ollama_tool_definitions = [
    {
        "type": "function",
        "function": {
            "name": "play_youtube_video",
            "description": "Searches for a video on YouTube and opens it in the default browser. Use this when the user wants to play a song, watch a video, or search YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The name of the video, song, or topic to search for."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": "Performs a Google search in the default web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or question."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Opens a specific URL or website in the default web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The website URL (e.g., 'github.com', 'https://chat.openai.com')."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_code_file",
            "description": "Creates a new file with the specified code or text content. Use this when the user asks you to write code, create a script, or make a text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The name of the file (e.g., 'script.py', 'index.html')."
                    },
                    "content": {
                        "type": "string",
                        "description": "The full code or text content to write into the file."
                    },
                    "folder_path": {
                        "type": "string",
                        "description": "The absolute path to the folder. If empty, saves to the user's Desktop."
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_vscode",
            "description": "Opens Visual Studio Code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "The absolute path to the folder to open in VS Code. If empty, opens VS Code on the Desktop."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Attempts to open a standard Windows application by its common executable name. Use this when the user says 'Open Notepad', 'Open Calculator', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the application (e.g., 'notepad', 'calc', 'mspaint', 'explorer')."
                    }
                },
                "required": ["app_name"]
            }
        }
    }
]
