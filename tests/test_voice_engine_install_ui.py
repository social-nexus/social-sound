from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "server" / "narration_api.py"
PAGE = ROOT / "server" / "motores" / "index.html"


def test_optional_engine_install_api_is_allowlisted_and_license_gated():
    source = API.read_text(encoding="utf-8")
    assert 'router.post("/engines/{engine_id}/install")' in source
    assert 'engine_id not in {"supertonic3", "omnivoice", "f5tts"}' in source
    assert 'if not accepted:' in source
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
