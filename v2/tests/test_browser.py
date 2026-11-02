from src.utils.config import AppConfig

def test_config_start_url(tmp_path):
    ini_file = tmp_path / "config.ini"
    selectors_file = tmp_path / "selectors.json"
    
    config = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config.start_url == "http://10.200.5.191/"
    
    config.start_url = "http://example.com/login"
    config.save()
    
    config2 = AppConfig(config_path=str(ini_file), selectors_path=str(selectors_file))
    assert config2.start_url == "http://example.com/login"
