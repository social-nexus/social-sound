from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "server" / "narration_api.py"
PAGE = ROOT / "server" / "motores" / "index.html"


def test_optional_engine_install_api_is_allowlisted_and_license_gated():
    source = API.read_text(encoding="utf-8")
    assert 'router.post("/engines/{engine_id}/install")' in source
    assert 'engine_id not in {"supertonic3", "omnivoice", "f5tts"}' in source
    assert 'if not accepted:' in source
    assert 'payload.get("license_accepted") is True' in source
    assert 'payload.get("non_commercial_ack") is not True' in source
    assert 'engine_id in {"omnivoice", "f5tts"}' in source
    assert 'if not engine_install_lock.acquire(blocking=False)' in source
    assert 'router.get("/engines/install/{job_id}")' in source
    assert "import queue" in source  # installer output reader uses queue.Queue()


def test_engine_catalog_ui_calls_install_api_and_requires_acknowledgments():
    source = PAGE.read_text(encoding="utf-8")
    assert '"/api/narration/"+' not in source
    assert '"/api/narration/engines/"+id+"/install"' in source
    assert 'license_accepted:license' in source
    assert 'non_commercial_ack:nc' in source
    assert "poll(res.job_id,id,card)" in source
    assert "Instalação iniciada" in source


def test_optional_engine_bat_scripts_support_noninteractive_ui_install():
    for name in ("instalar-supertonic.bat", "instalar-omnivoice.bat", "instalar-f5tts.bat"):
        script = (ROOT / name).read_text(encoding="utf-8")
        assert "SOCIAL_SOUND_INSTALL_FROM_UI" in script
    for name in ("instalar-omnivoice.bat", "instalar-f5tts.bat"):
        script = (ROOT / name).read_text(encoding="utf-8")
        assert "SOCIAL_SOUND_LICENSE_ACCEPTED" in script


def test_engine_catalog_ui_shows_optional_tokenizer_license_link():
    source = (ROOT / "server" / "motores" / "index.html").read_text(encoding="utf-8")
    assert "e.tokenizer_url" in source
    assert "Licença tokenizer" in source


def test_engine_install_api_releases_lock_when_thread_start_fails():
    source = (ROOT / "server" / "narration_api.py").read_text(encoding="utf-8")
    assert "installer_thread.start()" in source
    assert "engine_install_lock.release()" in source
    assert "Não foi possível iniciar o processo de instalação." in source


def test_narration_queue_catalog_shows_optional_tokenizer_license_link():
    source = (ROOT / "server" / "narracoes" / "app.js").read_text(encoding="utf-8")
    assert "e.tokenizer_url" in source
    assert "Licença tokenizer" in source


def test_optional_voice_engines_have_safe_uninstall_controls():
    api = API.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    assert 'router.delete("/engines/{engine_id}")' in api
    assert 'engine_install_lock.acquire(blocking=False)' in api
    assert 'inference_guard.acquire(blocking=False)' in api
    assert 'job.get("status") in {"queued", "processing"}' in api
    assert 'delete_shared_cache' in api
    assert 'engine_uninstalling_guard' in api
    assert 'engine_uninstalling.add(engine_id)' in api
    assert 'models--k2-fsa--OmniVoice' in api
    assert 'models--Cataldir--F5-TTS-pt-br' in api
    assert 'removable=installable||e.id==="voxcpm2"' in page
    assert 'e.id==="voxcpm2"?T("Liberar pesos baixados"):T("Desinstalar e excluir")' in page
    assert 'startUninstall' in page
    assert 'Pode afetar outros aplicativos' in page or 'outros aplicativos' in page


def test_narration_workspace_also_exposes_optional_engine_uninstall():
    source = (ROOT / "server" / "narracoes" / "app.js").read_text(encoding="utf-8")
    assert "data-uninstall-engine=\"'+esc(e.id)+'\"" in source
    assert '"voxcpm2"].includes(e.id)' in source
    assert 'async function uninstallEngine(id)' in source
    assert 'API+"/engines/"+id' in source
    assert 'delete_shared_cache:deleteShared' in source


def test_voxcpm2_weight_cleanup_is_available_in_both_voice_workspaces():
    motor = (ROOT / "server" / "motores" / "index.html").read_text(encoding="utf-8")
    narration = (ROOT / "server" / "narracoes" / "app.js").read_text(encoding="utf-8")
    assert 'Liberar pesos baixados' in motor
    assert 'Liberar pesos baixados' in narration
    assert 'O motor continuará integrado' in narration
    assert 'O motor continuará integrado' not in motor or 'Descarregar o VoxCPM2' in motor


def test_voice_engine_catalog_supports_english_ui_and_dynamic_labels():
    page = PAGE.read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in page
    assert '"Voice Engines"' in page
    assert 'T("Liberar pesos baixados")' in page
    assert 'T("Desinstalar e excluir")' in page
    assert 'T("Confirmo explicitamente que o uso será não comercial.")' in page


def test_voice_engine_page_has_language_selector():
    page = PAGE.read_text(encoding="utf-8")
    assert "function addEngineLanguageSelector()" in page
    assert 'select.id="engine-ui-language"' in page
