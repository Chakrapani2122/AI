import streamlit as st
import os
import configparser
import google.generativeai as genai
import tempfile
import base64
import io
import speech_recognition as sr
from streamlit.runtime.scriptrunner import add_script_run_ctx
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, WebRtcMode
import av
import whisper
import re
import time

st.set_page_config(page_title="AI", layout="centered")

st.title("AI!")

page = "Gemini AI Chat"

config = configparser.ConfigParser()
config.read("config.ini")

# Custom CSS to fix the input area at the bottom and make the response area scrollable
st.markdown('''
    <style>
    .fixed-input-container {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100vw;
        background: white;
        z-index: 100;
        padding: 1rem 2rem 1rem 2rem;
        box-shadow: 0 -2px 8px rgba(0,0,0,0.05);
    }
    .scrollable-response {
        max-height: 65vh;
        overflow-y: auto;
        margin-bottom: 120px;
        padding: 1rem 2rem 1rem 2rem;
    }
    /* Hide Streamlit footer and padding */
    footer {visibility: hidden;}
    .block-container {padding-bottom: 0px;}
    </style>
''', unsafe_allow_html=True)

response_placeholder = st.container()

# Chat history and session state setup
if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = []
if 'chat_session' not in st.session_state:
    st.session_state['chat_session'] = None
# Add a key for the prompt input to allow clearing
if 'prompt_key' not in st.session_state:
    st.session_state['prompt_key'] = 0
# Initialize resume_text if not present
if 'resume_text' not in st.session_state:
    st.session_state['resume_text'] = ""

def sanitize_input(text):
    # Remove potentially dangerous characters and excessive whitespace
    return re.sub(r'[\r\n\t]+', ' ', text).strip()

