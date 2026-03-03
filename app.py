import streamlit as st
import feedparser
import os
import requests
from groq import Groq
import google.generativeai as genai
from dotenv import load_dotenv

# Laad API sleutels uit .env bestand
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Mij Gedacht AI Agent", page_icon="🎙️")
st.title("🎙️ Mij Gedacht: Online AI Agent")

rss_url = st.text_input("RSS Feed URL", "https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")

if st.button("Analyseer Laatste Aflevering"):
    with st.spinner("Bezig met ophalen en analyseren..."):
        # 1. RSS Feed uitlezen
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            st.error("Kon geen afleveringen vinden.")
        else:
            entry = feed.entries[0]
            audio_url = entry.enclosures[0].href
            st.info(f"Aflevering gevonden: {entry.title}")

            # 2. Audio downloaden (beperkt fragment voor test/snelheid)
            audio_file = "temp_audio.mp3"
            response = requests.get(audio_url, stream=True)
            with open(audio_file, "wb") as f:
                # We downloaden de eerste 20MB (ongeveer 15-20 min audio)
                for chunk in response.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
                    if os.path.getsize(audio_file) > 20 * 1024 * 1024:
                        break

            # 3. Transcriptie via GROQ (Whisper Large V3)
            st.write("🤖 AI luistert naar de podcast via Groq...")
            with open(audio_file, "rb") as file:
                transcription = groq_client.audio.transcriptions.create(
                    file=(audio_file, file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="nl"
                )
            
            # 4. Samenvatting via Gemini
            st.write("🧠 Brein (Gemini) maakt de samenvatting...")
            prompt = f"""
            Je bent een expert van de podcast 'Mij Gedacht'. 
            Hieronder volgt een transcript van een aflevering. 
            Maak een gevatte samenvatting in het Vlaams. 
            Focus op: besproken FC De Kampioenen thema's, grappige momenten en de algemene sfeer.
            
            Transcript: {transcription[:15000]} 
            """
            summary = gemini_model.generate_content(prompt)

            # Resultaat tonen
            st.success("Analyse voltooid!")
            st.subheader("De 'Mij Gedacht' Samenvatting")
            st.write(summary.text)
            
            # Opruimen
            if os.path.exists(audio_file):
                os.remove(audio_file)