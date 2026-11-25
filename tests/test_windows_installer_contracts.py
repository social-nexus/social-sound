from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_installer(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_main_installer_checks_virtual_environment_and_core_dependencies():
    installer = read_installer("instalar.bat")
    assert 'if not exist ".venv\\Scripts\\python.exe" goto sem_python' in installer
    assert "python -m pip install --upgrade pip\nif errorlevel 1 goto falha" in installer
    assert (
        'pip install voxcpm fastapi "uvicorn[standard]" python-multipart '
        'soundfile httpx "keyring>=25.5,<26"\n'
        "if errorlevel 1 goto falha\npip check\nif errorlevel 1 goto falha"
    ) in installer


def test_optional_voice_engines_use_isolated_python_environments():
    expected = {
        "instalar-f5tts.bat": ".venvs\\f5tts",
        "instalar-omnivoice.bat": ".venvs\\omnivoice",
        "instalar-supertonic.bat": ".venvs\\supertonic",
    }
    for filename, environment in expected.items():
        installer = read_installer(filename)
        assert environment in installer
        assert "py -3.11 -m venv" in installer
        assert "-m pip check" in installer
        assert "if errorlevel 1 goto falha" in installer


def test_f5_installer_keeps_pytorch_and_torchcodec_versions_aligned():
    installer = read_installer("instalar-f5tts.bat")
    torch_install = installer.index('"torch==2.8.0" "torchaudio==2.8.0"')
    codec_install = installer.index('"torchcodec==0.7.0"')
    f5_install = installer.index('"f5-tts==1.1.22"')
    assert torch_install < codec_install < f5_install
    assert "assert m.version('torchcodec') == '0.7.0'" in installer


def test_noncommercial_engines_require_explicit_license_confirmation():
    for filename in ("instalar-f5tts.bat", "instalar-omnivoice.bat"):
        installer = read_installer(filename)
        confirmation = installer.index("set /p ")
        download = installer.index("--download")
        assert confirmation < download
        assert 'if /i not "%CONFIRM%"=="S"' in installer
