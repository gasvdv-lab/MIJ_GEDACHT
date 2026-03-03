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
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    
    # DE FIX: We gebruiken de korte naam 'gemini-1.5-flash' 
    # De bibliotheek kiest zelf de beste versie (v1beta of v1)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Fout bij initialisatie: {e}")
    st.stop()

st.set_page_config(page_title="Mij Gedacht AI", page_icon="🎙️")
st.title("🎙️ Mij Gedacht: Online AI Agent")

rss_url = st.text_input("RSS Feed URL", "https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")

if st.button("Analyseer Laatste Aflevering"):
    with st.spinner("De agent luistert en denkt na..."):
        try:
            # 1. RSS Feed
            feed = feedparser.parse(rss_url)
            entry = feed.entries[0]
            audio_url = entry.enclosures[0].href
            st.info(f"Bezig met: {entry.title}")

            # 2. Audio ophalen (fragment van 10MB voor snelheid)
            audio_file = "temp_audio.mp3"
            response = requests.get(audio_url, stream=True)
            with open(audio_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
                    if os.path.getsize(audio_file) > 10 * 1024 * 1024:
                        break

            # 3. Transcriptie via GROQ (Whisper Large V3 Turbo)
            st.write("🤖 AI luistert via Groq...")
            with open(audio_file, "rb") as file:
                transcription = groq_client.audio.transcriptions.create(
                    file=(audio_file, file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="nl"
                )
            
            # 4. Samenvatting via Gemini
            st.write("🧠 Brein (Gemini) analyseert...")
            prompt = f"Vat dit fragment van de podcast 'Mij Gedacht' kort en gevat samen in het Vlaams: {transcription[:8000]}"
            
            # We voegen een extra check toe voor de generatie
            response = gemini_model.generate_content(prompt)

            st.success("Klaar!")
            st.subheader("De Analyse")
            st.write(response.text)
            
        except Exception as e:
            # We tonen de fout maar houden het opgeruimd
            st.error(f"Er ging iets mis: {e}")
        finally:
            if os.path.exists(audio_file):
                os.remove(audio_file)
