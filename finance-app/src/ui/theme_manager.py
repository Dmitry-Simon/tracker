import os
import toml

CONFIG_PATH = ".streamlit/config.toml"

LIGHT_THEME = {
    "base": "light",
    "primaryColor": "#FF4B4B",
    "backgroundColor": "#FFFFFF",
    "secondaryBackgroundColor": "#F0F2F6",
    "textColor": "#262730",
    "font": "sans serif"
}

DARK_THEME = {
    "base": "dark",
    "primaryColor": "#FF4B4B", 
    "font": "sans serif"
}

def get_current_theme():
    """Returns 'light' or 'dark' based on config.toml"""
    if not os.path.exists(CONFIG_PATH):
        return "light"
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = toml.load(f)
            return config.get("theme", {}).get("base", "light")
    except Exception:
        return "light"

def toggle_theme():
    """
    Switches config.toml between Light (custom colors) and Dark (native).
    Returns the new theme name.
    """
    current = get_current_theme()
    new_theme_key = "dark" if current == "light" else "light"
    new_theme_settings = DARK_THEME if new_theme_key == "dark" else LIGHT_THEME
    
    # Read existing config to preserve other sections like [server]
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = toml.load(f)
        except Exception:
            pass
    
    # Update [theme] section
    config["theme"] = new_theme_settings
    
    # Write back
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        toml.dump(config, f)
        
    return new_theme_key
