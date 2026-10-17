import json
import subprocess


def game_focused():
    """
    ask Hyprl which window has focus True if its Hotline Miami
    """
    try:
        out = subprocess.run(
            ["hyprctl", "activewindow", "-j"], capture_output=True, text=True
        ).stdout
        window = json.loads(out)
    except (OSError, ValueError):
        return False
    name = f"{window.get('class', '')} {window.get('title', '')}".lower()
    return "hotline" in name or "219150" in name  # 219150 = the game's Steam id
