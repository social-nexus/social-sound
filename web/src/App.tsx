import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Download, 
  Mic, 
  Settings, 
  Type, 
  Zap,
  CheckCircle,
  AlertCircle,
  Loader2,
  Waves,
  MessageSquare,
  Smile,
  Frown,
  Ghost,
  ShieldCheck,
  ZapOff,
  Files,
  FileText,
  Trash2,
  SplitSquareHorizontal,
  Upload,
  Clock,
  Volume2,
  Activity,
  Command,
  PlayCircle,
  StopCircle,
  Megaphone,
  BookOpen,
  Radio
} from 'lucide-react';

// Configurações do App
// Servidor local de voz (VoxCPM2) - veja server/server.py
const API = "http://localhost:8000";
const SEGMENTS = new Map(); // url do áudio -> { cues, duration }, usado para montar o SRT

const EMPTY_VOICE = { id: "", label: "Carregando vozes...", gender: "Fem", type: "Aguardando o servidor" };

const TONES = [
  { id: "natural", label: "Natural", icon: <Waves size={14} />, prompt: "" },
  { id: "animado", label: "Animado", icon: <Zap size={14} />, prompt: "high energy, excited, like a YouTuber" },
  { id: "serio", label: "Sério", icon: <ShieldCheck size={14} />, prompt: "serious, formal and professional, documentary narrator" },
  { id: "sussurrado", label: "Sussurro", icon: <Ghost size={14} />, prompt: "whispering, suspenseful and mysterious" },
  { id: "calmo", label: "Calmo", icon: <Smile size={14} />, prompt: "very calm, relaxing and soothing" },
  { id: "dramatico", label: "Dramático", icon: <ZapOff size={14} />, prompt: "dramatic, slow, lots of emotion" },
  { id: "corporativo", label: "Business", icon: <ShieldCheck size={14} />, prompt: "confident news anchor" },
  { id: "anunciante", label: "Anunciante", icon: <Megaphone size={14} />, prompt: "radio announcer, energetic, clear, salesy tone" },
  { id: "storyteller", label: "História", icon: <BookOpen size={14} />, prompt: "captivating storyteller, immersive" },
  { id: "urgente", label: "Urgente", icon: <Radio size={14} />, prompt: "urgent, fast and clear, breaking news reporter" },
  { id: "epico", label: "Épico", icon: <Zap size={14} />, prompt: "deep, epic and impactful, movie trailer narrator" },
];

// Tags suportadas: apenas pausas (o VoxCPM2 não interpreta risadas, suspiros etc.)
const VOICE_COMMANDS = [
  { label: "Pausa Curta", tag: "<short pause>", icon: <Clock size={12} /> },
  { label: "Pausa 1s", tag: "<pause 1s>", icon: <Clock size={12} /> },
  { label: "Pausa Longa", tag: "<long pause>", icon: <Clock size={12} /> },
];

