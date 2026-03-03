import streamlit as st
import feedparser
import os
import requests
import json
import base64
import time
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except Exception as e:
    st.error(f"Configuratie fout: {e}")
    st.stop()

# 2. Clients initialiseren
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-3-flash-preview')
except Exception as e:
    st.error(f"Initialisatie fout: {e}")

# 3. GitHub Functies
def get_github_db():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    return {}, None

def save_to_github(data, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {
        "message": f"Update: {len(data)} items",
        "content": base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")
    }
    if sha: payload["sha"] = sha
    resp = requests.put(url, json=payload, headers=headers)
    return resp.status_code == 200 or resp.status_code == 201

# --- UI ---
st.title("🎙️ Mij Gedacht AI - Diagnose Mode")
db, current_sha = get_github_db()
st.write(f"Archief bevat {len(db)} items.")

if st.button("🚀 Test Transcriptie"):
    feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
    entry = feed.entries[0]
    
    with st.status("Stap 1: Downloaden...") as s:
        r = requests.get(entry.enclosures[0].href, stream=True)
        with open("test.mp3", "wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                f.write(chunk)
                if os.path.getsize("test.mp3") > 2 * 1024 * 1024: break # Extreem klein fragment (2MB)
        
        st.write("Stap 2: Groq aanroepen...")
        try:
            with open("test.mp3", "rb") as f:
                # We lezen het bestand expliciet in
                audio_data = f.read()
                
                transcription = groq_client.audio.transcriptions.create(
                    file=("test.mp3", audio_data),
                    model="whisper-large-v3-turbo",
                    response_format="json"
                )
            st.success("✅ Groq werkt!")
            st.write(transcription)
        except Exception as e:
            st.error("❌ Groq weigert dienst!")
            st.exception(e) # Dit toont de VOLLEDIGE foutmelding
        finally:
            if os.path.exists("test.mp3"): os.remove("test.mp3")
