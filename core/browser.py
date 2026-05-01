import json
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


def load_config(path="config.json"):
    """Загружает config.json из корня проекта."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


import json
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


import json
import os
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service


def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_driver(cfg):
    # Определяем путь к проекту
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, ".."))
    gecko_path = os.path.join(project_root, "drivers", "geckodriver.exe")

    options = Options()
    options.binary_location = cfg["firefox_binary"]
    options.set_preference("profile", cfg["firefox_profile"])

    service = Service(executable_path=gecko_path)

    driver = webdriver.Firefox(
        service=service,
        options=options
    )

    driver.set_window_size(
        cfg.get("window_width", 1200),
        cfg.get("window_height", 800)
    )

    return driver
