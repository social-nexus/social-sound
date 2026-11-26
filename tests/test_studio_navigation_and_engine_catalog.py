from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "server" / "estudio" / "index.html"
ENGINES_PAGE = ROOT / "server" / "motores" / "index.html"
SERVER = ROOT / "server" / "server.py"


def test_studio_has_separate_voice_engine_and_ai_configuration_tabs():
    html = STUDIO.read_text(encoding="utf-8")
    assert 'id="t-motores"' in html
    assert 'onclick="show(\'motores\')"' in html
    assert 'id="p-motores"' in html
    assert 'url:"/motores/"' in html
    assert 'id="t-ia-config"' in html
    assert 'url:"/ia-roteiros/"' in html
    assert "Inteligência Artificial" in html
    assert "Produção" in html
    assert "</nav>><div" not in html


def test_voice_engines_page_displays_catalog_and_size_estimates():
    html = ENGINES_PAGE.read_text(encoding="utf-8")
    assert "/api/narration/engines" in html
    assert "download_estimate" in html
    assert "disk_estimate" in html
    assert "em segundo plano" in html


def test_voice_engines_page_is_mounted_by_server():
    source = SERVER.read_text(encoding="utf-8")
    assert 'app.mount("/motores"' in source


def test_main_studio_language_selector_persists_and_translates_shell():
    html = STUDIO.read_text(encoding="utf-8")
    assert 'id="app-language"' in html
    assert 'value="en">English' in html
    assert 'localStorage.setItem("social-sound-language",APP_LANG)' in html
    assert 'localStorage.getItem("social-sound-language")' in html
    assert '"Script / Humanization"' in html
    assert '"Narration Queue"' in html
    assert '"AI Settings"' in html
    assert 'encodeURIComponent(APP_LANG)' in html
    assert 'lang="en"' in html or 'document.documentElement.lang=APP_LANG==="en"?"en":"pt-BR"' in html
