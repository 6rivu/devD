"""
CVOLVE PRO — Text-to-Speech
============================
Uses Puter.js (free, no API key needed) for TTS via st.components.v1.html.
Falls back to browser SpeechSynthesis when Puter is unavailable.
"""

import os
import logging


def tts_component_html(question_text: str) -> str:
    """Full HTML page for st.components.v1.html — loads Puter.js and plays speech."""
    escaped = question_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            display: flex; align-items: center; justify-content: center;
            min-height: 50px; background: transparent;
        }}
        .speak-btn {{
            padding: 8px 20px; border-radius: 24px; border: none;
            background: linear-gradient(135deg, #6c5ce7, #a29bfe);
            color: white; font-weight: 600; cursor: pointer; font-size: 14px;
            transition: transform 0.2s; box-shadow: 0 2px 8px rgba(108,92,231,0.3);
        }}
        .speak-btn:hover {{ transform: scale(1.05); }}
        .speak-btn:active {{ transform: scale(0.97); }}
        .speak-btn.playing {{ background: linear-gradient(135deg, #e94560, #c0392b); }}
        #status {{ font-size: 12px; color: #888; margin-top: 4px; min-height: 18px; }}
    </style>
</head>
<body>
    <div style="text-align:center">
        <button class="speak-btn" id="speakBtn">🔊 Play Question</button>
        <div id="status"></div>
    </div>

    <script src="https://js.puter.com/v2/"></script>
    <script>
    (function() {{
        var btn = document.getElementById('speakBtn');
        var status = document.getElementById('status');
        var speaking = false;
        var text = `{escaped}`;

        btn.addEventListener('click', function() {{
            if (speaking) return;
            speaking = true;
            btn.classList.add('playing');
            btn.textContent = '🔊 Playing...';
            status.textContent = '';

            if (typeof puter !== 'undefined' && puter.ai && puter.ai.txt2speech) {{
                puter.ai.txt2speech(text)
                    .then(function(audio) {{
                        audio.play();
                        audio.addEventListener('ended', function() {{
                            speaking = false;
                            btn.classList.remove('playing');
                            btn.textContent = '🔊 Play Question';
                        }});
                    }})
                    .catch(function(err) {{
                        console.error('Puter TTS error:', err);
                        fallbackSpeak(text);
                    }});
            }} else {{
                fallbackSpeak(text);
            }}
        }});

        function fallbackSpeak(t) {{
            if (window.speechSynthesis) {{
                window.speechSynthesis.cancel();
                var u = new SpeechSynthesisUtterance(t);
                u.rate = 0.95; u.pitch = 1.05;
                u.onend = function() {{
                    speaking = false;
                    btn.classList.remove('playing');
                    btn.textContent = '🔊 Play Question';
                }};
                window.speechSynthesis.speak(u);
            }} else {{
                status.textContent = '❌ TTS not available';
                speaking = false;
                btn.classList.remove('playing');
                btn.textContent = '🔊 Play Question';
            }}
        }}
    }})();
    </script>
</body>
</html>
    """


def voice_recorder_component_html(textarea_key: str) -> str:
    """Full HTML page for st.components.v1.html — records voice and sends transcript back."""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            padding: 8px; background: transparent;
        }}
        .container {{ text-align: center; }}
        .btn {{
            padding: 8px 18px; border-radius: 24px; border: none;
            cursor: pointer; font-size: 14px; font-weight: 600;
            transition: all 0.2s; margin: 3px 4px;
        }}
        .btn-record {{ background: linear-gradient(135deg,#e94560,#c0392b); color: #fff; }}
        .btn-stop {{ background: linear-gradient(135deg,#2ecc71,#16a085); color: #fff; display: none; }}
        .btn-send {{ background: linear-gradient(135deg,#3498db,#2980b9); color: #fff; display: none; }}
        .btn:hover {{ transform: scale(1.05); }}
        #status {{ font-size: 13px; color: #555; margin-top: 6px; min-height: 20px; }}
        #transcript {{
            margin-top: 8px; padding: 10px; border-radius: 8px;
            background: #f8f9ff; border: 1px solid #dee2ff;
            font-size: 14px; line-height: 1.5; min-height: 40px;
            white-space: pre-wrap; display: none; text-align: left;
        }}
        .pulse {{ animation: pulse 1s infinite; }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.4}} }}
    </style>
</head>
<body>
    <div class="container">
        <button class="btn btn-record" id="startBtn">🎙️ Start Speaking</button>
        <button class="btn btn-stop" id="stopBtn">⏹️ Stop</button>
        <button class="btn btn-send" id="sendBtn" style="display:none">📋 Use This Answer</button>
        <div id="status"></div>
        <div id="transcript"></div>
    </div>

    <script>
    (function() {{
        var startBtn = document.getElementById('startBtn');
        var stopBtn = document.getElementById('stopBtn');
        var sendBtn = document.getElementById('sendBtn');
        var statusEl = document.getElementById('status');
        var transcriptEl = document.getElementById('transcript');
        var recognition = null;
        var finalText = '';

        var SR = window.SpeechRecognition || window.webkitSpeechRecognition;

        function postToStreamlit(val) {{
            var attempts = 0;
            function trySend() {{
                attempts++;
                try {{
                    if (window.Streamlit && window.Streamlit.setComponentValue) {{
                        window.Streamlit.setComponentValue(val);
                        return true;
                    }}
                }} catch(e) {{}}
                if (attempts < 15) {{
                    setTimeout(trySend, 300);
                }}
                return false;
            }}
            trySend();
        }}

        // Signal component readiness (retry until available)
        function signalReady() {{
            try {{
                if (window.Streamlit && window.Streamlit.setComponentReady) {{
                    window.Streamlit.setComponentReady();
                    return;
                }}
            }} catch(e) {{}}
            setTimeout(signalReady, 200);
        }}
        signalReady();

        startBtn.addEventListener('click', function() {{
            if (!SR) {{
                statusEl.textContent = 'Not supported. Please type instead.';
                return;
            }}
            finalText = '';
            transcriptEl.style.display = 'none';
            sendBtn.style.display = 'none';
            recognition = new SR();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'en-US';

            recognition.onstart = function() {{
                startBtn.style.display = 'none';
                stopBtn.style.display = 'inline-flex';
                statusEl.innerHTML = '<span class="pulse" style="color:#e94560;font-weight:600">🔴 Recording...</span>';
                transcriptEl.style.display = 'block';
                transcriptEl.textContent = '';
            }};

            recognition.onresult = function(event) {{
                var interim = '';
                for (var i = event.resultIndex; i < event.results.length; i++) {{
                    var t = event.results[i][0].transcript;
                    if (event.results[i].isFinal) finalText += t + ' ';
                    else interim += t;
                }}
                transcriptEl.textContent = finalText + interim;
            }};

            recognition.onend = function() {{
                startBtn.style.display = 'inline-flex';
                stopBtn.style.display = 'none';
                var txt = finalText.trim();
                if (txt) {{
                    transcriptEl.textContent = txt;
                    statusEl.innerHTML = '✅ <b>Done.</b> Sending to editor...';
                    sendBtn.style.display = 'none';
                    postToStreamlit(txt);
                }} else {{
                    statusEl.textContent = 'No speech detected. Try again or type your answer.';
                }}
            }};

            recognition.onerror = function(e) {{
                statusEl.textContent = 'Error: ' + e.error;
                startBtn.style.display = 'inline-flex';
                stopBtn.style.display = 'none';
            }};

            recognition.start();
        }});

        stopBtn.addEventListener('click', function() {{
            if (recognition) {{
                recognition.stop();
            }}
        }});

        sendBtn.addEventListener('click', function() {{
            var txt = finalText.trim();
            if (txt) {{
                postToStreamlit(txt);
                statusEl.innerHTML = '✅ <b>Sent!</b>';
                sendBtn.style.display = 'none';
            }}
        }});
    }})();
    </script>
</body>
</html>
    """
