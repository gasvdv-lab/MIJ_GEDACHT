import streamlit as st
import feedparser
import os
import requests
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
if "GROQ_API_KEY" in st.secrets and "GEMINI_API_KEY" in st.secrets:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error("⚠️ API sleutels niet gevonden!")
    st.stop()

# 2. Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

st.set_page_config(page_title="Mij Gedacht AI Agent", page_icon="🎙️", layout="wide")
st.title("🚀 Mij Gedacht: Volledige Analyse Agent")

rss_url = st.text_input("RSS Feed URL", "https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")

# Keuze voor aantal afleveringen
num_episodes = st.slider("Hoeveel afleveringen analyseren?", 1, 10, 3)

if st.button(f"Start Analyse van {num_episodes} afleveringen"):
    feed = feedparser.parse(rss_url)
    episodes = feed.entries[:num_episodes]
    
    for i, entry in enumerate(episodes):
        st.markdown(f"### 🎧 Aflevering {i+1}: {entry.title}")
        
        with st.status(f"Bezig met '{entry.title}'...", expanded=False) as status:
            try:
                audio_url = entry.enclosures[0].href
                audio_file = f"temp_{i}.mp3"
                
                # Downloaden
                st.write("📥 Audio ophalen...")
                response = requests.get(audio_url, stream=True)
                with open(audio_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024*1024):
                        f.write(chunk)
                        if os.path.getsize(audio_file) > 10 * 1024 * 1024:
                            break
                
                # Transcriptie via Groq
                st.write("🤖 Transcriberen (Groq)...")
                with open(audio_file, "rb") as file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(audio_file, file.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text",
                        language="nl"
                    )
                
                # Analyse via Gemini 3
                st.write("🧠 Analyseren (Gemini 3)...")
                prompt = f"Vat dit fragment van de podcast 'Mij Gedacht' gevat samen in het Vlaams: {transcription[:12000]}"
                summary = gemini_model.generate_content(prompt)
                
                status.update(label=f"✅ Klaar: {entry.title}", state="complete")
                st.write(summary.text)
                st.divider()
                
            except Exception as e:
                st.error(f"Fout bij {entry.title}: {e}")
            finally:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
