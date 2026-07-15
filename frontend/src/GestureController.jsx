import React, { useEffect, useRef, useState, useCallback } from 'react';
import { GestureRecognizer, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision';
import './GestureController.css';

export default function GestureController() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [isWebcamActive, setIsWebcamActive] = useState(false);
  const [gestureRecognizer, setGestureRecognizer] = useState(null);
  
  const lastVideoTime = useRef(-1);
  const lastActionTime = useRef(0);
  const handHistory = useRef([]);
  const workerRef = useRef(null);

  // Initialize Gesture Recognizer
  useEffect(() => {
    const loadModel = async () => {
      try {
        const vision = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm"
        );
        const recognizer = await GestureRecognizer.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath: "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
            delegate: "GPU"
          },
          runningMode: "VIDEO",
          numHands: 1
        });
        setGestureRecognizer(recognizer);
        console.log("Gesture recognizer loaded!");
      } catch (e) {
        console.error("Error loading MediaPipe:", e);
      }
    };
    loadModel();
  }, []);

  const sendGestureCommand = async (action) => {
    const now = Date.now();
    // Throttle commands to 1 second to prevent accidental double-swipes
    if (now - lastActionTime.current < 1000) return;
    lastActionTime.current = now;
    
    console.log("Gesture Detected:", action);
    try {
      await fetch("http://localhost:8520/api/gesture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action })
      });
    } catch (e) {
      console.error(e);
    }
  };

  const predictWebcam = useCallback(() => {
    if (!videoRef.current || !gestureRecognizer || !canvasRef.current) return;
    
    let startTimeMs = performance.now();
    // Only process if we have a new video frame
    if (videoRef.current.currentTime !== lastVideoTime.current) {
      lastVideoTime.current = videoRef.current.currentTime;
      
      try {
        const results = gestureRecognizer.recognizeForVideo(videoRef.current, startTimeMs);
        
        const canvasCtx = canvasRef.current.getContext("2d");
        canvasCtx.save();
        canvasCtx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
        
        if (results.landmarks && results.landmarks.length > 0) {
          // Draw landmarks
          const drawingUtils = new DrawingUtils(canvasCtx);
          for (const landmarks of results.landmarks) {
            drawingUtils.drawConnectors(landmarks, GestureRecognizer.HAND_CONNECTIONS, {
              color: "#00FF00",
              lineWidth: 2
            });
            drawingUtils.drawLandmarks(landmarks, { color: "#FF0000", lineWidth: 1 });
          }

          // Gesture Logic
          const categoryName = results.gestures.length > 0 ? results.gestures[0][0].categoryName : "None";
          const wrist = results.landmarks[0][0]; 
          const now = Date.now();
          
          handHistory.current.push({ x: wrist.x, y: wrist.y, time: now });
          handHistory.current = handHistory.current.filter(h => now - h.time < 500); // 500ms window
          
          if (handHistory.current.length > 5) {
            const first = handHistory.current[0];
            const last = handHistory.current[handHistory.current.length - 1];
            const dx = last.x - first.x;
            const dy = last.y - first.y;
            
            // Using 0.15 threshold for movement
            if (categoryName === "Open_Palm") {
              if (dx < -0.15) {
                sendGestureCommand("swipe_right");
                handHistory.current = [];
              } else if (dx > 0.15) {
                sendGestureCommand("swipe_left");
                handHistory.current = [];
              }
            } else if (categoryName === "Pointing_Up") {
              if (dy < -0.15) {
                sendGestureCommand("scroll_up");
                handHistory.current = [];
              } else if (dy > 0.15) {
                sendGestureCommand("scroll_down");
                handHistory.current = [];
              }
            }
          }
        } else {
          handHistory.current = []; // reset if hand lost
        }
        canvasCtx.restore();
      } catch (err) {
        // MediaPipe might throw if video isn't fully ready
      }
    }
  }, [gestureRecognizer]);

  // Use a Web Worker to drive the loop. Web Workers are NOT throttled when the tab is in the background!
  useEffect(() => {
    if (isWebcamActive) {
      // Create an inline web worker
      const workerCode = `
        let timer = null;
        self.onmessage = function(e) {
          if (e.data === 'start') {
            timer = setInterval(() => self.postMessage('tick'), 33); // ~30fps
          } else if (e.data === 'stop') {
            clearInterval(timer);
          }
        };
      `;
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      workerRef.current = new Worker(URL.createObjectURL(blob));
      
      workerRef.current.onmessage = () => {
        predictWebcam();
      };
      
      workerRef.current.postMessage('start');
      
    } else {
      if (workerRef.current) {
        workerRef.current.postMessage('stop');
        workerRef.current.terminate();
        workerRef.current = null;
      }
    }
    
    return () => {
      if (workerRef.current) {
        workerRef.current.postMessage('stop');
        workerRef.current.terminate();
        workerRef.current = null;
      }
    };
  }, [isWebcamActive, predictWebcam]);

  const toggleWebcam = async () => {
    if (!isWebcamActive) {
      if (!gestureRecognizer) {
        alert("Please wait, model is still loading...");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.addEventListener("loadeddata", () => {
             setIsWebcamActive(true);
          });
        }
      } catch (err) {
        console.error("Camera error:", err);
      }
    } else {
      // Stop webcam
      setIsWebcamActive(false);
      if (videoRef.current && videoRef.current.srcObject) {
        const tracks = videoRef.current.srcObject.getTracks();
        tracks.forEach(track => track.stop());
        videoRef.current.srcObject = null;
      }
    }
  };

  return (
    <div className={`gesture-container ${isWebcamActive ? 'active' : ''}`}>
      <button className="gesture-toggle" onClick={toggleWebcam}>
        {isWebcamActive ? "Close Camera" : "Gesture Mode"}
      </button>
      
      <div className="video-wrapper" style={{ display: isWebcamActive ? 'block' : 'none' }}>
        <video 
          ref={videoRef} 
          autoPlay 
          playsInline 
          style={{ width: '320px', height: '240px', transform: 'scaleX(-1)' }}
        ></video>
        <canvas 
          ref={canvasRef} 
          className="output_canvas" 
          width="320" 
          height="240" 
          style={{ position: 'absolute', top: 0, left: 0, transform: 'scaleX(-1)' }}
        ></canvas>
        <div className="gesture-help">
          <p>✋ Open Palm + Swipe Left/Right = Switch Window</p>
          <p>☝️ Pointing Up + Swipe Up/Down = Scroll</p>
        </div>
      </div>
    </div>
  );
}