# Improved error handling and user feedback for voice and chat features
try:
    # Resume input section (at the top)
    st.markdown('### Candidate Resume')
    resume_input = st.text_area('Paste the candidate\'s resume here:', value=st.session_state['resume_text'], height=200, key='resume_input')
    sanitized_resume = sanitize_input(resume_input)
    if sanitized_resume != st.session_state['resume_text']:
        st.session_state['resume_text'] = sanitized_resume
        st.session_state['chat_history'] = []
        st.session_state['chat_session'] = None

    # If resume is provided and chat session not started, start a new chat session with the resume as context
    if st.session_state['resume_text'] and st.session_state['chat_session'] is None:
        api_key = config.get("gemini", "api_key", fallback=None)
        if api_key and api_key != "your_actual_api_key_here":
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                st.session_state['chat_session'] = model.start_chat(history=[
                    {"role": "user", "parts": [
                        "Act as an interview candidate responding to questions in a job interview. Use the contents of the resume I provide as your background. I will ask you interview questions one at a time, and you will answer each question as if you are the candidate, primarily based on the information in the resume. Your answers must be in well-structured paragraphs, using simple to intermediate English. Keep the language clear, confident, and professional, without using overly complex vocabulary. If a question asks for something not directly mentioned in the resume, you may provide a reasonable and relevant answer in line with the resume tone and context. Wait for the next question after each answer. Answers should be short and in a human-like tone to make it sound natural and conversational. Answer in simple terms.\n"
                        f"Resume: {st.session_state['resume_text']}"
                    ]}
                ])
            except Exception as e:
                st.error(f"Failed to initialize chat session: {e}")
        else:
            st.warning("API key missing or invalid. Please check your config.ini.")

    # Add instructions for voice feature and permissions
    st.markdown('''
    <div style="margin-bottom: 1em; color: #555;">
    <b>Tip:</b> To use the voice feature, allow microphone access in your browser when prompted. Click <b>Start Listening</b>, speak your question, then click <b>Stop</b>. Your question will be transcribed and submitted automatically.
    </div>
    ''', unsafe_allow_html=True)

    # Accessibility: Show browser/mic permission tip for macOS users
    if os.uname().sysname == 'Darwin':
        st.info('If you have trouble with the mic, go to System Settings > Privacy & Security > Microphone and ensure your browser is allowed. Also, allow mic access in your browser when prompted.')

    def render_chat_history():
        chat_container = st.container()
        with chat_container:
            # Conversational bubble UI for chat history
            st.markdown('<div class="scrollable-response" id="chat-scroll">', unsafe_allow_html=True)
            for i, entry in enumerate(st.session_state['chat_history']):
                if entry['role'] == 'user':
                    st.markdown(f"""
                    <div style='display:flex;justify-content:flex-end;margin-bottom:4px;'>
                        <div style='background:#DCF8C6;padding:1em 1.2em;border-radius:18px 18px 2px 18px;max-width:70%;box-shadow:0 1px 2px #eee;'>
                            <b>You:</b> {entry['text']}
                        </div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style='display:flex;justify-content:flex-start;margin-bottom:8px;'>
                        <div style='background:#F1F0F0;padding:1em 1.2em;border-radius:18px 18px 18px 2px;max-width:70%;box-shadow:0 1px 2px #eee;'>
                            <b>AI:</b> {entry['text']}
                        </div>
                    </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("""
                <script>
                var chatDiv = window.parent.document.getElementById('chat-scroll');
                if (chatDiv) { chatDiv.scrollTop = chatDiv.scrollHeight; }
                </script>
            """, unsafe_allow_html=True)

    def stream_response(full_text, role='model'):
        display_text = ''
        for char in full_text:
            display_text += char
            # Update the chat history with the streaming text
            if st.session_state['chat_history'] and st.session_state['chat_history'][-1]['role'] == role:
                st.session_state['chat_history'][-1]['text'] = display_text
            else:
                st.session_state['chat_history'].append({'role': role, 'text': display_text})
            time.sleep(0.01)
            st.experimental_rerun()

    def submit_question(question):
        st.session_state['chat_history'].append({'role': 'user', 'text': question})
        try:
            with st.spinner("thinking..."):
                response = st.session_state['chat_session'].send_message(question)
            # Streaming/typer animation for model response
            stream_response(response.text)
        except Exception as e:
            st.session_state['chat_history'].append({'role': 'model', 'text': f"Error: {e}"})
        st.session_state['prompt_key'] += 1
        st.experimental_rerun()

    # Display chat history with auto-scroll to latest message
    render_chat_history()

    st.markdown('<div style="height:50px;"></div>', unsafe_allow_html=True)  # Increased spacer to push input further down

    # Fixed input area at the bottom with keyboard shortcut support
    st.markdown('<div class="fixed-input-container">', unsafe_allow_html=True)
    cols = st.columns([8, 1])
    with cols[0]:
        prompt_input = st.text_area(
            "Enter your interview question:",
            key=f"text_prompt_{st.session_state['prompt_key']}",
            label_visibility="collapsed",
            height=40,
            placeholder="Type your question and press Enter to send. Shift+Enter for a new line."
        )
    with cols[1]:
        send = st.button("📤", use_container_width=True, help="Send")
    st.markdown('''
    <script>
    const textarea = window.parent.document.querySelector('textarea[data-testid="stTextArea"]');
    if (textarea) {
      textarea.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          const sendBtn = window.parent.document.querySelector('button[title="Send"]');
          if (sendBtn) sendBtn.click();
        }
      });
    }
    </script>
    ''', unsafe_allow_html=True)

    # --- ChatGPT-like Voice Input: Single Toggle Mic Button ---
    if 'is_listening' not in st.session_state:
        st.session_state['is_listening'] = False
    if 'audio_ready' not in st.session_state:
        st.session_state['audio_ready'] = False

    st.markdown('### 🎤 Voice Input (Click mic to start/stop)')
    mic_col = st.columns([1])[0]
    if not st.session_state['is_listening']:
        if mic_col.button('🎤 Start Listening', key='mic_toggle_start'):
            st.session_state['is_listening'] = True
            st.session_state['audio_ready'] = False
            if 'audio_ctx' in st.session_state and st.session_state['audio_ctx'] and st.session_state['audio_ctx'].audio_processor:
                st.session_state['audio_ctx'].audio_processor.frames = []
    else:
        if mic_col.button('⏹️ Stop', key='mic_toggle_stop'):
            st.session_state['is_listening'] = False
            st.session_state['audio_ready'] = True
        st.info('🟢 Listening... Speak now!')

    class AudioProcessor(AudioProcessorBase):
        def __init__(self):
            self.frames = []
        def recv_audio(self, frame: av.AudioFrame) -> av.AudioFrame:
            self.frames.append(frame)
            return frame
        def get_wav_bytes(self):
            if not self.frames:
                return None
            import numpy as np
            import wave
            import io
            samples = np.concatenate([frame.to_ndarray() for frame in self.frames])
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(samples.tobytes())
            return buf.getvalue()

    ctx = webrtc_streamer(
        key="audio",
        mode=WebRtcMode.SENDRECV,
        audio_receiver_size=1024,
        video_receiver_size=0,
        audio_processor_factory=AudioProcessor,
        async_processing=False,
        media_stream_constraints={"audio": True, "video": False},
    )
    st.session_state['audio_ctx'] = ctx

    @st.cache_resource(show_spinner="Loading Whisper model...")
    def get_whisper_model():
        return whisper.load_model('base')

    if st.session_state['audio_ready'] and ctx and ctx.audio_processor and ctx.audio_processor.frames:
        st.session_state['audio_ready'] = False
        wav_bytes = ctx.audio_processor.get_wav_bytes()
        if wav_bytes:
            st.info('🔄 Transcribing...')
            import io
            try:
                model = get_whisper_model()
                audio_buffer = io.BytesIO(wav_bytes)
                result = model.transcribe(audio_buffer)
                text = sanitize_input(result['text'].strip())
                if text:
                    st.success(f"Transcribed: {text}")
                    st.session_state[f'text_prompt_{st.session_state["prompt_key"]}'] = text
                    if text and st.session_state['chat_session']:
                        submit_question(text)
                else:
                    st.warning("No speech detected. Please try again.")
            except Exception as e:
                st.error(f"Could not transcribe audio: {e}")
            ctx.audio_processor.frames = []
    # Download chat transcript button
    if st.session_state['chat_history']:
        import json
        transcript = '\n'.join([
            f"Q: {entry['text']}" if entry['role']=='user' else f"A: {entry['text']}" for entry in st.session_state['chat_history']
        ])
        st.download_button(
            label="Download Chat Transcript",
            data=transcript,
            file_name="chat_transcript.txt",
            mime="text/plain"
        )

    # Add Regenerate, Edit & Resend, and Clear Chat buttons
    button_col1, button_col2, button_col3 = st.columns([1,1,1])
    with button_col1:
        if st.button('🔄', disabled=not st.session_state['chat_history'] or st.session_state['chat_history'][-1]['role'] != 'user'):
            if st.session_state['chat_history']:
                last_user_msg = [msg['text'] for msg in reversed(st.session_state['chat_history']) if msg['role']=='user']
                if last_user_msg:
                    submit_question(last_user_msg[0])
    with button_col2:
        if st.button('✏️', disabled=not st.session_state['chat_history'] or st.session_state['chat_history'][-1]['role'] != 'user'):
            if st.session_state['chat_history']:
                last_user_msg = [msg['text'] for msg in reversed(st.session_state['chat_history']) if msg['role']=='user']
                if last_user_msg:
                    edited = st.text_area('Edit your last question:', last_user_msg[0], key='edit_resend')
                    if st.button('Resend', key='resend_btn'):
                        submit_question(edited)
    with button_col3:
        if st.button('🗑️'):
            st.session_state['chat_history'] = []
            st.session_state['chat_session'] = None
            st.session_state['prompt_key'] = 0
            st.experimental_rerun()
except Exception as e:
    st.error(f"An unexpected error occurred: {e}")
