import pytest
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtCore import QByteArray
from src.utils.config import AppConfig

def test_config_start_url(tmp_path):
    ini_file = tmp_path / "config.ini"
    selectors_file = tmp_path / "selectors.json"
    
    config = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config.start_url == ""
    
    config.start_url = "https://example.com/login"
    config.save()
    
    config2 = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config2.start_url == "https://example.com/login"

def test_playwright_chromium_launchable():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        assert browser is not None
        page = browser.new_page()
        page.set_content("<html><body><h1>Test</h1></body></html>")
        h1_text = page.locator("h1").inner_text()
        assert h1_text == "Test"
        browser.close()
