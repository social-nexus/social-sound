from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "server" / "ai_web" / "app.js"


def test_local_model_catalog_renders_download_actions_without_license_gate():
    source = APP_JS.read_text(encoding="utf-8")
    render = source.split("function renderModels(){", 1)[1].split("async function runJob(", 1)[0]
    # Models that do not require acceptance (e.g. Apache-2.0 Qwen) must still
    # receive the download button; license acceptance is only conditional UI.
    assert 'if(!m.installed){' in render
    assert 'button.textContent=T("Baixar modelo")' in render
    assert 'button.onclick=()=>downloadModel(m)' in render
    assert 'if(m.requires_license_acceptance){' in render
    assert 'button.disabled=!!m.requires_license_acceptance' in render
    assert 'button.disabled=!check.checked' in render
    assert 'activate.textContent=active?T("Modelo ativo"):T("Ativar modelo")' in render and 'activate.onclick=()=>activateModel(m)' in render


def test_script_generation_instructions_follow_selected_duration():
    source = APP_JS.read_text(encoding="utf-8")
    assert 'durationLabel=$("duration").selectedOptions[0]?.textContent||duration' in source
    assert 'const durationSeconds=duration==="60-70"?65' in source
    assert 'const characterLimit=Math.max(100,Math.round(durationSeconds*20))' in source
    assert 'approximately "+durationLabel' in source
    assert 'no máximo "+characterLimit.toLocaleString("pt-BR")+" caracteres' in source


def test_local_model_removal_preserves_runtime_and_other_models():
    source = APP_JS.read_text(encoding="utf-8")
    assert 'remove.textContent=T("Desinstalar e excluir")' in source
    assert 'Os pesos deste modelo serão removidos' in source
    assert 'O llama.cpp instalado, os outros modelos' in source
    assert 'm.size_bytes' in source
    assert 'result.removed_bytes' in source
    assert 'Espaço liberado:' in source


def test_cloud_provider_key_can_be_removed_from_script_and_prompt_workspaces():
    app = APP_JS.read_text(encoding="utf-8")
    scripts = (APP_JS.parents[1] / "ia-roteiros" / "index.html").read_text(encoding="utf-8")
    prompts = (APP_JS.parents[1] / "ia-prompts" / "index.html").read_text(encoding="utf-8")
    assert 'async function removeProviderKey()' in app
    assert '$("remove-key").onclick=removeProviderKey' in app
    assert 'providersApi+"/key/"+encodeURIComponent(provider)' in app
    assert 'id="remove-key"' in scripts
    assert 'id="remove-key"' in prompts


def test_model_delete_confirmation_matches_generation_conflict_behavior():
    source = APP_JS.read_text(encoding="utf-8")
    assert "a exclusão será bloqueada" in source
    assert "você precisará tentar novamente quando terminar" in source


def test_ai_workspace_supports_english_static_and_dynamic_ui():
    source = APP_JS.read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in source
    assert source.index("const UI_LANG=") < source.index("const providerNames=")
    assert '"AI — Scripts & Narration"' in source
    assert 'applyAIEnglish();' in source
    assert 'T("Baixar modelo")' in source
    assert 'T("Desinstalar e excluir")' in source
    assert 'T("Gerando…")' in source
    assert 'T("Geração concluída usando ")' in source
    assert 'T("Texto copiado para a área de transferência.")' in source
    assert 'T("Roteiro enviado para a área de Narração. Abra a aba Narração no menu lateral.")' in source
    assert 'T("Local AI (llama.cpp)")' in source or 'UI_LANG==="en"?"Local AI (llama.cpp)"' in source


def test_ai_workspaces_have_visible_language_selector():
    source = APP_JS.read_text(encoding="utf-8")
    assert "function addAILanguageSelector()" in source
    assert 'select.id="ai-ui-language"' in source
    assert 'url.searchParams.set("lang","en")' in source


def test_narration_react_page_has_visible_language_selector():
    app = (Path(__file__).resolve().parents[1] / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'id="ui-language"' in app
    assert 'value={UI_LANG}' in app
    assert 'url.searchParams.set("lang","en")' in app
    assert 'option value="pt-BR">Português' in app
    assert 'option value="en">English' in app


def test_narration_queue_static_ui_localizes_to_english():
    source = (Path(__file__).resolve().parents[1] / "server" / "narracoes" / "app.js").read_text(encoding="utf-8")
    assert 'get("lang")==="en"' in source
    assert "function applyStaticEnglish()" in source
    assert '"Divisão Inteligente de Narrações":"Smart Narration Splitter"' in source
    assert "applyStaticEnglish();" in source\n    assert 'T("Fila ativa")' in source\n    assert 'T("Pausar após a atual")' in source\n    assert 'T("Adicionada à fila.")' in source\n    assert 'T("Motores com uso comercial permitido")' in source\n    assert 'T("Liberar pesos baixados")' in source\n    assert 'T("Desinstalar e excluir")' in source