const App = () => {
  const [text, setText] = useState("");
  const [voices, setVoices] = useState([]);
  const [selectedVoice, setSelectedVoice] = useState(EMPTY_VOICE);
  const [extraStyle, setExtraStyle] = useState("");
  const [makeSrt, setMakeSrt] = useState(true);
  const [srtChars, setSrtChars] = useState(42);
  const [paraPause, setParaPause] = useState(0.8);
  const [voiceName, setVoiceName] = useState("");
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const [refFile, setRefFile] = useState(null);
  const [uploadingVoice, setUploadingVoice] = useState(false);
  const [regenId, setRegenId] = useState(null);
  const refInputRef = useRef(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [error, setError] = useState(null);
  const [currentTone, setCurrentTone] = useState(TONES[0]);
  const [searchTerm, setSearchTerm] = useState("");
  const [batchQueue, setBatchQueue] = useState([]); 
  const [charLimit, setCharLimit] = useState(500);
  const [enableSplit, setEnableSplit] = useState(false);
  
  // Estado e Referência para o Preview de Voz
  const [previewState, setPreviewState] = useState({ id: null, status: 'idle' });
  const previewAudioRef = useRef(typeof Audio !== "undefined" ? new Audio() : null);
  const previewUrlRef = useRef(null);
  const previewRequestRef = useRef(0);

  useEffect(() => () => {
    previewAudioRef.current?.pause();
    if (previewAudioRef.current) previewAudioRef.current.src = "";
    for (const url of SEGMENTS.keys()) URL.revokeObjectURL(url);
    SEGMENTS.clear();
  }, []);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
        SEGMENTS.delete(audioUrl);
      }
    };
  }, [audioUrl]);

  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);

  const filteredVoices = voices.filter(v => 
    (v.label || v.id).toLowerCase().includes(searchTerm.toLowerCase()) || 
    v.type.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const buildStyle = () => [currentTone.prompt, extraStyle.trim()].filter(Boolean).join(", ");

  const loadVoices = async () => {
    try {
      const data = await (await fetch(`${API}/voices`)).json();
      const presets = data.presets.map(p => ({ id: `preset:${p.id}`, label: p.label, gender: p.gender, type: p.desc, badge: "Padrão", preset: true }));
      const mine = data.mine.map(m => ({ id: `mine:${m.name}`, label: m.name, gender: "Clone", type: m.has_transcript ? "Clonagem máxima (com transcrição)" : "Clonagem controlável", badge: "Meu áudio", mine: true }));
      const list = [...mine, ...presets];
      setVoices(list);
      setSelectedVoice(prev => list.find(v => v.id === prev.id) || list[0]);
    } catch (e) {
      setError("Servidor de voz offline. Rode o iniciar.bat e aguarde carregar.");
    }
  };

  useEffect(() => { loadVoices(); }, []);

  // Recebe o roteiro enviado pela aba "Roteiro" (guardado no navegador e avisado pela janela com abas)
  useEffect(() => {
    const pegar = () => {
      try {
        const pendente = localStorage.getItem("socialsound:texto-pendente");
        if (pendente) { localStorage.removeItem("socialsound:texto-pendente"); setText(pendente); }
      } catch (e) { /* sem acesso ao armazenamento */ }
    };
    pegar();
    const aoReceber = (e) => { if (e.origin === window.location.origin && e.data && e.data.tipo === "texto-pendente") pegar(); };
    window.addEventListener("message", aoReceber);
    return () => window.removeEventListener("message", aoReceber);
  }, []);

  // Converte qualquer áudio para WAV 24 kHz mono 16 bits (máx. 30 s)
  const toWav24kBlob = async (file) => {
    const ctx = new AudioContext();
    const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
    ctx.close();
    const secs = Math.min(decoded.duration, 30);
    const off = new OfflineAudioContext(1, Math.ceil(secs * 24000), 24000);
    const node = off.createBufferSource();
    node.buffer = decoded;
    node.connect(off.destination);
    node.start();
    const rendered = await off.startRendering();
    const f32 = rendered.getChannelData(0);
    const pcm = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return pcmToWav(pcm, 24000);
  };

  const handleVoiceUpload = async () => {
    if (!refFile) { setError("Escolha um arquivo de áudio da sua voz."); return; }
    setUploadingVoice(true);
    try {
      const blob = await toWav24kBlob(refFile);
      const name = voiceName.trim() || refFile.name.replace(/\.[^.]+$/, "");
      const form = new FormData();
      form.append("file", blob, "voz.wav");
      form.append("name", name);
      form.append("transcript", voiceTranscript);
      const res = await fetch(`${API}/voices`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());
      const saved = await res.json();
      await loadVoices();
      setSelectedVoice({ id: `mine:${saved.name}`, label: saved.name, gender: "Clone", type: voiceTranscript.trim() ? "Clonagem máxima (com transcrição)" : "Clonagem controlável", badge: "Meu áudio", mine: true });
      setRefFile(null); setVoiceName(""); setVoiceTranscript("");
    } catch (err) {
      setError("Falha ao enviar a voz: " + String(err.message).slice(0, 200));
    }
    setUploadingVoice(false);
  };

  const deleteVoice = async (e, voice) => {
    e.stopPropagation();
    try {
      const response = await fetch(`${API}/voices/${encodeURIComponent(voice.label)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${(await response.text()).slice(0, 160)}`);
      await loadVoices();
    } catch (err) {
      setError("Falha ao remover a voz: " + String(err.message || err).slice(0, 180));
    }
  };

  const regeneratePreset = async (e, voice) => {
    e.stopPropagation();
    setRegenId(voice.id);
    try {
      const response = await fetch(`${API}/presets/${voice.id.split(":")[1]}/regenerate`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${(await response.text()).slice(0, 160)}`);
    } catch (err) {
      setError("Não consegui gerar outra versão desta voz: " + String(err.message || err).slice(0, 180));
    } finally {
      setRegenId(null);
    }
  };

  const pcmToWav = (pcmData, sampleRate) => {
    const buffer = new ArrayBuffer(44 + pcmData.length * 2);
    const view = new DataView(buffer);
    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) view.setUint8(offset + i, string.charCodeAt(i));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 32 + pcmData.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, pcmData.length * 2, true);
    for (let i = 0; i < pcmData.length; i++) view.setInt16(44 + i * 2, pcmData[i], true);
    return new Blob([buffer], { type: 'audio/wav' });
  };

  const fmtSrt = (sec) => {
    const ms = Math.round(sec * 1000);
    const p = (n, l = 2) => String(n).padStart(l, "0");
    return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
  };

  const buildSrt = (cues) =>
    cues.map((c, i) => `${i + 1}\n${fmtSrt(c.start)} --> ${fmtSrt(c.end)}\n${c.text}\n`).join("\n");

  const downloadSrt = (content, filename) => {
    const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    triggerDownload(url, filename);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  // Junta as legendas de todos os itens concluídos da fila, em ordem, somando a duração dos áudios anteriores
  const downloadCombinedSrt = () => {
    let offset = 0;
    const all = [];
    for (const item of batchQueue) {
      const seg = item.status === 'done' ? SEGMENTS.get(item.url) : null;
      if (!seg) continue;
      seg.cues.forEach(c => all.push({ start: c.start + offset, end: c.end + offset, text: c.text }));
      offset += seg.duration;
    }
    if (!all.length) { setError("Nenhum item concluído com legenda ainda."); return; }
    downloadSrt(buildSrt(all), `socialsound-${selectedVoice.label || selectedVoice.id}-legenda-unica.srt`);
  };

  const triggerDownload = (url, filename) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const parseSRT = (srtContent) => {
    const lines = srtContent.split('\n');
    let textOnly = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line === '' || /^\d+$/.test(line) || /-->/.test(line)) continue;
      textOnly.push(line);
    }
    return textOnly.join(' ');
  };

  const splitText = (textToSplit, limit) => {
    if (!textToSplit) return [];
    if (!enableSplit || limit <= 0) return [textToSplit];
    
    const chunks = [];
    const sentences = textToSplit.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g) || [textToSplit];
    let currentChunk = "";

    for (const sentence of sentences) {
      const trimmedSentence = sentence.trim();
      if (!trimmedSentence) continue;

      if (trimmedSentence.length > limit) {
         if (currentChunk) {
            chunks.push(currentChunk.trim());
            currentChunk = "";
         }

         const words = trimmedSentence.split(/\s+/);
         let subChunk = "";
         for (const word of words) {
            if ((subChunk + (subChunk ? " " : "") + word).length <= limit) {
                subChunk += (subChunk ? " " : "") + word;
            } else {
                if (subChunk) chunks.push(subChunk.trim());
                subChunk = word;
            }
         }
         if (subChunk) currentChunk = subChunk + " ";
      } else {
          if ((currentChunk + (currentChunk ? " " : "") + trimmedSentence).length <= limit) {
             currentChunk += (currentChunk ? " " : "") + trimmedSentence;
          } else {
             if (currentChunk) chunks.push(currentChunk.trim());
             currentChunk = trimmedSentence + " ";
          }
      }
    }
    
    if (currentChunk.trim()) chunks.push(currentChunk.trim());
    return chunks;
  };

  const insertCommand = (commandTag) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const currentText = text;

    const newText = currentText.substring(0, start) + commandTag + " " + currentText.substring(end);
    setText(newText);

    // Reposiciona o cursor
    setTimeout(() => {
      textarea.selectionStart = textarea.selectionEnd = start + commandTag.length + 1;
      textarea.focus();
    }, 0);
  };

  // Função para Tocar/Pausar a Amostra da Voz
  const releasePreviewUrl = () => {
    const url = previewUrlRef.current;
    if (url) {
      URL.revokeObjectURL(url);
      SEGMENTS.delete(url);
      previewUrlRef.current = null;
    }
  };

  const togglePreview = async (e, voiceId) => {
    e.stopPropagation();
    const requestId = ++previewRequestRef.current;
    if (previewState.id === voiceId && (previewState.status === "playing" || previewState.status === "loading")) {
      if (previewAudioRef.current) {
        previewAudioRef.current.onended = null;
        previewAudioRef.current.pause();
        previewAudioRef.current.src = "";
      }
      releasePreviewUrl();
      setPreviewState({ id: null, status: "idle" });
      return;
    }
    if (previewAudioRef.current) {
      previewAudioRef.current.onended = null;
      previewAudioRef.current.pause();
      previewAudioRef.current.src = "";
    }
    releasePreviewUrl();
    setPreviewState({ id: voiceId, status: "loading" });
    let url = null;
    try {
      url = await apiRequest("Olá! Esta é uma demonstração de como a minha voz soa.", voiceId, "");
      if (requestId !== previewRequestRef.current) {
        URL.revokeObjectURL(url);
        SEGMENTS.delete(url);
        return;
      }
      if (previewAudioRef.current) {
        previewUrlRef.current = url;
        previewAudioRef.current.src = url;
        await previewAudioRef.current.play();
        if (requestId !== previewRequestRef.current) {
          if (previewUrlRef.current === url) releasePreviewUrl();
          return;
        }
        setPreviewState({ id: voiceId, status: "playing" });
        previewAudioRef.current.onended = () => {
          if (previewUrlRef.current === url) releasePreviewUrl();
          if (previewAudioRef.current) previewAudioRef.current.src = "";
          setPreviewState({ id: null, status: "idle" });
        };
      } else {
        URL.revokeObjectURL(url);
        SEGMENTS.delete(url);
      }
    } catch (err) {
      if (url) {
        if (previewUrlRef.current === url) releasePreviewUrl();
        else { URL.revokeObjectURL(url); SEGMENTS.delete(url); }
      }
      if (requestId === previewRequestRef.current) {
        console.error("Erro no preview da voz:", err);
        setPreviewState({ id: null, status: "idle" });
      }
    }
  };
  const apiRequest = async (inputText, voiceId, style) => {
    const form = new FormData();
    form.append("text", inputText);
    form.append("voice", voiceId || "");
    form.append("style", style || "");
    form.append("srt_chars", String(srtChars));
    form.append("para_pause", String(paraPause));
    const response = await fetch(`${API}/tts`, { method: "POST", body: form });
    if (!response.ok) throw new Error(`Status ${response.status}: ${(await response.text()).slice(0, 200)}`);
    const data = await response.json();
    const bin = atob(data.audio);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
    SEGMENTS.set(url, { cues: data.cues, duration: data.duration });
    return url;
  };

  const generateSingle = async () => {
    if (!text.trim()) {
      setError("Por favor, digite algum texto para narrar.");
      return;
    }
    
    if (enableSplit) {
       const chunks = splitText(text, charLimit);
       if (chunks.length > 1) {
           const newItems = chunks.map((chunk, index) => ({
                id: Math.random().toString(36).substr(2, 9),
                name: `Texto_Manual_Parte_${index + 1}`,
                content: chunk,
                status: 'pending'
           }));
           setBatchQueue(prev => [...prev, ...newItems]);
           setText(""); 
           return;
       }
    }

    setIsGenerating(true);
    setError(null);
    setAudioUrl(null);

    try {
      const url = await apiRequest(text, selectedVoice.id, buildStyle());
      setAudioUrl(url);
    } catch (err) {
      setError("Erro na geração: " + (err.message || "verifique se o servidor de voz está rodando."));
      console.error(err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleFileUpload = (e) => {
    const files = Array.from(e.target.files);
    
    files.forEach(file => {
      const isSRT = file.name.toLowerCase().endsWith('.srt');
      const isTXT = file.type === "text/plain" || file.name.toLowerCase().endsWith('.txt');

      if (isTXT || isSRT) {
        const reader = new FileReader();
        reader.onload = (event) => {
          let content = event.target.result;
          if (isSRT) content = parseSRT(content);

          const baseFileName = file.name.replace(/\.(txt|srt)$/i, '');
          const chunks = splitText(content, charLimit);
          
          const newQueueItems = chunks.map((chunk, index) => ({
             id: Math.random().toString(36).substr(2, 9),
             name: chunks.length > 1 ? `${baseFileName}_pt${index + 1}` : baseFileName,
             content: chunk,
             status: 'pending'
          }));

          setBatchQueue(prev => [...prev, ...newQueueItems]);
        };
        reader.readAsText(file);
      }
    });
    
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const batchProcessingRef = useRef(false);

  const processBatch = async () => {
    if (batchProcessingRef.current || batchQueue.length === 0) return;
    batchProcessingRef.current = true;
    setIsGenerating(true);
    // Snapshot the queue so additions made during processing wait for the next run.
    const itemsToProcess = batchQueue.filter(item => item.status !== 'done');

    try {
      for (const queueItem of itemsToProcess) {
        setBatchQueue(prev => prev.map(item => item.id === queueItem.id ? { ...item, status: 'processing' } : item));

        try {
          const url = await apiRequest(queueItem.content, selectedVoice.id, buildStyle());
          const filename = `socialsound-${selectedVoice.label || selectedVoice.id}-${queueItem.name}.wav`;

          triggerDownload(url, filename);
          if (makeSrt && SEGMENTS.get(url)) downloadSrt(buildSrt(SEGMENTS.get(url).cues), filename.slice(0, -4) + ".srt");
          setBatchQueue(prev => prev.map(item => item.id === queueItem.id ? { ...item, status: 'done', url } : item));
        } catch (err) {
          console.error(err);
          setBatchQueue(prev => prev.map(item => item.id === queueItem.id ? { ...item, status: 'error' } : item));
        }

        await new Promise(r => setTimeout(r, 200));
      }
    } finally {
      batchProcessingRef.current = false;
      setIsGenerating(false);
    }
  };

  const removeFromQueue = (id) => {
    const removed = batchQueue.find(item => item.id === id);
    if (removed?.url) {
      URL.revokeObjectURL(removed.url);
      SEGMENTS.delete(removed.url);
    }
    setBatchQueue(prev => prev.filter(item => item.id !== id));
  };
  const clearDoneFromQueue = () => {
    batchQueue.filter(item => item.status === 'done' && item.url).forEach(item => {
      URL.revokeObjectURL(item.url);
      SEGMENTS.delete(item.url);
    });
    setBatchQueue(prev => prev.filter(item => item.status !== 'done'));
  };

  return (
    <div className="min-h-screen bg-nx-bg text-nx-text font-sans pb-20">
      <header className="bg-nx-card/85 backdrop-blur border-b border-nx-line sticky top-0 z-30 shadow-lg shadow-black/30">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-2.5 md:py-0 md:min-h-[76px] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <img src="/icone.png?v=2" alt="" className="w-11 h-11 object-contain shrink-0" />
            <div>
              <h1 className="text-[22px] leading-[1.2] font-black tracking-[-0.02em] text-nx-text mb-0.5">Narração e clonagem de voz</h1>
              <p className="text-sm text-nx-muted">Escreva ou carregue um TXT/SRT, escolha a voz e o tom e gere o áudio já com a legenda.</p>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-4 shrink-0">
             {enableSplit && (
                 <div className="bg-amber-500/10 text-amber-300 border border-amber-500/20 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-tighter flex items-center gap-1">
                    <SplitSquareHorizontal size={12}/> Divisão Ativa ({charLimit}c)
                 </div>
             )}
            <div className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-tighter">
              Download Automático
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-4 md:p-8 grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Lado Esquerdo */}
        <section className="lg:col-span-7 space-y-6">
          
          <div className="bg-nx-card rounded-3xl shadow-xl shadow-black/40 border border-nx-line p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-4">
              <div className="flex items-center gap-2 text-nx-text font-semibold">
                <Type size={18} className="text-nx-purple-soft" />
                <span>Entrada de Texto & Personalização</span>
              </div>
              
              <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center bg-nx-bg p-1.5 rounded-xl border border-nx-line">
                      <label className="flex items-center gap-2 text-xs font-bold text-nx-text cursor-pointer px-2">
                          <input 
                              type="checkbox" 
                              checked={enableSplit}
                              onChange={(e) => setEnableSplit(e.target.checked)}
                              className="w-4 h-4 rounded accent-nx-purple"
                          />
                          Dividir
                      </label>
                      {enableSplit && (
                          <div className="flex items-center border-l border-nx-line pl-2 ml-1">
                              <input 
                                  type="number"
                                  min="50"
                                  max="5000"
                                  value={charLimit}
                                  onChange={(e) => setCharLimit(parseInt(e.target.value) || 500)}
                                  className="w-16 bg-nx-card border border-nx-line rounded px-2 py-1 text-xs text-center outline-none focus:border-nx-purple/60"
                                  title="Limite de Caracteres"
                              />
                          </div>
                      )}
                  </div>

                  <button 
                    onClick={() => fileInputRef.current.click()}
                    className="flex items-center gap-2 text-xs font-bold bg-nx-purple/10 text-nx-purple-soft hover:bg-nx-purple/20 px-4 py-2 rounded-xl transition-colors shadow-sm"
                  >
                    <Upload size={14} />
                    TXT / SRT
                  </button>
                  <input type="file" ref={fileInputRef} onChange={handleFileUpload} multiple accept=".txt,.srt" className="hidden" />
              </div>
            </div>

            {/* Barra de Comandos de Voz */}
            <div className="mb-4 bg-nx-bg border border-nx-line rounded-xl p-3">
              <p className="text-[10px] font-bold text-nx-muted uppercase tracking-wider mb-2 flex items-center gap-1">
                <Command size={12}/> Inserir Direções de Atuação
              </p>
              <div className="flex flex-wrap gap-2">
                {VOICE_COMMANDS.map((cmd, idx) => (
                  <button
                    key={idx}
                    onClick={() => insertCommand(cmd.tag)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-nx-card border border-nx-line text-nx-text text-[11px] font-semibold rounded-lg hover:border-nx-purple/50 hover:text-nx-purple-soft transition-colors shadow-sm"
                    title={`Insere a tag ${cmd.tag} no texto`}
                  >
                    {cmd.icon} {cmd.label}
                  </button>
                ))}
              </div>
            </div>
            
            <textarea
              ref={textareaRef}
              className="w-full h-40 p-5 rounded-2xl border-2 border-nx-line bg-nx-bg focus:ring-4 focus:ring-nx-purple/20 focus:border-nx-purple/60 transition-all outline-none resize-none text-base leading-relaxed text-nx-text placeholder:text-nx-muted/60"
              placeholder="Digite o texto aqui. Use os botões acima para inserir pausas. O tom e o estilo extra ficam no painel ao lado."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />

            {error && <div className="mt-3 text-sm text-red-300 bg-red-500/10 p-3 rounded-lg border border-red-500/30">{error}</div>}

            <div className="mt-4">
              <button 
                onClick={generateSingle}
                disabled={isGenerating || text.length === 0}
                className={`w-full flex items-center justify-center gap-3 py-4 rounded-2xl font-black transition-all transform active:scale-[0.98] shadow-lg ${
                  isGenerating || text.length === 0
                  ? 'bg-white/5 text-nx-muted/60 cursor-not-allowed shadow-none' 
                  : 'bg-gradient-to-r from-nx-purple to-nx-blue text-white hover:brightness-110 shadow-nx-purple/30'
                }`}
              >
                {isGenerating && !batchQueue.some(q => q.status === 'processing') ? (
                  <Loader2 className="animate-spin" size={20} />
                ) : (enableSplit && text.length > charLimit) ? <Files size={20} /> : <Play size={20} fill="currentColor" />}
                
                {(enableSplit && text.length > charLimit) ? 'ENVIAR PARA FILA (DIVIDIDO)' : 'GERAR ÁUDIO'}
              </button>
            </div>
          </div>

          {/* Fila */}
          {batchQueue.length > 0 && (
            <div className="bg-nx-card rounded-3xl shadow-xl shadow-black/40 border border-nx-line overflow-hidden">
              <div className="p-4 sm:p-6 bg-nx-bg border-b border-nx-line flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-center gap-2 font-bold text-nx-text">
                  <Files size={20} className="text-nx-purple-soft" />
                  <span>Fila de Geração ({batchQueue.filter(q => q.status !== 'done').length} pendentes)</span>
                </div>
                <div className="flex gap-2">
                    {makeSrt && (
                      <button onClick={downloadCombinedSrt} className="px-4 py-2 text-xs font-bold text-nx-purple-soft bg-transparent border border-nx-purple/40 rounded-xl hover:bg-nx-purple/10 transition-colors" title="Um único SRT para todos os itens concluídos, na ordem da fila">
                        SRT ÚNICO
                      </button>
                    )}
                    <button onClick={clearDoneFromQueue} disabled={isGenerating} className="px-4 py-2 text-xs font-bold text-nx-muted bg-transparent border border-nx-line rounded-xl hover:bg-white/5 hover:text-nx-text transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                        LIMPAR
                    </button>
                    <button 
                      onClick={processBatch}
                      disabled={isGenerating || batchQueue.every(q => q.status === 'done')}
                      className="bg-nx-purple text-white px-6 py-2 rounded-xl text-sm font-black hover:bg-nx-purple-dark transition-all shadow-md shadow-nx-purple/30 flex items-center gap-2 disabled:opacity-50"
                    >
                    {isGenerating && batchQueue.some(q => q.status === 'processing') ? <Loader2 className="animate-spin" size={16} /> : <Zap size={16} fill="currentColor" />}
                    INICIAR TUDO
                    </button>
                </div>
              </div>
              <div className="max-h-96 overflow-y-auto p-4 space-y-2 custom-scrollbar bg-nx-bg/50">
                {batchQueue.map((item) => (
                  <div key={item.id} className="flex items-center justify-between p-4 bg-nx-card border border-nx-line rounded-2xl shadow-sm">
                    <div className="flex items-center gap-3 w-2/3">
                      <FileText size={20} className={item.status === 'done' ? "text-emerald-400" : item.status === 'processing' ? "text-amber-400" : "text-nx-muted"} />
                      <div className="w-full">
                        <p className="text-sm font-bold text-nx-text truncate w-full" title={item.name}>{item.name}</p>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] text-nx-muted uppercase font-bold tracking-tight">
                              {item.status === 'pending' && 'Aguardando'}
                              {item.status === 'processing' && 'Gerando...'}
                              {item.status === 'done' && 'Concluído'}
                              {item.status === 'error' && 'Falha'}
                            </span>
                            <span className="text-[9px] bg-white/5 text-nx-muted px-1.5 rounded">{item.content.length} chars</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {item.status === 'processing' && <Loader2 className="animate-spin text-amber-400" size={18} />}
                      {item.status === 'done' && <CheckCircle className="text-emerald-400" size={18} />}
                      {item.status === 'error' && <AlertCircle className="text-red-400" size={18} />}
                      {item.status !== 'processing' && (
                        <button onClick={() => removeFromQueue(item.id)} disabled={isGenerating} className="p-2 text-nx-muted/60 hover:text-red-400 bg-white/5 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Player Resultante */}
          {audioUrl && !enableSplit && (
            <div className="bg-nx-card rounded-3xl shadow-2xl shadow-black/40 border-2 border-emerald-500/25 p-6 animate-in zoom-in-95 duration-300">
              <div className="flex items-center gap-2 text-emerald-400 font-bold mb-4 text-sm uppercase tracking-wider">
                <CheckCircle size={18} /> Narração Pronta
              </div>
              <div className="flex flex-col sm:flex-row items-center gap-4">
                <div className="flex-1 w-full bg-nx-bg p-2 rounded-2xl">
                  <audio controls src={audioUrl} className="w-full h-10" />
                </div>
                <button 
                  onClick={() => triggerDownload(audioUrl, `narracao-${selectedVoice.label || selectedVoice.id}.wav`)}
                  className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-4 bg-nx-blue text-white rounded-2xl font-bold hover:bg-nx-blue-dark transition-all shrink-0 shadow-lg"
                >
                  <Download size={18} /> BAIXAR
                </button>
                {makeSrt && SEGMENTS.get(audioUrl) && (
                  <button
                    onClick={() => downloadSrt(buildSrt(SEGMENTS.get(audioUrl).cues), `narracao-${selectedVoice.label || selectedVoice.id}.srt`)}
                    className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-4 bg-nx-purple text-white rounded-2xl font-bold hover:bg-nx-purple-dark transition-all shrink-0 shadow-lg"
                  >
                    <Download size={18} /> BAIXAR SRT
                  </button>
                )}
              </div>
            </div>
          )}
        </section>

        {/* Lado Direito: Configurações */}
        <aside className="lg:col-span-5 space-y-6">
          
          {/* Estilos Globais */}
          <div className="bg-nx-card rounded-3xl shadow-sm border border-nx-line p-6">
            <h3 className="text-xs font-black text-nx-muted uppercase tracking-widest mb-4 flex items-center gap-2">
              <Settings size={14} className="text-nx-purple-soft" /> Diretriz de Tom Global
            </h3>
            <p className="text-xs text-nx-muted mb-3">Isto define o contexto e a personalidade base da narração.</p>
            <input
              type="text"
              placeholder="Estilo extra opcional (ex.: slightly faster, cheerful)"
              value={extraStyle}
              onChange={(e) => setExtraStyle(e.target.value)}
              className="w-full mb-4 px-3 py-2.5 bg-nx-bg border border-nx-line rounded-xl text-xs outline-none focus:ring-2 focus:ring-nx-purple/30"
            />
            <div className="mb-4 p-3 bg-nx-bg border border-nx-line rounded-xl space-y-2">
              <div className="flex items-center gap-2 text-xs text-nx-muted">
                <span>Pausa entre parágrafos (segundos)</span>
                <input
                  type="number" min={0} max={5} step={0.1} value={paraPause}
                  onChange={(e) => setParaPause(Math.max(0, Number(e.target.value) || 0))}
                  className="w-16 px-2 py-1 bg-nx-card border border-nx-line rounded-lg text-xs outline-none"
                />
              </div>
              <label className="flex items-center gap-2 text-xs font-bold text-nx-text cursor-pointer">
                <input type="checkbox" className="accent-nx-purple" checked={makeSrt} onChange={(e) => setMakeSrt(e.target.checked)} /> Gerar legenda SRT junto com o áudio
              </label>
              {makeSrt && (
                <div className="flex items-center gap-2 text-xs text-nx-muted">
                  <span>Máx. de caracteres por legenda</span>
                  <input
                    type="number" min={15} max={120} value={srtChars}
                    onChange={(e) => setSrtChars(Number(e.target.value) || 42)}
                    className="w-16 px-2 py-1 bg-nx-card border border-nx-line rounded-lg text-xs outline-none"
                  />
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-48 overflow-y-auto custom-scrollbar pr-1">
              {TONES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setCurrentTone(t)}
                  className={`flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 transition-all ${
                    currentTone.id === t.id 
                    ? 'border-nx-purple bg-nx-purple/15 text-nx-text shadow-sm shadow-nx-purple/20' 
                    : 'border-transparent bg-nx-bg text-nx-muted hover:border-nx-line hover:text-nx-text'
                  }`}
                >
                  {t.icon}
                  <span className="text-[10px] font-bold uppercase">{t.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Clonar minha voz */}
          <div className="bg-nx-card rounded-3xl shadow-sm border border-nx-line p-6 space-y-3">
            <h3 className="text-xs font-black text-nx-muted uppercase tracking-widest flex items-center gap-2">
              <Mic size={14} className="text-nx-purple-soft" /> Clonar minha voz
            </h3>
            <p className="text-xs text-nx-muted">Use apenas a sua própria voz, ou a de alguém que autorizou. Envie um áudio limpo de 10 a 30 segundos, só com a fala. WAV ou MP3.</p>
            <input
              type="text"
              placeholder="Nome da voz"
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              className="w-full px-3 py-2.5 bg-nx-bg border border-nx-line rounded-xl text-sm outline-none focus:ring-2 focus:ring-nx-purple/30"
            />
            <button
              onClick={() => refInputRef.current.click()}
              className="w-full flex items-center justify-center gap-2 text-xs font-bold bg-nx-purple/10 text-nx-purple-soft hover:bg-nx-purple/20 px-4 py-3 rounded-xl transition-colors"
            >
              <Upload size={14} /> {refFile ? refFile.name : "Escolher meu áudio"}
            </button>
            <input type="file" ref={refInputRef} accept="audio/*" className="hidden" onChange={(e) => setRefFile(e.target.files[0] || null)} />
            <textarea
              placeholder="Transcrição exata do áudio (opcional, mas melhora muito a semelhança)"
              value={voiceTranscript}
              onChange={(e) => setVoiceTranscript(e.target.value)}
              rows={3}
              className="w-full px-3 py-2.5 bg-nx-bg border border-nx-line rounded-xl text-xs outline-none focus:ring-2 focus:ring-nx-purple/30 resize-none"
            />
            <button
              onClick={handleVoiceUpload}
              disabled={uploadingVoice}
              className="w-full bg-nx-blue text-white py-3 rounded-xl text-sm font-black hover:bg-nx-blue-dark transition-all disabled:opacity-50"
            >
              {uploadingVoice ? "ENVIANDO..." : "SALVAR MINHA VOZ"}
            </button>
            <p className="text-[11px] text-nx-muted">Com transcrição a clonagem é máxima, mas o campo de estilo/tom é ignorado nessa voz. Sem transcrição, o tom e o estilo funcionam.</p>
          </div>

          {/* Vozes */}
          <div className="bg-nx-card rounded-3xl shadow-sm border border-nx-line p-6 flex flex-col h-[520px]">
            <div className="mb-4">
              <h3 className="text-xs font-black text-nx-muted uppercase tracking-widest mb-3">Vozes (padrão e a sua)</h3>
              <div className="relative">
                <input 
                  type="text" 
                  placeholder="Buscar voz..."
                  className="w-full pl-9 pr-4 py-2.5 bg-nx-bg border border-nx-line rounded-xl text-sm outline-none focus:ring-2 focus:ring-nx-purple/30 transition-all"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                <Settings size={16} className="absolute left-3 top-3 text-nx-muted/60" />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto pr-2 space-y-2 custom-scrollbar">
              {filteredVoices.map((voice) => (
                <div
                  key={voice.id}
                  onClick={() => setSelectedVoice(voice)}
                  className={`w-full flex flex-col p-3 rounded-xl border-2 transition-all cursor-pointer ${
                    selectedVoice.id === voice.id 
                    ? 'border-nx-purple bg-nx-purple/10 shadow-md shadow-nx-purple/20' 
                    : 'border-transparent bg-nx-bg hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between w-full">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm ${
                        selectedVoice.id === voice.id ? 'bg-gradient-to-br from-nx-purple to-nx-blue text-white' : 'bg-white/10 text-nx-muted'
                      }`}>
                        {(voice.label || voice.id)[0]}
                      </div>
                      <div className="text-left">
                        <p className="font-bold text-sm text-nx-text flex items-center gap-2">
                          {voice.label || voice.id}
                          {voice.badge && <span className="px-1.5 py-0.5 bg-nx-blue/15 text-blue-300 text-[8px] rounded-md uppercase tracking-wider">{voice.badge}</span>}
                        </p>
                        <p className="text-[10px] text-nx-muted font-medium">{voice.type}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className={`px-2.5 py-1 rounded-md text-[9px] font-bold uppercase tracking-wider ${
                        voice.gender === 'Fem' ? 'bg-nx-purple/15 text-nx-purple-soft' : 'bg-nx-blue/15 text-blue-300'
                      }`}>
                        {voice.gender}
                      </div>
                      {voice.mine && (
                        <button onClick={(e) => deleteVoice(e, voice)} className="p-1.5 rounded-full bg-white/5 text-nx-muted/60 hover:text-red-400" title="Remover esta voz">
                          <Trash2 size={14} />
                        </button>
                      )}
                      {voice.preset && (
                        <button onClick={(e) => regeneratePreset(e, voice)} className="px-2 py-1 rounded-full bg-white/5 text-nx-muted hover:text-nx-purple-soft text-xs font-bold" title="Gerar outra versão desta voz (o resultado varia a cada vez)">
                          {regenId === voice.id ? "..." : "↻"}
                        </button>
                      )}
                      <button
                        onClick={(e) => togglePreview(e, voice.id)}
                        className={`p-1.5 rounded-full transition-all ${
                          previewState.id === voice.id 
                            ? 'bg-nx-purple/20 text-nx-purple-soft shadow-sm' 
                            : 'bg-white/5 text-nx-muted hover:bg-white/10 hover:text-nx-purple-soft'
                        }`}
                        title="Ouvir amostra de voz"
                      >
                        {previewState.id === voice.id && previewState.status === 'loading' ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : previewState.id === voice.id && previewState.status === 'playing' ? (
                          <StopCircle size={14} />
                        ) : (
                          <PlayCircle size={14} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              
              {filteredVoices.length === 0 && (
                  <div className="text-center text-nx-muted text-sm mt-10">
                      Nenhuma voz encontrada.
                  </div>
              )}
            </div>
          </div>
        </aside>
      </main>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148,163,184,.25); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #7C3AED; }
      `}} />
    </div>
  );
};

export default App;