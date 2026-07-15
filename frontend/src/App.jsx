import React, { useState, useEffect, useRef } from 'react';
import GestureController from './GestureController';

// API Base URL (served from same host or relative path)
const API_URL = '';

export default function App() {
  // Application State
  const [isListening, setIsListening] = useState(false);
  const [isWokenUp, setIsWokenUp] = useState(false);
  // States: IDLE, LISTENING, PROCESSING, SPEAKING, AWAITING_SELECTION, AWAITING_FULL_DRIVE_SEARCH
  const [assistantState, setAssistantState] = useState('IDLE');
  const [pendingCandidates, setPendingCandidates] = useState([]);
  const [userSpeechText, setUserSpeechText] = useState('Say "AION" to wake me up...');
  const [assistantResponseText, setAssistantResponseText] = useState('');
  const [manualQuery, setManualQuery] = useState('');

  // Refs for Speech & Audio
  const recognitionRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const micStreamRef = useRef(null);
  const speechVolumeRef = useRef(0);
  const silenceTimeoutRef = useRef(null);
  const shouldListenRef = useRef(false);
  const assistantStateRef = useRef('IDLE');

  useEffect(() => {
    assistantStateRef.current = assistantState;
  }, [assistantState]);

  
  // Refs for Visualizer Canvas
  const canvasRef = useRef(null);
  const animationFrameIdRef = useRef(null);
  const particleSystemRef = useRef({
    rotationX: 0.3,
    rotationY: 0,
    rotationZ: 0,
    time: 0,
    rings: [],
    coreNodes: [],
    coreConnections: []
  });

  // ========================================================
  // 1. Initializing 3D Particle Visualizer Data
  // ========================================================
  useEffect(() => {
    const ringCounts = [40, 50, 60, 70];
    const ringRadii = [85, 115, 150, 185];
    const system = particleSystemRef.current;

    // Generate concentric rings of particles
    system.rings = ringRadii.map((radius, rIdx) => {
      const count = ringCounts[rIdx];
      const ringParticles = [];
      for (let i = 0; i < count; i++) {
        const angle = (i / count) * Math.PI * 2;
        ringParticles.push({
          angle: angle,
          baseRadius: radius,
          rIdx: rIdx,
          speedMultiplier: 0.55 + rIdx * 0.1
        });
      }
      return ringParticles;
    });

    // Central geometric node network (nucleus)
    const nodeCount = 12;
    system.coreNodes = [];
    for (let i = 0; i < nodeCount; i++) {
      const phi = Math.acos(-1 + (2 * i) / nodeCount);
      const theta = Math.sqrt(nodeCount * Math.PI) * phi;
      system.coreNodes.push({
        x: 40 * Math.sin(phi) * Math.cos(theta),
        y: 40 * Math.sin(phi) * Math.sin(theta),
        z: 40 * Math.cos(phi),
        origX: 40 * Math.sin(phi) * Math.cos(theta),
        origY: 40 * Math.sin(phi) * Math.sin(theta),
        origZ: 40 * Math.cos(phi)
      });
    }

    // Connect core nodes to form a geometric structure
    system.coreConnections = [];
    for (let i = 0; i < nodeCount; i++) {
      for (let j = i + 1; j < nodeCount; j++) {
        const dx = system.coreNodes[i].x - system.coreNodes[j].x;
        const dy = system.coreNodes[i].y - system.coreNodes[j].y;
        const dz = system.coreNodes[i].z - system.coreNodes[j].z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (dist < 75) {
          system.coreConnections.push([i, j]);
        }
      }
    }
  }, []);

  // ========================================================
  // 2. Visualizer Canvas Render Loop (Reactivity to Microphone)
  // ========================================================
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    
    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    let time = 0;

    const render = () => {
      const width = canvas.width / window.devicePixelRatio;
      const height = canvas.height / window.devicePixelRatio;
      const cx = width / 2;
      const cy = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Volume/Microphone reactivity (RMS amplitude mapped to volume)
      let volume = speechVolumeRef.current; // 0 to 255
      let speed = 0.04;
      let amplitude = 2.0;
      let micInfluence = volume / 10; // normalized mic reactivity

      // Adjust animation settings based on current state
      if (assistantState === 'LISTENING') {
        speed = 0.08;
        amplitude = 8.0 + micInfluence * 15.0;
      } else if (assistantState === 'PROCESSING') {
        speed = 0.18;
        amplitude = 25.0;
      } else if (assistantState === 'SPEAKING') {
        speed = 0.06;
        const envelope = Math.abs(Math.sin(time * 3) * Math.cos(time * 0.7));
        amplitude = 5.0 + envelope * 30.0;
      }

      time += speed;

      // 1. Draw concentric premium light-gray ripple rings
      const ringCount = 3;
      const baseRadii = [60, 95, 130];
      for (let r = 0; r < ringCount; r++) {
        const pulse = Math.sin(time * 0.5 + r * 1.5) * (2.0 + micInfluence * 2.0);
        const radius = baseRadii[r] + pulse;
        
        ctx.strokeStyle = `rgba(9, 9, 11, ${0.04 - r * 0.012})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 2. Draw central glowing gradient background (very subtle)
      const glow = ctx.createRadialGradient(cx, cy, 5, cx, cy, 120 + micInfluence * 20);
      let glowOpacity = 0.03;
      if (assistantState === 'LISTENING') glowOpacity = 0.05 + micInfluence * 0.02;
      else if (assistantState === 'PROCESSING') glowOpacity = 0.08;
      else if (assistantState === 'SPEAKING') glowOpacity = 0.06;

      glow.addColorStop(0, `rgba(9, 9, 11, ${glowOpacity})`);
      glow.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, 140, 0, Math.PI * 2);
      ctx.fill();

      // 3. Draw central pulsing circle (the Core Node)
      const corePulse = Math.sin(time) * 1.5;
      const coreRadius = 14 + corePulse + (micInfluence * 0.5);
      
      // Core fill
      ctx.fillStyle = '#09090b';
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius, 0, Math.PI * 2);
      ctx.fill();

      // Core border outline
      ctx.strokeStyle = '#e4e4e7';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius + 4, 0, Math.PI * 2);
      ctx.stroke();

      // 4. Draw horizontal soundwave oscilloscope lines (Siri-like clean lines)
      const lineCount = 3;
      const lineOpacities = [0.9, 0.45, 0.2];
      const lineWidths = [1.5, 1.0, 0.8];
      const phaseOffsets = [0, Math.PI / 3, -Math.PI / 3];
      const frequencies = [0.035, 0.045, 0.025];
      
      for (let l = 0; l < lineCount; l++) {
        ctx.strokeStyle = `rgba(9, 9, 11, ${lineOpacities[l]})`;
        ctx.lineWidth = lineWidths[l];
        ctx.beginPath();
        
        const lineLength = 220; // width of the wave lines
        const startX = cx - lineLength / 2;
        const endX = cx + lineLength / 2;

        for (let x = startX; x <= endX; x++) {
          const t = (x - startX) / lineLength; // normalized 0 to 1
          // Envelope function to fade the wave at its ends
          const envelope = Math.sin(t * Math.PI); 
          
          const angle = (x - startX) * frequencies[l] - time + phaseOffsets[l];
          const y = cy + Math.sin(angle) * amplitude * envelope;
          
          if (x === startX) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
      }

      animationFrameIdRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
    };
  }, [assistantState]);


  // ========================================================
  // 3. Audio Stream, Noise Gate, & Analyser Setup
  // ========================================================
  const initAudio = async () => {
    if (audioContextRef.current) return;

    try {
      // Noise suppression, echo cancellation, auto gain control enabled!
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 44100
        }
      });
      micStreamRef.current = stream;

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioContextClass();
      const analyserNode = audioCtx.createAnalyser();
      analyserNode.fftSize = 64;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyserNode);

      audioContextRef.current = audioCtx;
      analyserRef.current = analyserNode;

      const bufferLength = analyserNode.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      // Volume/RMS sampling loop for energy threshold (noise filter)
      const checkVolume = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        speechVolumeRef.current = avg; // average frequency volume

        requestAnimationFrame(checkVolume);
      };
      checkVolume();

    } catch (e) {
      console.warn("Could not start audio analyser for mic reactivity:", e);
    }
  };

  // ========================================================
  // 4. Speech Recognition with Noise Gate Filter
  // ========================================================
  const startRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Web Speech API not supported.");
      return;
    }

    if (recognitionRef.current) {
      try {
        recognitionRef.current.start();
      } catch (e) {
        // Recognition already running
      }
      return;
    }

    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-US';

    rec.onstart = () => {
      setIsListening(true);
    };

    rec.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }


      const displayTranscript = interimTranscript || finalTranscript;
      if (displayTranscript) {
        setUserSpeechText(displayTranscript);
      }

      // Wake word "AION" detection when IDLE
      if (!isWokenUp && displayTranscript.toLowerCase().includes('aion')) {
        triggerWakeUp();
        return;
      }

      // Process voice commands when woken up
      if (isWokenUp && finalTranscript.trim()) {
        clearTimeout(silenceTimeoutRef.current);
        // Wait 1 second of silence after user stops speaking to auto-submit query
        silenceTimeoutRef.current = setTimeout(() => {
          const command = finalTranscript.trim();
          const cleanedCommand = command.replace(/aion/gi, '').trim();
          if (cleanedCommand) {
            sendApiCommand(cleanedCommand);
          }
        }, 1000);
      }
    };

    rec.onend = () => {
      setIsListening(false);
      // Restart speech recognition automatically if it should be active and assistant is not speaking
      if (shouldListenRef.current && assistantStateRef.current !== 'SPEAKING') {
        try {
          rec.start();
        } catch (e) {
          // Already running
        }
      }
    };

    rec.onerror = (e) => {
      console.error("Speech Recognition Error:", e.error);
      if (e.error === 'not-allowed') {
        setUserSpeechText("Mic permission denied.");
        setIsListening(false);
        setIsWokenUp(false);
        shouldListenRef.current = false;
      }
    };


    recognitionRef.current = rec;
    rec.start();
  };

  const stopRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  };

  const triggerWakeUp = () => {
    setIsWokenUp(true);
    setAssistantState('LISTENING');
    setUserSpeechText("AION is listening...");
    speakResponse("Yes? How can I help you?");
  };

  // ========================================================
  // 5. Speech Synthesis (Audio Output)
  // ========================================================
  const speakResponse = (text) => {
    const synth = window.speechSynthesis;
    if (!synth) return;

    synth.cancel(); // Cancel any current utterances

    const utterance = new SpeechSynthesisUtterance(text);

    
    // Select clean default browser voices (e.g. Google, Cortana)
    const voices = synth.getVoices();
    const cleanVoice = voices.find(v => v.name.includes('Google') || v.name.includes('Natural') || v.name.includes('Zira')) || voices[0];
    if (cleanVoice) {
      utterance.voice = cleanVoice;
    }

    utterance.onstart = () => {
      stopRecognition();
      setAssistantState('SPEAKING');
      setAssistantResponseText(text);
    };

    utterance.onend = () => {
      // Re-enter listening state after finishing response if allowed
      setAssistantState('LISTENING');
      if (shouldListenRef.current) {
        startRecognition();
      }
    };

    utterance.onerror = (e) => {
      console.error("Speech Synthesis Error:", e);
      setAssistantState('LISTENING');
      if (shouldListenRef.current) {
        startRecognition();
      }
    };


    synth.speak(utterance);
  };

  // ========================================================
  // 6. API Post Requests to Python server
  // ========================================================
  const sendApiCommand = async (commandText) => {
    if (!commandText) return;

    console.log(`Sending command to backend: '${commandText}'`);
    setAssistantState('PROCESSING');

    try {
      const res = await fetch(`${API_URL}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: commandText })
      });

      if (!res.ok) {
        throw new Error(`Server returned error: ${res.statusText}`);
      }

      const data = await res.json();
      handleBackendData(data);

    } catch (err) {
      console.error("API Connection Error:", err);
      setUserSpeechText("Connection error.");
      speakResponse("Sorry, I had trouble talking to the backend system.");
    }
  };

  const handleBackendData = (data) => {
    const text = data.response || '';
    const nextState = data.state;
    const candidates = data.candidates || [];

    setPendingCandidates(candidates);

    // Filter out the numbered file list from screen bubble & voice synthesis if candidates card is displayed
    let displayResponse = text;
    if (candidates.length > 0) {
      const lines = text.split('\n');
      const intro = lines[0] || ""; // e.g. "I found 4 files."
      const outro = lines[lines.length - 1] || ""; // e.g. "Which one should I open?"
      displayResponse = `${intro} ${outro}`;
    }

    speakResponse(displayResponse);
    setAssistantResponseText(displayResponse);

    if (nextState === 'IDLE') {
      setIsWokenUp(false);
      setAssistantState('IDLE');
      setUserSpeechText('Say "AION" to wake me up...');
    } else {
      setAssistantState(nextState);
    }
  };



  // ========================================================
  // 7. Interactive Bindings & Fallbacks
  // ========================================================
  const toggleVoice = async () => {
    // 1. Verify Browser Support & Secure Context (HTTPS requirement for mobile)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

    if (!SpeechRecognition || !hasMediaDevices) {
      const currentOrigin = `${window.location.protocol}//${window.location.host}`;
      let errorMsg = "Microphone access or Speech Recognition is not supported on this browser.";

      if (!window.isSecureContext) {
        errorMsg = `Web Speech API requires HTTPS (a Secure Context) on mobile devices!\n\n` +
          `To fix this on your phone:\n` +
          `1. Open Chrome on your phone and go to:\n` +
          `   chrome://flags/#unsafely-treat-insecure-origin-as-secure\n\n` +
          `2. Add this origin to the list:\n` +
          `   ${currentOrigin}\n\n` +
          `3. Change the dropdown status to "Enabled" and tap "Relaunch" at the bottom.\n\n` +
          `Alternatively, run over HTTPS using tunnel tools like ngrok or ADB reverse port forwarding.`;
      }

      alert(errorMsg);
      setUserSpeechText("HTTPS / Secure context required.");
      return;
    }

    await initAudio();
    if (isListening) {
      shouldListenRef.current = false;
      stopRecognition();
      setIsWokenUp(false);
      setAssistantState('IDLE');
      setUserSpeechText('Say "AION" to wake me up...');
    } else {
      shouldListenRef.current = true;
      setIsWokenUp(true);
      setAssistantState('LISTENING');
      setUserSpeechText("AION is listening...");
      startRecognition();
      speakResponse("How can I help you?");
    }
  };


  const handleFormSubmit = (e) => {
    e.preventDefault();
    if (manualQuery.trim()) {
      setIsWokenUp(true);
      setUserSpeechText(`You searched: "${manualQuery.trim()}"`);
      sendApiCommand(manualQuery.trim());
      setManualQuery('');
    }
  };

  const selectCandidate = (index) => {
    sendApiCommand(index.toString());
  };

  // Auto-fetch speech synthesis voice list cache
  useEffect(() => {
    if (window.speechSynthesis) {
      window.speechSynthesis.getVoices();
    }
  }, []);



  // Icon Mapping
  const getFileIcon = (ext) => {
    const extLower = ext.toLowerCase().replace('.', '');
    const docTypes = ['doc', 'docx', 'pdf', 'txt', 'rtf', 'odt'];
    const sheetTypes = ['xls', 'xlsx', 'csv'];
    const slideTypes = ['ppt', 'pptx'];
    const codeTypes = ['py', 'js', 'ts', 'html', 'css', 'cpp', 'c', 'h', 'java', 'sql', 'json', 'xml'];
    const imageTypes = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp'];
    const audioTypes = ['mp3', 'wav', 'ogg', 'm4a', 'flac'];
    const videoTypes = ['mp4', 'mkv', 'avi', 'mov', 'wmv'];
    const zipTypes = ['zip', 'rar', '7z', 'tar', 'gz'];
    
    if (docTypes.includes(extLower)) return '📄';
    if (sheetTypes.includes(extLower)) return '📊';
    if (slideTypes.includes(extLower)) return '📈';
    if (codeTypes.includes(extLower)) return '💻';
    if (imageTypes.includes(extLower)) return '🖼️';
    if (audioTypes.includes(extLower)) return '🎵';
    if (videoTypes.includes(extLower)) return '🎥';
    if (zipTypes.includes(extLower)) return '📦';
    if (extLower === 'exe') return '⚙️';
    return '📁';
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="logo">
          <span className="logo-text">A I O N</span>
          <span className="logo-subtext">FILE INTELLIGENCE</span>
        </div>
        <div className="status-badge-container">
          <span className={`status-dot ${assistantState.toLowerCase()}`}></span>
          <span className="status-text">{assistantState}</span>
        </div>
      </header>

      {/* Main Visualizer Area */}
      <main className="visualizer-section">
        {/* User Voice Transcripts */}
        <div className="feedback-container">
          <div className={`user-speech-bubble ${isListening ? 'active-speech' : ''}`}>
            {userSpeechText}
          </div>
          <div className="assistant-response-bubble">
            {assistantResponseText}
          </div>
        </div>

        <div className="visualizer-wrapper">
          <canvas ref={canvasRef} id="canvas-visualizer"></canvas>
          <div className="center-glow"></div>
        </div>
      </main>


      {/* Interactive Glassmorphic File List */}
      <section className={`results-panel ${pendingCandidates.length > 0 ? '' : 'hidden'}`}>
        <div className="results-header">
          <h2>Matching Files</h2>
          <span className="results-count">{pendingCandidates.length} files found</span>
        </div>
        <div className="results-list">
          {pendingCandidates.map((cand, idx) => (
            <div 
              key={idx} 
              className="result-item"
              onClick={() => selectCandidate(idx + 1)}
            >
              <div className="result-info">
                <span className="result-index">{idx + 1}</span>
                <span className="result-icon">{getFileIcon(cand.extension)}</span>
                <div className="result-details">
                  <span className="result-name" title={cand.filename}>{cand.filename}</span>
                  <span className="result-path" title={cand.path}>{cand.path}</span>
                </div>
              </div>
              <div className="result-meta">
                <span className="result-score">Score: {Math.round(cand.score)}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="results-help">
          Say <span className="voice-cmd">"first one"</span>, <span className="voice-cmd">"open 3"</span>, or say <span className="voice-cmd">"cancel"</span> to abort.
        </div>
      </section>

      {/* Bottom Footer Controls */}
      <footer className="control-bar">
        <div className="mic-toggle-wrapper">
          <button 
            onClick={toggleVoice} 
            className={`mic-btn ${isListening ? 'active' : ''}`}
            title={isListening ? "Stop voice assistant" : "Activate voice assistant"}
          >
            {isListening ? (
              <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="24" height="24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" fill="currentColor"/>
              </svg>
            )}
          </button>
          <span id="listening-tip">
            {isListening ? 'Active | Click ✕ to stop' : 'Click mic to speak'}
          </span>
        </div>


        {/* Manual query fallback */}
        <form onSubmit={handleFormSubmit} className="query-form">
          <input 
            type="text" 
            value={manualQuery}
            onChange={(e) => setManualQuery(e.target.value)}
            placeholder="Type a file command (e.g. open resume)..."
            autoComplete="off"
          />
          <button type="submit" className="send-btn">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/>
            </svg>
          </button>
        </form>
      </footer>
      
      {/* Gesture Control Module */}
      <GestureController />
    </div>
  );
}
