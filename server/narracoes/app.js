const API="/api/narration";
const UI_LANG=new URLSearchParams(location.search).get("lang")==="en"?"en":"pt-BR";
const UI_STR={"en":{
"Na fila":"Queued","Em andamento":"In progress","Concluída":"Completed","Falhou":"Failed","Interrompida":"Interrupted",
"Nenhuma narração na fila ainda.":"No narrations in the queue yet.",
"Parte ":"Part "," de ":" of ","pendente":"pending",
"Regenerar esta parte":"Regenerate this part","Nova versão — aguardando sua aprovação":"New version — awaiting your approval",
"Aprovar e substituir":"Approve and replace","Descartar":"Discard",
"Narração ":"Narration "," parte(s)":" part(s)",
"Motor: ":"Engine: "," · Voz: ":" · Voice: "," · Criada: ":" · Created: ",
" partes concluídas":" parts completed",
"Tempo em andamento: ":"Elapsed time: ","Tempo de geração: ":"Generation time: ",
"Áudio completo":"Full audio","Baixar áudio completo":"Download full audio",
"Ver partes e versões":"View parts and versions",
"↑ Subir":"↑ Move up","↓ Descer":"↓ Move down","Remover da fila":"Remove from queue",
"Tentar novamente":"Retry","Nenhuma voz encontrada":"No voices found",
"Voz predefinida":"Preset voice","Voz automática":"Automatic voice",
"Clonar voz com áudio de referência":"Clone voice from reference audio",
"Criar voz por descrição":"Create voice from description",
"Minha voz":"My voice","Padrão":"Preset",
"Supertonic 3 usa 10 vozes predefinidas. Clonagem de áudio não está disponível.":"Supertonic 3 has 10 preset voices. Audio cloning is not available.",
"OmniVoice é somente para uso não comercial. Use apenas sua voz ou uma voz com autorização.":"OmniVoice is non-commercial only. Use only your own voice or a voice you have permission to use.",
"F5-TTS PT-BR é um modelo comunitário experimental e somente para uso não comercial. Use uma voz autorizada.":"F5-TTS Brazilian Portuguese is an experimental community model for non-commercial use only. Use an authorized voice.",
"O VoxCPM2 aceita vozes salvas e vozes predefinidas.":"VoxCPM2 supports saved and preset voices.",
"Erro ":"Error ","Não foi possível carregar a fila: ":"Could not load queue: "
}};
const T=value=>UI_LANG==="en"?(UI_STR.en[value]||value):value;
const $=id=>document.getElementById(id);
let jobs=[];let queuePaused=false;let voicesData=null;const jobElapsed=new Map();function elapsedLabel(ms){const total=Math.max(0,Math.floor(ms/1000));return String(Math.floor(total/60)).padStart(2,"0")+":"+String(total%60).padStart(2,"0");}
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const statusLabel=s=>T(({queued:"Na fila",processing:"Em andamento",completed:"Concluída",failed:"Falhou",interrupted:"Interrompida"}[s]||s));
async function request(url,options={}){const res=await fetch(url,options);if(!res.ok){let msg="Erro "+res.status;try{const d=await res.json();msg=d.detail||msg}catch{}throw new Error(msg)}return res.json()}
function refreshVoiceOptions(){
 const engine=$("engine").value;let opts=[];
 if(engine==="supertonic3"){
  opts=["M1","M2","M3","M4","M5","F1","F2","F3","F4","F5"].map(v=>({id:"supertonic:"+v,label:v+" — "+T("Voz predefinida")}));
  $("styleField").style.display="none";$("omnivoiceFields").style.display="none";
  $("stylehint").textContent=T("Supertonic 3 usa 10 vozes predefinidas. Clonagem de áudio não está disponível.");
 }else if(engine==="omnivoice"){
  opts=[{id:"omnivoice:auto",label:T("Voz automática")},{id:"omnivoice:clone",label:T("Clonar voz com áudio de referência")},{id:"omnivoice:design",label:T("Criar voz por descrição")}];
  $("omnivoiceFields").style.display="block";$("styleField").style.display="none";
  $("stylehint").textContent=T("OmniVoice é somente para uso não comercial. Use apenas sua voz ou uma voz com autorização.");
 }else if(engine==="f5tts"){
  opts=[{id:"f5tts:clone",label:T("Clonar voz com áudio de referência")}];
  $("omnivoiceFields").style.display="block";$("styleField").style.display="none";
  $("stylehint").textContent=T("F5-TTS PT-BR é um modelo comunitário experimental e somente para uso não comercial. Use uma voz autorizada.");
 }else{
  if(voicesData){voicesData.mine.forEach(v=>opts.push({id:"mine:"+v.name,label:v.name+" — "+T("Minha voz")}));voicesData.presets.forEach(v=>opts.push({id:"preset:"+v.id,label:v.label+" — "+T("Padrão")}))}
  $("styleField").style.display="block";$("omnivoiceFields").style.display="none";
  $("stylehint").textContent=T("O VoxCPM2 aceita vozes salvas e vozes predefinidas.");
 }
 $("voice").innerHTML=opts.map(v=>'<option value="'+esc(v.id)+'">'+esc(v.label)+'</option>').join("")||'<option value="">'+T("Nenhuma voz encontrada")+'</option>';
 if(engine==="omnivoice"||engine==="f5tts")refreshOmniMode();
}
function refreshOmniMode(){
 const engine=$("engine").value;if(engine!=="omnivoice"&&engine!=="f5tts")return;
 const mode=engine==="f5tts"?"clone":($("voice").value.split(":")[1]||"auto");
 $("omnivoiceReferenceField").style.display=mode==="clone"?"block":"none";
 $("styleField").style.display=mode==="design"?"block":"none";
 if(mode==="design"){$("style").placeholder="Ex.: voz feminina adulta, grave, acolhedora, sotaque brasileiro, ritmo calmo";$("stylehint").textContent="Descreva as características desejadas. Não imite pessoa real sem autorização."}
}
async function loadVoices(){try{voicesData=await fetch("/voices").then(r=>r.json());refreshVoiceOptions()}catch(e){$("formerror").textContent="Não foi possível carregar as vozes: "+e.message}}
async function loadEngines(){try{const data=await request(API+"/engines");const engines=data.engines||[];const supertonic=engines.find(e=>e.id==="supertonic3");const omni=engines.find(e=>e.id==="omnivoice");const f5=engines.find(e=>e.id==="f5tts");$("engine").innerHTML='<option value="voxcpm2">VoxCPM2</option>'+(supertonic&&supertonic.installed?'<option value="supertonic3">Supertonic 3</option>':'<option value="supertonic3" disabled>Supertonic 3 — instale pela aba Motores de Voz</option>')+(omni&&omni.installed?'<option value="omnivoice">OmniVoice (não comercial)</option>':'<option value="omnivoice" disabled>OmniVoice — instale pela aba Motores de Voz</option>')+(f5&&f5.installed?'<option value="f5tts">F5-TTS PT-BR (não comercial)</option>':'<option value="f5tts" disabled>F5-TTS PT-BR — instale pela aba Motores de Voz</option>');const groups=[["commercial","Motores com uso comercial permitido"],["non_commercial","Motores não comerciais"]];$("engines").innerHTML=groups.map(([category,title])=>{const items=engines.filter(e=>e.category===category);return '<div><h3 style="font-size:13px;margin:0 0 9px">'+title+'</h3>'+items.map(e=>'<article class="engine"><span class="status '+(e.installed?'completed':'')+'">'+(e.installed?(e.id==="supertonic3"||e.id==="omnivoice"||e.id==="f5tts"?"Instalado":"Integrado"):(e.id==="supertonic3"?"Opcional · instalar pela aba Motores de Voz":e.id==="omnivoice"?"Opcional · instalar pela aba Motores de Voz":e.id==="f5tts"?"Opcional · instalar pela aba Motores de Voz":"Opcional · não instalado"))+'</span><h3>'+esc(e.name)+'</h3><div class="meta">Código: '+esc(e.code_license)+'<br>Pesos: '+esc(e.weights_license)+'<br>Clonagem: '+(e.voice_cloning?'Sim':'Não')+(e.download_estimate?'<br><strong>Download estimado:</strong> '+esc(e.download_estimate):'')+(e.disk_estimate?'<br><strong>Espaço recomendado:</strong> '+esc(e.disk_estimate):'')+'</div><p>'+esc(e.size_notes||'')+'</p><p>'+esc(e.notes)+'</p><a href="'+esc(e.model_url)+'" target="_blank" rel="noreferrer">Modelo e licença oficial</a> · <a href="'+esc(e.code_url)+'" target="_blank" rel="noreferrer">Código</a>'+(e.tokenizer_url?' · <a href="'+esc(e.tokenizer_url)+'" target="_blank" rel="noreferrer">Licença tokenizer</a>':'')+(e.installed&&["supertonic3","omnivoice","f5tts","voxcpm2"].includes(e.id)?'<button type="button" class="btn" data-uninstall-engine="'+esc(e.id)+'">'+(e.id==="voxcpm2"?"Liberar pesos baixados":"Desinstalar e excluir")+'</button>':'')+'</article>').join("")+'</div>'}).join("");$("engines").querySelectorAll("[data-uninstall-engine]").forEach(button=>button.addEventListener("click",()=>uninstallEngine(button.dataset.uninstallEngine)));refreshVoiceOptions()}catch(e){$("engines").textContent="Não foi possível carregar o catálogo de motores."}}
async function uninstallEngine(id){const isCore=id==="voxcpm2";const name=({voxcpm2:"VoxCPM2",supertonic3:"Supertonic 3",omnivoice:"OmniVoice",f5tts:"F5-TTS PT-BR"})[id]||id;if(!confirm(isCore?"Descarregar o VoxCPM2 da memória e liberar seus pesos baixados? O motor continuará integrado e poderá baixar os pesos novamente quando for usado.":"Desinstalar "+name+"? O ambiente exclusivo será removido. Narrações e projetos serão preservados."))return;let deleteShared=false;if(isCore||["omnivoice","f5tts"].includes(id))deleteShared=confirm(isCore?"Excluir também os pesos VoxCPM2 do cache Hugging Face compartilhado? Outros aplicativos que usem os mesmos arquivos poderão precisar baixá-los novamente.\n\nEscolha Cancelar para preservar os arquivos e apenas descarregar da memória.":"Excluir também os pesos deste motor do cache Hugging Face compartilhado? Isso pode afetar outros aplicativos que usem os mesmos arquivos.\n\nEscolha Cancelar para preservar o cache.");try{const result=await request(API+"/engines/"+id,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({delete_shared_cache:deleteShared})});$("formerror").textContent=(isCore?"Pesos VoxCPM2 liberados da memória/cache.":"Motor removido.")+" Espaço liberado: "+(Number(result.removed_bytes||0)/1024**3).toFixed(2)+" GB."+(result.preserved?.length?" "+result.preserved.join("; "):"");await loadEngines();}catch(e){$("formerror").textContent="Não foi possível desinstalar: "+e.message;}}
async function analyze(){const text=$("script").value.trim();if(!text)throw new Error("Cole ou carregue o texto primeiro.");const result=await request(API+"/split",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,target_seconds:Number($("duration").value)})});$("splitinfo").textContent=result.parts.length+" parte(s) estimada(s).";return result}
async function enqueue(){
 try{
  $("formerror").textContent="";
  const text=$("script").value.trim();if(!text)throw new Error("Cole ou carregue o texto primeiro.");
  const engine=$("engine").value,voice=$("voice").value;
  const mode=engine==="f5tts"?"clone":engine==="omnivoice"?(voice.split(":")[1]||"auto"):"auto";
  let reference_audio="";
  if((engine==="omnivoice"||engine==="f5tts")&&mode==="clone"){
   const file=$("omnivoiceReference").files[0];
   if(!file)throw new Error("Selecione o áudio de referência.");
   if(!$("omnivoiceReferenceText").value.trim())throw new Error("Informe a transcrição do áudio de referência.");
   const form=new FormData();form.append("file",file);
   const uploaded=await request(API+"/omnivoice/reference",{method:"POST",body:form});
   reference_audio=uploaded.reference_audio;
  }
  await request(API+"/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,engine,voice,mode,reference_audio,reference_text:$("omnivoiceReferenceText").value,style:$("style").value,target_seconds:Number($("duration").value)})});
  $("script").value="";$("splitinfo").textContent="Adicionada à fila.";await refresh();
 }catch(e){$("formerror").textContent=e.message}
}
async function refresh(){try{const [data,queue]=await Promise.all([request(API+"/jobs"),request(API+"/queue/status")]);jobs=data.jobs||[];const now=Date.now();const parseQueueTime=value=>value?Date.parse(String(value).replace(" ","T")+"Z"):NaN;jobs.forEach(job=>{const started=parseQueueTime(job.started_at),ended=parseQueueTime(job.completed_at);if(Number.isFinite(started)){jobElapsed.set(job.id,{start:started,end:job.status==="processing"?null:(Number.isFinite(ended)?ended:started)});}else if(job.status==="processing"&&!jobElapsed.has(job.id)){jobElapsed.set(job.id,{start:now,end:null});}});queuePaused=!!queue.paused;$("queueStatus").textContent=queuePaused?"Fila pausada após o trabalho atual":"Fila ativa";$("toggleQueue").textContent=queuePaused?"Continuar fila":"Pausar após a atual";const candidates=await Promise.all(jobs.map(async j=>{try{return [j.id,(await request(API+"/jobs/"+j.id+"/candidates")).candidates||[]]}catch{return [j.id,[]]}}));const byJob=Object.fromEntries(candidates);render(byJob)}catch(e){$("jobs").innerHTML='<div class="empty">Não foi possível carregar a fila: '+esc(e.message)+'</div>'}}
function render(candidates){if(!jobs.length){$("jobs").innerHTML='<div class="panel empty">'+T("Nenhuma narração na fila ainda.")+'</div>';return}
$("jobs").innerHTML=jobs.map(job=>{const engineLabel=job.engine==="supertonic3"?"Supertonic 3":job.engine==="omnivoice"?"OmniVoice":job.engine==="f5tts"?"F5-TTS PT-BR":"VoxCPM2";const done=job.parts.filter(p=>p.status==="completed"||p.status==="approved").length;const pct=job.parts.length?Math.round(done/job.parts.length*100):0;const timer=jobElapsed.get(job.id);const elapsed=timer?elapsedLabel((timer.end??Date.now())-timer.start):"00:00";const parts=job.parts.map((part,index)=>{const cand=(candidates[job.id]||[]).filter(c=>c.part_index===index);return '<div class="part"><div class="parthead"><strong>Parte '+(index+1)+' de '+job.parts.length+'</strong><span class="status">'+esc(part.status||"pendente")+'</span></div><p>'+esc(part.text)+'</p>'+(part.audio_url?'<audio controls preload="none" src="'+esc(part.audio_url)+'"></audio>':'')+(job.status==="completed"?'<div class="actions" style="margin-top:8px"><button class="secondary" data-action="regen" data-job="'+job.id+'" data-part="'+index+'">Regenerar esta parte</button></div>':'')+cand.map(c=>'<div class="candidate"><strong>Nova versão — aguardando sua aprovação</strong><audio controls preload="none" src="'+esc(c.audio_url)+'"></audio><div class="actions"><button class="success" data-action="approve" data-id="'+c.id+'">Aprovar e substituir</button><button class="danger" data-action="discard" data-id="'+c.id+'">Descartar</button></div></div>').join("")+'</div>'}).join("");
return '<article class="job"><div class="jobhead"><h3>Narração '+esc(job.id.slice(0,8))+' · '+job.parts.length+' parte(s)</h3><span class="status '+esc(job.status)+'">'+esc(statusLabel(job.status))+'</span></div><div class="small muted">Motor: '+engineLabel+' · Voz: '+esc(job.voice)+' · Criada: '+esc(job.created_at)+'</div><div class="progress"><span style="width:'+pct+'%"></span></div><div class="small muted">'+done+' de '+job.parts.length+' partes concluídas</div>'+(job.status==="processing"||job.status==="completed"&&timer?'<div class="small muted">⏱ '+(job.status==="processing"?'Tempo em andamento: ':'Tempo de geração: ')+elapsed+'</div>':'')+''+(job.error?'<p class="error">'+esc(job.error)+'</p>':'')+(job.audio_url?'<div style="margin:12px 0"><strong>Áudio completo</strong><audio controls src="'+esc(job.audio_url)+'"></audio><a class="linkbtn secondary" href="'+esc(job.audio_url)+'" download="social-sound-narracao.wav">Baixar áudio completo</a></div>':'')+'<details style="margin-top:14px"><summary style="cursor:pointer;font-weight:800">Ver partes e versões</summary><div class="parts" style="margin-top:12px">'+parts+'</div></details>'+(job.status==="queued"?'<div class="actions" style="margin-top:12px"><button class="secondary" data-action="move-up" data-job="'+job.id+'">↑ Subir</button><button class="secondary" data-action="move-down" data-job="'+job.id+'">↓ Descer</button><button class="danger" data-action="remove" data-job="'+job.id+'">Remover da fila</button></div>':'')+(["failed","interrupted"].includes(job.status)?'<div class="actions" style="margin-top:12px"><button data-action="requeue" data-job="'+job.id+'">Tentar novamente</button></div>':'')+'</article>'}).join("");
if(UI_LANG==="en")$("jobs").innerHTML=Object.keys(UI_STR.en).reduce((html,pt)=>html.split(pt).join(UI_STR.en[pt]),$("jobs").innerHTML);
}
$("preview").addEventListener("click",async()=>{try{$("formerror").textContent="";await analyze()}catch(e){$("formerror").textContent=e.message}});
$("enqueue").addEventListener("click",enqueue);$("refresh").addEventListener("click",refresh);$("engine").addEventListener("change",refreshVoiceOptions);$("voice").addEventListener("change",refreshOmniMode);
$("txtfile").addEventListener("change",async e=>{const file=e.target.files[0];if(file){$("script").value=await file.text();$("filelabel").textContent=file.name;e.target.value=""}});
$("jobs").addEventListener("click",async e=>{const b=e.target.closest("button[data-action]");if(!b)return;b.disabled=true;try{const action=b.dataset.action,job=b.dataset.job;if(action==="regen"){await request(API+"/jobs/"+job+"/parts/"+b.dataset.part+"/regenerate",{method:"POST"});await refresh()}else if(action==="approve"){await request(API+"/candidates/"+b.dataset.id+"/approve",{method:"POST"});await refresh()}else if(action==="discard"){await request(API+"/candidates/"+b.dataset.id+"/discard",{method:"POST"});await refresh()}else if(action==="requeue"){await request(API+"/jobs/"+job+"/requeue",{method:"POST"});await refresh()}else if(action==="move-up"||action==="move-down"){await request(API+"/jobs/"+job+"/"+(action==="move-up"?"move-up":"move-down"),{method:"POST"});await refresh()}else if(action==="remove"){if(confirm("Remover esta narração que ainda não começou?")){await request(API+"/jobs/"+job,{method:"DELETE"});await refresh()}else b.disabled=false}}catch(err){alert(err.message);b.disabled=false}});
$("toggleQueue").addEventListener("click",async()=>{const action=queuePaused?"resume":"pause";$("toggleQueue").disabled=true;try{await request(API+"/queue/"+action,{method:"POST"});await refresh()}catch(e){alert(e.message)}finally{$("toggleQueue").disabled=false}});
loadVoices();loadEngines();refresh();setInterval(refresh,2000);
