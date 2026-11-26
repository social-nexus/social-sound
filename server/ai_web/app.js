(() => {
const $=id=>document.getElementById(id);
const api="/api/ai",providersApi="/api/ai/providers";
const workspace=document.body.dataset.workspace;
const UI_LANG=new URLSearchParams(location.search).get("lang")==="en"?"en":"pt-BR";
const providerNames={local:UI_LANG==="en"?"Local AI (llama.cpp)":"IA local (llama.cpp)",openai:"OpenAI",anthropic:"Anthropic Claude",gemini:"Google Gemini",openrouter:"OpenRouter",deepseek:"DeepSeek",groq:"Groq",mistral:"Mistral AI"};
const AI_EN={
"IA — Roteiros e Narração":"AI — Scripts & Narration","Crie, revise, adapte e prepare textos para narrar.":"Create, revise, adapt and prepare scripts for narration.",
"Preparação do roteiro":"Script preparation","Tema ou título (opcional)":"Topic or title (optional)","Tema principal do vídeo":"Main video topic",
"Formato":"Format","Shorts / Reels / TikTok":"Shorts / Reels / TikTok","Vídeo longo":"Long video","Formato livre":"Flexible format",
"Duração":"Duration","60–70 segundos":"60–70 seconds","30 segundos":"30 seconds","90 segundos":"90 seconds","3 minutos":"3 minutes","5 minutos":"5 minutes","10 minutos":"10 minutes","15 minutos":"15 minutes",
"Tom e estilo":"Tone and style","Natural, humano e envolvente":"Natural, human and engaging","Comédia":"Comedy","Documentário sério":"Serious documentary","Emocionante e reflexivo":"Emotional and reflective","Educativo e didático":"Educational and instructional","Suspense":"Suspense","Marketing e vendas":"Marketing and sales","Personalizado":"Custom",
"Público":"Audience","Texto base, ideia ou informações que devem ser mantidas":"Base text, idea or information to retain","Cole o texto, rascunho, tópicos ou contexto do roteiro.":"Paste the text, draft, bullet points or script context.","Instruções extras":"Extra instructions",
"Gerar com IA":"Generate with AI","Resultado do roteiro":"Script result","O roteiro gerado aparecerá aqui. Você pode editar antes de enviar para narração.":"The generated script will appear here. You can edit it before sending to narration.",
"Copiar":"Copy","Salvar TXT":"Save TXT","Enviar para Narração":"Send to Narration",
"Provedor de IA":"AI Provider","IA selecionada":"Selected AI","Modelo API":"API model","Digite ou escolha o identificador do modelo":"Type or select the model ID",
"Chave API (se for cadastrar ou atualizar)":"API key (when adding or updating)","Cole sua chave API":"Paste your API key",
"Salvar chave segura":"Save secure key","Testar conexão":"Test connection","Remover chave salva":"Remove saved key","Salvar provedor/modelo":"Save provider/model",
"Chaves API ficam no cofre de credenciais do sistema operacional, não no arquivo de configuração.":"API keys are stored in the operating system credential vault, not in the configuration file.",
"IA local — Modelos e Runtime":"Local AI — Models & Runtime","Consultando estado do gerenciador local…":"Checking local manager status…",
"Runtime compatível com seu sistema":"Runtime compatible with your system","Instalar llama.cpp":"Install llama.cpp","Atualizar estado":"Refresh status",
"Camadas de modelo na GPU (0 = CPU)":"GPU model layers (0 = CPU)","Se a GPU tiver pouca VRAM, comece com 0 (CPU) e aumente gradualmente. O modelo Qwen 4B quantizado é uma opção relativamente compacta.":"If your GPU has limited VRAM, start at 0 (CPU) and increase gradually. Quantized Qwen 4B is a relatively compact option.",
"Importar modelo GGUF (opcional)":"Import GGUF model (optional)","Importar GGUF":"Import GGUF","Catálogo e modelos instalados":"Catalog and installed models",
"Ex.: público geral, crianças, fãs de histórias…":"e.g. general audience, children, story fans…","Ex.: curiosidades sobre o espaço, história bíblica, humor cotidiano…":"e.g. space facts, biblical history, everyday comedy…",
"Modelo importado":"Imported model","Licença: ":"License: ","Espaço ocupado: ":"Space used: ","Peso estimado do arquivo: ":"Estimated file size: ","Espaço livre recomendado: ":"Recommended free space: ","não estimado":"not estimated",
"Li e aceito os termos de licença":"I have read and accept the license terms","Abrir licença":"Open license","Baixar modelo":"Download model","Modelo ativo":"Model active","Ativar modelo":"Activate model","Desinstalar e excluir":"Uninstall and delete",
"Gerando…":"Generating…","Enviando pedido para ":"Sending request to ","Geração concluída usando ":"Generation completed using ","Informe um tema ou cole um texto base antes de gerar.":"Enter a topic or paste base text before generating.",
"Cole um roteiro, ideia ou descrição de cena antes de gerar.":"Paste a script, idea or scene description before generating.","Selecione ou digite o modelo API.":"Select or enter the API model.",
"Modelos locais disponíveis após baixar e ativar um modelo GGUF.":"Local models are available after downloading and activating a GGUF model.",
"Uma chave já está salva no cofre seguro. Para substituir, digite uma nova chave.":"A key is already saved in the secure vault. Enter a new key to replace it.",
"A chave será salva no cofre de credenciais do sistema, não em arquivo.":"The key will be saved in the system credential vault, not in a file.",
"Sugestões: ":"Suggestions: "," (também pode digitar outro modelo suportado).":" (you can also type another supported model).",
"Ative um modelo local antes de testar.":"Activate a local model before testing.","Teste local: ":"Local test: ","Teste concluído: ":"Test completed: ",
"Uma chave já está salva":"A key is already saved","Chave removida do cofre seguro. Nenhuma conta ou dado do provedor foi excluído.":"Key removed from the secure vault. No provider account or data was deleted.",
"Runtime ativo · modelo ":"Runtime active · model "," · variante ":" · variant ","Runtime instalado, não está ativo.":"Runtime installed but inactive.","Runtime llama.cpp ainda não instalado.":"llama.cpp runtime is not installed yet.",
"Runtime ativo — será desligado ao desinstalar.":"Runtime active — will be stopped during uninstall.","Runtime instalado.":"Runtime installed.",
"Desinstalar runtime e excluir arquivos":"Uninstall runtime and delete files","Nenhum runtime compatível encontrado":"No compatible runtime found",
"Nenhum modelo no catálogo. Verifique a conexão com o gerenciador de IA.":"No models in catalog. Check the connection to the AI manager.",
"Importar modelo GGUF":"Import GGUF model","Modelo importado: ":"Model imported: ","Importando modelo GGUF…":"Importing GGUF model…",
"Escolha um arquivo .gguf para importar.":"Choose a .gguf file to import.","Importar este arquivo GGUF? A licença do modelo não será verificada automaticamente.":"Import this GGUF file? The model license will not be checked automatically.",
"Desinstalar runtime ":"Uninstall runtime "," e excluir seus arquivos baixados?":" and delete its downloaded files?"," O runtime ativo será desligado antes da remoção.":" The active runtime will be stopped before removal.",
"Runtime removido. Espaço liberado: ":"Runtime removed. Space freed: "," GB.":" GB.",
"Desinstalar e excluir ":"Uninstall and delete ","? Os pesos deste modelo serão removidos. Se ele estiver ativo, será desligado antes da exclusão. Se houver uma geração em andamento, a exclusão será bloqueada e você precisará tentar novamente quando terminar. O llama.cpp instalado, os outros modelos, seus roteiros e projetos serão preservados.":"? The model weights will be removed. If active, it will be stopped first. Deletion is blocked during generation. Installed llama.cpp, other models, scripts and projects will be preserved.",
"Modelo ":"Model "," removido. Espaço liberado: ":" removed. Space freed: "," O llama.cpp instalado e os demais modelos foram preservados.":" Installed llama.cpp and other models were preserved.",
"Não consegui consultar o gerenciador de IA: ":"Could not query the AI manager: ","A tarefa começou. Aguarde…":"Task started. Please wait…","A tarefa falhou.":"The task failed.",
"Gerar com IA":"Generate with AI","Gerar diálogo":"Generate dialogue","Gerar roteiro":"Generate script",
"Informe o nome do modelo para o provedor selecionado.":"Enter a model name for the selected provider.","Configuração salva. Provedor atual: ":"Configuration saved. Current provider: ","Selecione um provedor externo e informe a chave API.":"Select an external provider and enter an API key.","Chave salva no cofre de credenciais do sistema.":"Key saved in the system credential vault.","Selecione um runtime compatível.":"Select a compatible runtime.","Instale e selecione um runtime compatível.":"Install and select a compatible runtime.","Inicializando modelo. Isso pode levar alguns minutos…":"Initializing model. This may take a few minutes…","Modelo local ativado: ":"Local model activated: ","Geração concluída usando ":"Generation completed using ","Texto copiado para a área de transferência.":"Text copied to clipboard.","Texto copiado.":"Text copied.","Gere ou escreva o roteiro antes de enviar.":"Generate or write a script before sending.","Roteiro enviado para a área de Narração. Abra a aba Narração no menu lateral.":"Script sent to Narration. Open the Narration tab in the side menu.","Não consegui enviar o texto para a Narração.":"Could not send the text to Narration.",
"Não foi possível iniciar a tarefa: ":"Could not start task: ","Runtime já instalado.":"Runtime already installed.",
"Baixando runtime oficial llama.cpp…":"Downloading official llama.cpp runtime…",
"Verificando SHA-256 do pacote ":"Verifying SHA-256 of package "," do runtime…":" of the runtime…",
"Runtime instalado e verificado.":"Runtime installed and verified.",
"Consultando hash e tamanho no Hugging Face…":"Checking hash and size on Hugging Face…",
"Modelo já instalado e verificado.":"Model already installed and verified.",
"Validando SHA-256 do modelo…":"Validating model SHA-256…",
"Modelo baixado e verificado.":"Model downloaded and verified."
};
const T=value=>UI_LANG==="en"?(AI_EN[value]||value):value;
function applyAIEnglish(){
if(UI_LANG!=="en")return;
document.documentElement.lang="en";
const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
let node;while((node=walker.nextNode())){const key=node.nodeValue.trim();if(AI_EN[key])node.nodeValue=node.nodeValue.replace(key,AI_EN[key]);}
document.querySelectorAll("option").forEach(o=>{const key=o.textContent.trim();if(AI_EN[key])o.textContent=AI_EN[key];});
document.querySelectorAll("[placeholder]").forEach(el=>{const key=el.placeholder.trim();if(AI_EN[key])el.placeholder=AI_EN[key];});
}
function addAILanguageSelector(){
 const header=document.querySelector("header");if(!header||header.querySelector("#ai-ui-language"))return;
 const box=document.createElement("div");box.style.cssText="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin:8px 0";
 const label=document.createElement("label");label.htmlFor="ai-ui-language";label.textContent=UI_LANG==="en"?"Language":"Idioma";
 const select=document.createElement("select");select.id="ai-ui-language";select.style.cssText="background:#101827;color:inherit;border:1px solid #354156;border-radius:8px;padding:6px 10px";
 for(const [value,text] of [["pt-BR","Português"],["en","English"]]){const o=document.createElement("option");o.value=value;o.textContent=text;select.appendChild(o);}
 select.value=UI_LANG;select.addEventListener("change",()=>{const url=new URL(location.href);if(select.value==="en")url.searchParams.set("lang","en");else url.searchParams.delete("lang");location.href=url.toString();});
 box.append(label,select);header.appendChild(box);
}
addAILanguageSelector();
applyAIEnglish();

let cfg=null,catalog=null,aiStatus=null,selectedProvider="local",modelChoices=[],pollTimer=null;
const msg=(id,text,type="")=>{const el=$(id);if(!el)return;el.className="status "+type;el.textContent=text;};
async function apiFetch(url,opts={}){const res=await fetch(url,opts);let data={};try{data=await res.json()}catch{}if(!res.ok)throw new Error(data.detail||data.message||"Falha na solicitação.");return data;}
function json(method,body){return {method,headers:{"Content-Type":"application/json"},body:JSON.stringify(body)};}
function providerName(id){return providerNames[id]||id;}
function currentModel(){return $("provider-model")?.value.trim()||"";}
async function loadConfig(){cfg=await apiFetch(providersApi+"/config");selectedProvider=cfg.selected_provider||"local";const select=$("provider");select.innerHTML='<option value="local">'+T("IA local (llama.cpp)")+'</option>'+cfg.providers.map(p=>'<option value="'+p.id+'">'+p.name+'</option>').join("");select.value=selectedProvider;modelChoices=cfg.providers;refreshProviderFields();if(cfg.selected_model)$("provider-model").value=cfg.selected_model;else if(selectedProvider!=="local")$("provider-model").value=(cfg.providers.find(p=>p.id===selectedProvider)?.models||[])[0]||"";}
function refreshProviderFields(){selectedProvider=$("provider").value;const external=selectedProvider!=="local";$("api-model-wrap").classList.toggle("hidden",!external);$("api-key-wrap").classList.toggle("hidden",!external);$("api-buttons").classList.toggle("hidden",!external);const p=cfg?.providers?.find(x=>x.id===selectedProvider);$("remove-key").classList.toggle("hidden",!p||!p.configured);if(p){if(!$("provider-model").value||selectedProvider!==cfg.selected_provider)$("provider-model").value=p.models[0]||"";$("model-help").textContent=T("Sugestões: ")+p.models.join(", ")+T(" (também pode digitar outro modelo suportado).");$("key-help").textContent=p.configured?T("Uma chave já está salva no cofre seguro. Para substituir, digite uma nova chave."):T("A chave será salva no cofre de credenciais do sistema, não em arquivo."); }else{$("provider-model").value="";$("model-help").textContent=T("Modelos locais disponíveis após baixar e ativar um modelo GGUF.");}}
async function saveProvider(){const provider=$("provider").value;const model=$("provider-model").value.trim();if(provider!=="local"&&!model){msg("provider-msg",T("Informe o nome do modelo para o provedor selecionado."),"warn");return false;}try{cfg=await apiFetch(providersApi+"/config",json("PUT",{provider,model}));msg("provider-msg",T("Configuração salva. Provedor atual: ")+providerName(provider)+".","good");return true;}catch(e){msg("provider-msg",e.message,"error");return false;}}
async function saveKey(){const provider=$("provider").value,key=$("api-key").value.trim();if(provider==="local"||!key){msg("provider-msg",T("Selecione um provedor externo e informe a chave API."),"warn");return;}try{await apiFetch(providersApi+"/key",json("POST",{provider,api_key:key}));$("api-key").value="";cfg=await apiFetch(providersApi+"/config");refreshProviderFields();msg("provider-msg",T("Chave salva no cofre de credenciais do sistema."),"good");}catch(e){msg("provider-msg",e.message,"error");}}
async function removeProviderKey(){const provider=$("provider").value;if(provider==="local")return;if(!confirm(T("Remover a chave salva de ")+providerName(provider)+T(" do cofre seguro deste computador? Isso não cancela a conta nem apaga nada no site do provedor.")))return;try{await apiFetch(providersApi+"/key/"+encodeURIComponent(provider),{method:"DELETE"});if(cfg?.selected_provider===provider)await apiFetch(providersApi+"/config",json("PUT",{provider:"local"}));cfg=await apiFetch(providersApi+"/config");selectedProvider=cfg.selected_provider||"local";$("provider").value=selectedProvider;refreshProviderFields();msg("provider-msg",T("Chave removida do cofre seguro. Nenhuma conta ou dado do provedor foi excluído."),"good");}catch(e){msg("provider-msg",e.message,"error");}}
async function testProvider(){const provider=$("provider").value,model=currentModel();if(provider==="local"){if(!aiStatus?.runtime_running){msg("provider-msg",T("Ative um modelo local antes de testar."),"warn");return;}try{const test=await apiFetch(api+"/generate",json("POST",{provider:"local",system_prompt:"Responda de forma curta.",prompt:"Responda somente: conexão local funcionando.",max_tokens:100}));msg("provider-msg",T("Teste local: ")+test.text,"good");}catch(e){msg("provider-msg",e.message,"error");}return;}try{if(!await saveProvider())return;const result=await apiFetch(providersApi+"/test",json("POST",{provider,model}));msg("provider-msg",T("Teste concluído: ")+result.message,"good");}catch(e){msg("provider-msg",e.message,"error");}}
async function loadLocal(){try{catalog=await apiFetch(api+"/catalog");aiStatus=await apiFetch(api+"/status");renderModels();renderRuntime();}catch(e){msg("local-msg",T("Não consegui consultar o gerenciador de IA: ")+e.message,"error");}}
function renderRuntime(){const select=$("runtime");const compatible=(catalog?.runtimes||[]).filter(x=>x.compatible);select.innerHTML=compatible.length?compatible.map(x=>'<option value="'+x.id+'">'+x.label+(x.installed?" (instalado)":"")+'</option>').join(""):'<option value="">'+T("Nenhum runtime compatível encontrado")+'</option>';const installed=compatible.find(x=>x.installed);if(installed)select.value=installed.id;const status=aiStatus?.runtime_running?(T("Runtime ativo · modelo ")+aiStatus.active_model+T(" · variante ")+aiStatus.active_variant):aiStatus?.runtime_installed?T("Runtime instalado, não está ativo."):T("Runtime llama.cpp ainda não instalado.");msg("local-msg",status,aiStatus?.runtime_running?"good":"warn");const list=$("runtime-installed");if(list){list.innerHTML="";for(const runtime of (catalog?.runtimes||[]).filter(x=>x.installed)){const row=document.createElement("div");row.className="model-item";const title=document.createElement("strong");title.textContent=runtime.label;row.appendChild(title);const active=aiStatus?.runtime_running&&aiStatus?.active_variant===runtime.id;const note=document.createElement("div");note.className="small";note.textContent=active?T("Runtime ativo — será desligado ao desinstalar."):T("Runtime instalado.");row.appendChild(note);const button=document.createElement("button");button.className="btn danger";button.textContent=T("Desinstalar runtime e excluir arquivos");button.onclick=()=>uninstallRuntime(runtime);row.appendChild(button);list.appendChild(row);}}}function renderModels(){
const list=$("models");list.innerHTML="";
const models=[...(catalog?.models||[])];
for(const imported of (catalog?.installed_models||[]).filter(m=>!models.some(x=>x.id===m.id))){
models.push({id:imported.id,name:imported.name,description:"Modelo GGUF importado pelo usuário.",installed:true,license:imported.license,size_bytes:imported.size_bytes});
}
for(const model of models){const installedInfo=(catalog?.installed_models||[]).find(x=>x.id===model.id);if(installedInfo)model.size_bytes=installedInfo.size_bytes;}
if(!models.length){list.textContent=T("Nenhum modelo no catálogo. Verifique a conexão com o gerenciador de IA.");return;}
for(const m of models){
const item=document.createElement("div");item.className="model-item";
const name=document.createElement("strong");name.textContent=m.name;item.appendChild(name);
const description=document.createElement("div");description.className="small";description.textContent=m.description||T("Modelo importado");item.appendChild(description);
const licenseLine=document.createElement("div");licenseLine.className="small";licenseLine.textContent=T("Licença: ")+(m.license||T("Licença do modelo"));item.appendChild(licenseLine);
const sizeLine=document.createElement("div");sizeLine.className="small";sizeLine.textContent=m.size_bytes?T("Espaço ocupado: ")+(m.size_bytes/1024**3).toFixed(2)+" GB":T("Peso estimado do arquivo: ")+(m.download_estimate||(m.approx_size_gb?m.approx_size_gb+" GB (aprox.)":T("arquivo importado")));item.appendChild(sizeLine);
const diskLine=document.createElement("div");diskLine.className="small";diskLine.textContent=T("Espaço livre recomendado: ")+(m.disk_estimate||(m.approx_size_gb?Math.ceil(m.approx_size_gb*1.5)+" GB":T("não estimado")));item.appendChild(diskLine);
if(m.requires_license_acceptance){
const label=document.createElement("label");label.className="small inline";
const check=document.createElement("input");check.type="checkbox";
label.append(check,document.createTextNode(T("Li e aceito os termos de licença")));item.appendChild(label);
const link=document.createElement("a");link.href=m.license_url;link.target="_blank";link.rel="noopener";link.textContent=T("Abrir licença");link.className="small";item.appendChild(link);
}
const row=document.createElement("div");row.className="row";
if(!m.installed){
const button=document.createElement("button");button.className="btn";button.textContent=T("Baixar modelo");
button.disabled=!!m.requires_license_acceptance;
button.onclick=()=>downloadModel(m);row.appendChild(button);
if(m.requires_license_acceptance){
const check=item.querySelector('input[type="checkbox"]');if(check)check.onchange=()=>button.disabled=!check.checked;
}
}else{
const active=(aiStatus?.active_model||"")===m.id&&aiStatus?.runtime_running;
const activate=document.createElement("button");activate.className="btn primary";activate.textContent=active?T("Modelo ativo"):T("Ativar modelo");activate.disabled=active;activate.onclick=()=>activateModel(m);row.appendChild(activate);
const remove=document.createElement("button");remove.className="btn danger";remove.textContent=T("Desinstalar e excluir");remove.onclick=()=>deleteModel(m);row.appendChild(remove);
}
item.appendChild(row);list.appendChild(item);
}
}
async function runJob(id,kind){msg("local-msg",T("A tarefa começou. Aguarde…"),"warn");while(true){await new Promise(r=>setTimeout(r,1500));const job=await apiFetch(api+"/jobs/"+id);msg("local-msg",(job.progress||0)+"% · "+T(job.message),job.status==="error"?"error":job.status==="done"?"good":"warn");if(job.status==="done"){await loadLocal();return;}if(job.status==="error")throw new Error(job.message||T("A tarefa falhou."));}}
async function uninstallRuntime(runtime){if(!confirm(T("Desinstalar runtime ")+runtime.label+T(" e excluir seus arquivos baixados?")+(aiStatus?.active_variant===runtime.id?T(" O runtime ativo será desligado antes da remoção."): "")))return;try{const result=await apiFetch(api+"/runtime/"+encodeURIComponent(runtime.id),{method:"DELETE"});await loadLocal();msg("local-msg",T("Runtime removido. Espaço liberado: ")+((result.removed_bytes||0)/1024**3).toFixed(2)+T(" GB."),"good");}catch(e){msg("local-msg",e.message,"error");}}
async function installRuntime(){const variant=$("runtime").value;if(!variant){msg("local-msg",T("Selecione um runtime compatível."),"warn");return;}try{const result=await apiFetch(api+"/runtime/install",json("POST",{variant}));if(result.job_id)await runJob(result.job_id,"runtime");else await loadLocal();}catch(e){msg("local-msg",e.message,"error");}}
async function downloadModel(m){try{const accept=m.requires_license_acceptance?true:false;const result=await apiFetch(api+"/models/download",json("POST",{model_id:m.id,accept_license:accept}));if(result.job_id)await runJob(result.job_id,"model");else await loadLocal();}catch(e){msg("local-msg",e.message,"error");}}
async function importModel(){const file=$("gguf-file").files[0];if(!file){msg("local-msg",T("Escolha um arquivo .gguf para importar."),"warn");return;}if(!confirm(T("Importar este arquivo GGUF? A licença do modelo não será verificada automaticamente.")))return;try{msg("local-msg",T("Importando modelo GGUF…"),"warn");const fd=new FormData();fd.append("file",file);const result=await apiFetch(api+"/models/import",{method:"POST",body:fd});msg("local-msg",T("Modelo importado: ")+result.name+" · "+result.warning,"good");await loadLocal();}catch(e){msg("local-msg",e.message,"error");}}
async function activateModel(m){const variant=$("runtime").value,gpu_layers=Number($("gpu-layers").value);if(!variant){msg("local-msg",T("Instale e selecione um runtime compatível."),"warn");return;}try{msg("local-msg",T("Inicializando modelo. Isso pode levar alguns minutos…"),"warn");await apiFetch(api+"/models/activate",json("POST",{model_id:m.id,variant,gpu_layers}));await loadLocal();msg("local-msg",T("Modelo local ativado: ")+m.name,"good");}catch(e){msg("local-msg",e.message,"error");}}
async function deleteModel(m){if(!confirm(T("Desinstalar e excluir ")+m.name+T("? Os pesos deste modelo serão removidos. Se ele estiver ativo, será desligado antes da exclusão. Se houver uma geração em andamento, a exclusão será bloqueada e você precisará tentar novamente quando terminar. O llama.cpp instalado, os outros modelos, seus roteiros e projetos serão preservados.")))return;try{const result=await apiFetch(api+"/models/"+encodeURIComponent(m.id),{method:"DELETE"});await loadLocal();const freed=(Number(result.removed_bytes||0)/1024**3).toFixed(2);msg("local-msg",T("Modelo ")+m.name+T(" removido. Espaço liberado: ")+freed+T(" GB. O llama.cpp instalado e os demais modelos foram preservados."),"good");}catch(e){msg("local-msg",e.message,"error");}}
function promptForWorkspace(){
if(workspace==="scripts"){
const subject=$("subject").value.trim(),format=$("format").value,duration=$("duration").value,durationLabel=$("duration").selectedOptions[0]?.textContent||duration,tone=$("tone").value,audience=$("audience").value.trim(),notes=$("notes").value.trim(),base=$("script-input").value.trim();
const durationSeconds=duration==="60-70"?65:duration==="30"||duration==="90"?Number(duration):Number(duration)*60;
const characterLimit=Math.max(100,Math.round(durationSeconds*20));
const formatDesc=format==="shorts"?"Short-form vertical video for Shorts, Reels or TikTok, approximately "+durationLabel+".":format==="long"?"Long-form YouTube video, around "+durationLabel+".":"Flexible video format, around "+durationLabel+".";
const system="Você é roteirista profissional de vídeos e narrador editorial. Escreva em português brasileiro natural, com ritmo de fala, frases claras, sem inventar dados. Crie uma abertura forte, desenvolvimento organizado e fechamento adequado. Evite linguagem robótica e excesso de adjetivos. Não imite autores ou criadores específicos. Entregue apenas o roteiro final, sem explicar o processo.";
const shortRules=format==="shorts"?"Para Shorts/Reels/TikTok, mantenha aproximadamente "+durationLabel+" e no máximo "+characterLimit.toLocaleString("pt-BR")+" caracteres, com ritmo de fala e retenção. ":"";
const prompt="TEMA/ASSUNTO: "+(subject||"desenvolva o assunto descrito abaixo")+"\nFORMATO: "+formatDesc+"\nTOM: "+tone+"\nPÚBLICO: "+(audience||"público geral")+"\nINSTRUÇÕES: "+shortRules+(notes||"Use uma estrutura clara e envolvente")+"\n\nREFERÊNCIA OU TEXTO BASE:\n"+(base||"Crie o roteiro com base no tema e instruções acima.");
return {system,prompt};
}
const input=$("visual-input").value.trim(),kind=$("visual-kind").value,style=$("visual-style").value.trim(),tool=$("target-tool").value,lang=$("prompt-language").value,sceneCount=$("scene-count").value;
const system="You are an expert prompt writer and visual director for AI image and video generation. Write polished, detailed generation prompts. Do not imitate copyrighted characters or living artists. Use explicit shot descriptions, subject, setting, lighting, composition, movement, mood, continuity details and avoid vague language. Output "+(lang==="en"?"in English":"in Brazilian Portuguese")+" and organize each scene with a clear heading and prompt. Avoid camera zoom unless explicitly requested.";
const countInstruction=sceneCount==="auto"?"Determine a suitable scene count from the source and divide at natural visual changes.":"Create exactly "+sceneCount+" scene prompts.";
const prompt="OUTPUT TYPE: "+(kind==="image"?"Image generation prompts":"Video generation prompts")+"\nTARGET TOOL: "+(tool||"general-purpose generator")+"\nVISUAL STYLE / CHARACTER CONTINUITY: "+(style||"choose a coherent visual style and maintain continuity")+"\nSCENE COUNT: "+sceneCount+"\n\nSOURCE SCRIPT OR CONCEPT:\n"+input+"\n\n"+countInstruction+" For every scene include scene number, time/sequence if inferable, image composition, environment, character actions and expressions, camera angle and framing, lighting, color palette, and continuity locks. For video prompts, include motion and scene progression, but do not add unsupported narrative events. Keep each scene prompt usable on its own.";
return {system,prompt};
}

async function generate(){if(workspace==="scripts"&&!$("script-input").value.trim()&&!$("subject").value.trim()){msg("generation-msg",T("Informe um tema ou cole um texto base antes de gerar."),"warn");return;}if(workspace==="prompts"&&!$("visual-input").value.trim()){msg("generation-msg",T("Cole um roteiro, ideia ou descrição de cena antes de gerar."),"warn");return;}const p=$("provider").value;const model=$("provider-model").value.trim();if(p!=="local"&&!model){msg("provider-msg",T("Selecione ou digite o modelo API."),"warn");return;}const prompts=promptForWorkspace();const btn=$("generate");btn.disabled=true;btn.textContent=T("Gerando…");msg("generation-msg",T("Enviando pedido para ")+providerName(p)+"…","warn");try{const result=await apiFetch(api+"/generate",json("POST",{provider:p,provider_model:model,system_prompt:prompts.system,prompt:prompts.prompt,max_tokens:5000}));$("output").value=result.text;msg("generation-msg",T("Geração concluída usando ")+result.model+".","good");}catch(e){msg("generation-msg",e.message,"error");}finally{btn.disabled=false;btn.textContent=T("Gerar com IA");}}
async function copyOutput(){try{await navigator.clipboard.writeText($("output").value);msg("generation-msg",T("Texto copiado para a área de transferência."),"good");}catch(e){$("output").select();document.execCommand("copy");msg("generation-msg",T("Texto copiado."),"good");}}
function sendToNarration(){const text=$("output").value.trim();if(!text){msg("generation-msg",T("Gere ou escreva o roteiro antes de enviar."),"warn");return;}try{localStorage.setItem("socialsound:texto-pendente",text);if(parent!==window)parent.postMessage({tipo:"ir-para-narracao"},location.origin);msg("generation-msg",T("Roteiro enviado para a área de Narração. Abra a aba Narração no menu lateral."),"good");}catch(e){msg("generation-msg",T("Não consegui enviar o texto para a Narração."),"error");}}
function downloadOutput(){const text=$("output").value;if(!text)return;const blob=new Blob([text],{type:"text/plain;charset=utf-8"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=workspace==="scripts"?"roteiro-ia.txt":"prompts-visuais-ia.txt";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function setupWorkspace(){if(workspace==="scripts"){$("send-narration").classList.remove("hidden");$("subject").placeholder=T("Ex.: curiosidades sobre o espaço, história bíblica, humor cotidiano…");}else{$("send-narration").classList.add("hidden");}}
$("provider").addEventListener("change",refreshProviderFields);$("save-provider").onclick=saveProvider;$("save-key").onclick=saveKey;$("test-provider").onclick=testProvider;$("remove-key").onclick=removeProviderKey;$("install-runtime").onclick=installRuntime;$("import-model").onclick=importModel;$("generate").onclick=generate;$("copy-output").onclick=copyOutput;$("download-output").onclick=downloadOutput;$("send-narration").onclick=sendToNarration;$("refresh-local").onclick=loadLocal;$("gpu-layers").oninput=()=>{$("gpu-value").textContent=$("gpu-layers").value;};
setupWorkspace();loadConfig().catch(e=>msg("provider-msg",e.message,"error"));loadLocal();
})();