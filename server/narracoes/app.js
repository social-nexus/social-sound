const API="/api/narration";
const $=id=>document.getElementById(id);
let jobs=[];let queuePaused=false;let voicesData=null;
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const statusLabel=s=>({queued:"Na fila",processing:"Em andamento",completed:"Concluída",failed:"Falhou",interrupted:"Interrompida"}[s]||s);
async function request(url,options={}){const res=await fetch(url,options);if(!res.ok){let msg="Erro "+res.status;try{const d=await res.json();msg=d.detail||msg}catch{}throw new Error(msg)}return res.json()}
function refreshVoiceOptions(){
 const engine=$("engine").value;let opts=[];
 if(engine==="supertonic3"){
  opts=["M1","M2","M3","M4","M5","F1","F2","F3","F4","F5"].map(v=>({id:"supertonic:"+v,label:v+" — Voz predefinida"}));
  $("styleField").style.display="none";$("omnivoiceFields").style.display="none";
  $("stylehint").textContent="Supertonic 3 usa 10 vozes predefinidas. Clonagem de áudio não está disponível.";
 }else if(engine==="omnivoice"){
  opts=[{id:"omnivoice:auto",label:"Voz automática"},{id:"omnivoice:clone",label:"Clonar voz com áudio de referência"},{id:"omnivoice:design",label:"Criar voz por descrição"}];
  $("omnivoiceFields").style.display="block";$("styleField").style.display="none";
  $("stylehint").textContent="OmniVoice é somente para uso não comercial. Use apenas sua voz ou uma voz com autorização.";
 }else if(engine==="f5tts"){
  opts=[{id:"f5tts:clone",label:"Clonar voz com áudio de referência"}];
  $("omnivoiceFields").style.display="block";$("styleField").style.display="none";
  $("stylehint").textContent="F5-TTS PT-BR é um modelo comunitário experimental e somente para uso não comercial. Use uma voz autorizada.";
 }else{
  if(voicesData){voicesData.mine.forEach(v=>opts.push({id:"mine:"+v.name,label:v.name+" — Minha voz"}));voicesData.presets.forEach(v=>opts.push({id:"preset:"+v.id,label:v.label+" — Padrão"}))}
  $("styleField").style.display="block";$("omnivoiceFields").style.display="none";
  $("stylehint").textContent="O VoxCPM2 aceita vozes salvas e vozes predefinidas.";
 }
 $("voice").innerHTML=opts.map(v=>'<option value="'+esc(v.id)+'">'+esc(v.label)+'</option>').join("")||'<option value="">Nenhuma voz encontrada</option>';
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
async function loadEngines(){try{const data=await request(API+"/engines");const engines=data.engines||[];const supertonic=engines.find(e=>e.id==="supertonic3");const omni=engines.find(e=>e.id==="omnivoice");const f5=engines.find(e=>e.id==="f5tts");$("engine").innerHTML='<option value="voxcpm2">VoxCPM2</option>'+(supertonic&&supertonic.installed?'<option value="supertonic3">Supertonic 3</option>':'<option value="supertonic3" disabled>Supertonic 3 — execute instalar-supertonic.bat</option>')+(omni&&omni.installed?'<option value="omnivoice">OmniVoice (não comercial)</option>':'<option value="omnivoice" disabled>OmniVoice — execute instalar-omnivoice.bat</option>')+(f5&&f5.installed?'<option value="f5tts">F5-TTS PT-BR (não comercial)</option>':'<option value="f5tts" disabled>F5-TTS PT-BR — execute instalar-f5tts.bat</option>');const groups=[["commercial","Motores com uso comercial permitido"],["non_commercial","Motores não comerciais"]];$("engines").innerHTML=groups.map(([category,title])=>{const items=engines.filter(e=>e.category===category);return '<div><h3 style="font-size:13px;margin:0 0 9px">'+title+'</h3>'+items.map(e=>'<article class="engine"><span class="status '+(e.installed?'completed':'')+'">'+(e.installed?(e.id==="supertonic3"||e.id==="omnivoice"||e.id==="f5tts"?"Instalado":"Integrado"):(e.id==="supertonic3"?"Opcional · instalar-supertonic.bat":e.id==="omnivoice"?"Opcional · instalar-omnivoice.bat":e.id==="f5tts"?"Opcional · instalar-f5tts.bat":"Opcional · não instalado"))+'</span><h3>'+esc(e.name)+'</h3><div class="meta">Código: '+esc(e.code_license)+'<br>Pesos: '+esc(e.weights_license)+'<br>Clonagem: '+(e.voice_cloning?'Sim':'Não')+(e.download_estimate?'<br><strong>Download estimado:</strong> '+esc(e.download_estimate):'')+(e.disk_estimate?'<br><strong>Espaço recomendado:</strong> '+esc(e.disk_estimate):'')+'</div><p>'+esc(e.size_notes||'')+'</p><p>'+esc(e.notes)+'</p><a href="'+esc(e.model_url)+'" target="_blank" rel="noreferrer">Modelo e licença oficial</a> · <a href="'+esc(e.code_url)+'" target="_blank" rel="noreferrer">Código</a></article>').join("")+'</div>'}).join("");refreshVoiceOptions()}catch(e){$("engines").textContent="Não foi possível carregar o catálogo de motores."}}
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
async function refresh(){try{const [data,queue]=await Promise.all([request(API+"/jobs"),request(API+"/queue/status")]);jobs=data.jobs||[];queuePaused=!!queue.paused;$("queueStatus").textContent=queuePaused?"Fila pausada após o trabalho atual":"Fila ativa";$("toggleQueue").textContent=queuePaused?"Continuar fila":"Pausar após a atual";const candidates=await Promise.all(jobs.map(async j=>{try{return [j.id,(await request(API+"/jobs/"+j.id+"/candidates")).candidates||[]]}catch{return [j.id,[]]}}));const byJob=Object.fromEntries(candidates);render(byJob)}catch(e){$("jobs").innerHTML='<div class="empty">Não foi possível carregar a fila: '+esc(e.message)+'</div>'}}
function render(candidates){if(!jobs.length){$("jobs").innerHTML='<div class="panel empty">Nenhuma narração na fila ainda.</div>';return}
$("jobs").innerHTML=jobs.map(job=>{const engineLabel=job.engine==="supertonic3"?"Supertonic 3":job.engine==="omnivoice"?"OmniVoice":job.engine==="f5tts"?"F5-TTS PT-BR":"VoxCPM2";const done=job.parts.filter(p=>p.status==="completed"||p.status==="approved").length;const pct=job.parts.length?Math.round(done/job.parts.length*100):0;const parts=job.parts.map((part,index)=>{const cand=(candidates[job.id]||[]).filter(c=>c.part_index===index);return '<div class="part"><div class="parthead"><strong>Parte '+(index+1)+' de '+job.parts.length+'</strong><span class="status">'+esc(part.status||"pendente")+'</span></div><p>'+esc(part.text)+'</p>'+(part.audio_url?'<audio controls preload="none" src="'+esc(part.audio_url)+'"></audio>':'')+(job.status==="completed"?'<div class="actions" style="margin-top:8px"><button class="secondary" data-action="regen" data-job="'+job.id+'" data-part="'+index+'">Regenerar esta parte</button></div>':'')+cand.map(c=>'<div class="candidate"><strong>Nova versão — aguardando sua aprovação</strong><audio controls preload="none" src="'+esc(c.audio_url)+'"></audio><div class="actions"><button class="success" data-action="approve" data-id="'+c.id+'">Aprovar e substituir</button><button class="danger" data-action="discard" data-id="'+c.id+'">Descartar</button></div></div>').join("")+'</div>'}).join("");
return '<article class="job"><div class="jobhead"><h3>Narração '+esc(job.id.slice(0,8))+' · '+job.parts.length+' parte(s)</h3><span class="status '+esc(job.status)+'">'+esc(statusLabel(job.status))+'</span></div><div class="small muted">Motor: '+engineLabel+' · Voz: '+esc(job.voice)+' · Criada: '+esc(job.created_at)+'</div><div class="progress"><span style="width:'+pct+'%"></span></div><div class="small muted">'+done+' de '+job.parts.length+' partes concluídas</div>'+(job.error?'<p class="error">'+esc(job.error)+'</p>':'')+(job.audio_url?'<div style="margin:12px 0"><strong>Áudio completo</strong><audio controls src="'+esc(job.audio_url)+'"></audio><a class="linkbtn secondary" href="'+esc(job.audio_url)+'" download="social-sound-narracao.wav">Baixar áudio completo</a></div>':'')+'<details style="margin-top:14px"><summary style="cursor:pointer;font-weight:800">Ver partes e versões</summary><div class="parts" style="margin-top:12px">'+parts+'</div></details>'+(job.status==="queued"?'<div class="actions" style="margin-top:12px"><button class="secondary" data-action="move-up" data-job="'+job.id+'">↑ Subir</button><button class="secondary" data-action="move-down" data-job="'+job.id+'">↓ Descer</button><button class="danger" data-action="remove" data-job="'+job.id+'">Remover da fila</button></div>':'')+(["failed","interrupted"].includes(job.status)?'<div class="actions" style="margin-top:12px"><button data-action="requeue" data-job="'+job.id+'">Tentar novamente</button></div>':'')+'</article>'}).join("")}
$("preview").addEventListener("click",async()=>{try{$("formerror").textContent="";await analyze()}catch(e){$("formerror").textContent=e.message}});
$("enqueue").addEventListener("click",enqueue);$("refresh").addEventListener("click",refresh);$("engine").addEventListener("change",refreshVoiceOptions);$("voice").addEventListener("change",refreshOmniMode);
$("txtfile").addEventListener("change",async e=>{const file=e.target.files[0];if(file){$("script").value=await file.text();$("filelabel").textContent=file.name;e.target.value=""}});
$("jobs").addEventListener("click",async e=>{const b=e.target.closest("button[data-action]");if(!b)return;b.disabled=true;try{const action=b.dataset.action,job=b.dataset.job;if(action==="regen"){await request(API+"/jobs/"+job+"/parts/"+b.dataset.part+"/regenerate",{method:"POST"});await refresh()}else if(action==="approve"){await request(API+"/candidates/"+b.dataset.id+"/approve",{method:"POST"});await refresh()}else if(action==="discard"){await request(API+"/candidates/"+b.dataset.id+"/discard",{method:"POST"});await refresh()}else if(action==="requeue"){await request(API+"/jobs/"+job+"/requeue",{method:"POST"});await refresh()}else if(action==="move-up"||action==="move-down"){await request(API+"/jobs/"+job+"/"+(action==="move-up"?"move-up":"move-down"),{method:"POST"});await refresh()}else if(action==="remove"){if(confirm("Remover esta narração que ainda não começou?")){await request(API+"/jobs/"+job,{method:"DELETE"});await refresh()}else b.disabled=false}}catch(err){alert(err.message);b.disabled=false}});
$("toggleQueue").addEventListener("click",async()=>{const action=queuePaused?"resume":"pause";$("toggleQueue").disabled=true;try{await request(API+"/queue/"+action,{method:"POST"});await refresh()}catch(e){alert(e.message)}finally{$("toggleQueue").disabled=false}});
loadVoices();loadEngines();refresh();setInterval(refresh,2000);
