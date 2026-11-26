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


def test_script_humanization_page_supports_english_static_ui():
    page = ROOT / "server" / "roteiro_web" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert 'new URLSearchParams(location.search).get("lang") === "en"' in html
    assert '"Prepare script":"Prepare script"' not in html
    assert '"Your script"' in html
    assert '"Humanize"' in html
    assert 'applyScriptEnglish();' in html
    assert 'document.documentElement.lang="en"' in html


def test_narration_queue_has_english_dynamic_translation():
    app = ROOT / "server" / "narracoes" / "app.js"
    js = app.read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in js
    assert '"Queued"' in js
    assert '"Approve and replace"' in js
    assert '"Elapsed time: "' in js
    assert 'labels=UI_LANG==="en"?' in js
    assert 'Regenerate this part' in js
    assert 'esc(part.text)' in js
    assert 'T("Nenhuma narração na fila ainda.")' in js


def test_dialogue_page_supports_english_interface():
    page = ROOT / "server" / "dialogo_web" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in html
    assert '"Multi-voice dialogue"' in html
    assert '"Generate dialogue"' in html
    assert 'applyDialogueEnglish();' in html
    assert 'UI_LANG==="en"?"Generating...":"Gerando..."' in html
    assert 'if(UI_LANG==="en")TONS.forEach' in html
    assert 'relogio = setInterval(function ()' in html
    assert 'mmss((Date.now() - inicio) / 1000)' in html

def test_narration_queue_translation_does_not_mutate_user_script_text():
    app = ROOT / "server" / "narracoes" / "app.js"
    js = app.read_text(encoding="utf-8")
    assert "Regenerate this part" in js
    assert "Approve and replace" in js
    assert "esc(part.text)" in js
    assert 'Object.keys(UI_STR.en).reduce((html,pt)' not in js

def test_main_narration_page_supports_english_ui():
    app = ROOT / "web" / "src" / "App.tsx"
    source = app.read_text(encoding="utf-8")
    assert 'get("lang") === "en"' in source
    assert 'T("Narração e clonagem de voz")' in source
    assert 'T("Clonar minha voz")' in source
    assert "T('GERAR ÁUDIO')" in source
    assert 'T("Gerar legenda SRT junto com o áudio")' in source


def test_voice_studio_is_integrated_into_main_navigation_and_mounted():
    html = STUDIO.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    page = ROOT / "server" / "estudio_voz" / "index.html"
    voice_html = page.read_text(encoding="utf-8")
    assert 'id="t-estudio-voz"' in html
    assert 'onclick="show(\'estudio-voz\')"' in html
    assert 'url:"/estudio-voz/"' in html
    assert 'app.mount("/estudio-voz"' in server
    assert "getUserMedia" in voice_html
    assert "PREPARAR E SALVAR VOZ" in voice_html
    assert "Biblioteca de vozes" in voice_html
    assert "TRANSCREVER AUTOMATICAMENTE" in voice_html
    assert "PREPARAÇÃO DE ÁUDIO" in voice_html
    assert "view.setUint8(offset+i,str.charCodeAt(i));" in voice_html
    assert "function wavBlob(samples,sr)" in voice_html


def test_subtitle_workspace_supports_english_ui():
    page = ROOT / "server" / "legenda_web" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in html
    assert '"Subtitles & timestamps"' in html
    assert '"Word-by-word subtitles (.srt)"' in html
    assert '"Generate subtitles"' in html
    assert 'applyCaptionEnglish();' in html
    assert 'UI_LANG==="en" ? (w?' in html
    assert 'UI_LANG==="en" ? (f==="palavras"' in html
