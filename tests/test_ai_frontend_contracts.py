from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "server" / "ai_web" / "app.js"


def test_local_model_catalog_renders_download_actions_without_license_gate():
    source = APP_JS.read_text(encoding="utf-8")
    render = source.split("function renderModels(){", 1)[1].split("async function runJob(", 1)[0]
    # Models that do not require acceptance (e.g. Apache-2.0 Qwen) must still
    # receive the download button; license acceptance is only conditional UI.
    assert 'if(!m.installed){' in render
    assert 'button.textContent="Baixar modelo"' in render
    assert 'button.onclick=()=>downloadModel(m)' in render
    assert 'if(m.requires_license_acceptance){' in render
    assert 'button.disabled=!!m.requires_license_acceptance' in render
    assert 'button.disabled=!check.checked' in render
    assert 'activate.textContent=active?"Modelo ativo":"Ativar modelo"' in render and 'activate.onclick=()=>activateModel(m)' in render


def test_script_generation_instructions_follow_selected_duration():
    source = APP_JS.read_text(encoding="utf-8")
    assert 'durationLabel=$("duration").selectedOptions[0]?.textContent||duration' in source
    assert 'const durationSeconds=duration==="60-70"?65' in source
    assert 'const characterLimit=Math.max(100,Math.round(durationSeconds*20))' in source
    assert 'approximately "+durationLabel' in source
    assert 'no máximo "+characterLimit.toLocaleString("pt-BR")+" caracteres' in source
