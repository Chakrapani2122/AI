import streamlit as st
import os
import configparser
import google.generativeai as genai

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

# Resume input section (at the top)
st.markdown('### Candidate Resume')
resume_input = st.text_area('Paste the candidate\'s resume here:', value=st.session_state['resume_text'], height=200, key='resume_input')
if resume_input != st.session_state['resume_text']:
    st.session_state['resume_text'] = resume_input
    st.session_state['chat_history'] = []
    st.session_state['chat_session'] = None

# If resume is provided and chat session not started, start a new chat session with the resume as context
if st.session_state['resume_text'] and st.session_state['chat_session'] is None:
    api_key = config.get("gemini", "api_key", fallback=None)
    if api_key and api_key != "your_actual_api_key_here":
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        # Start chat with system prompt (resume as context)
        st.session_state['chat_session'] = model.start_chat(history=[
            {"role": "user", "parts": [
                "Act as an interview candidate responding to questions in a job interview. Use the contents of the resume I provide as your background. I will ask you interview questions one at a time, and you will answer each question as if you are the candidate, primarily based on the information in the resume. Your answers should be in well-structured paragraphs, using simple to intermediate English. Keep the language clear, confident, and professional, without using overly complex vocabulary. The answers should be detailed enough to cover all relevant parts of the resume that match the question. If a question asks for something not directly mentioned in the resume, you may provide a reasonable and relevant answer in line with the resume’s tone and context. Wait for the next question after each answer. Answers should be short and in a human-like tone to make it sound natural and conversational.\n"
                f"Resume: {st.session_state['resume_text']}"
            ]}
        ])

# Display chat history
st.markdown('<div class="scrollable-response">', unsafe_allow_html=True)
for entry in st.session_state['chat_history']:
    if entry['role'] == 'user':
        st.markdown(f"<div style='text-align:right; margin-bottom:4px;'><b>Q:</b> {entry['text']}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='background:none;padding:1em;border-radius:8px;border:1px solid #eee; margin-bottom:8px;'><b>A:</b> {entry['text']}</div>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div style="height:50px;"></div>', unsafe_allow_html=True)  # Increased spacer to push input further down

# Fixed input area at the bottom
st.markdown('<div class="fixed-input-container">', unsafe_allow_html=True)
cols = st.columns([8, 1])
with cols[0]:
    prompt_input = st.text_input("Enter your interview question:", key=f"text_prompt_{st.session_state['prompt_key']}", label_visibility="collapsed")
with cols[1]:
    send = st.button("📤", use_container_width=True, help="Send")
st.markdown('</div>', unsafe_allow_html=True)

# Handle question submission
if (send or prompt_input) and st.session_state['chat_session']:
    question = prompt_input.strip()
    if question:
        st.session_state['chat_history'].append({'role': 'user', 'text': question})
        try:
            with st.spinner("thinking..."):
                response = st.session_state['chat_session'].send_message(question)
            st.session_state['chat_history'].append({'role': 'model', 'text': response.text})
        except Exception as e:
            st.session_state['chat_history'].append({'role': 'model', 'text': f"Error: {e}"})
        # Increment the prompt_key to clear the input box after sending
        st.session_state['prompt_key'] += 1
        st.experimental_rerun()
