import streamlit as st
import feedparser
import os
import requests
import json
import base64
import time # NIEUW: Voor de pauze
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except Exception:
    st.error("⚠️ API sleutels of GitHub Secrets missen!")
    st.stop()

# 2. Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Functies
def get_github_db():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        content = base64.b64decode(resp.json()["content"]).decode("utf-8")
        return json.loads(content), resp.json()["sha"]
    return {}, None

def save_to_github(data, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {
        "message": "Update podcast database",
        "content": base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")
    }
    if sha:
        payload["sha"] = sha
    
    resp = requests.put(url, json=payload, headers=headers)
    return resp.status_code, resp.json().get("content", {}).get("sha", sha)

st.set_page_config(page_title="Mij Gedacht Archief", page_icon="🗄️", layout="wide")
st.title("🗄️ Mij Gedacht: Het Volledige Archief")

db, current_sha = get_github_db()

# Zijbalk met status
st.sidebar.header("Archief Status")
st.sidebar.write(f"Aantal in database: {len(db)}")

if st.button("🚀 Scan & Analyseer Nieuwe Afleveringen"):
    feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
    new_entries = [e for e in feed.entries if e.title not in db]
    
    if not new_entries:
        st.success("Alles is up-to-date!")
    else:
        st.info(f"{len(new_entries)} nieuwe gevonden. We verwerken er max 3 per keer.")
        
        for entry in new_entries[:3]: # Verlaagd naar 3 voor stabiliteit
            with st.status(f"Bezig met: {entry.title}") as s:
                audio_url = entry.enclosures[0].href
                audio_file = "temp.mp3"
                
                # Download
                r = requests.get(audio_url, stream=True)
                with open(audio_file, "wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        f.write(chunk)
                        if os.path.getsize(audio_file) > 10*1024*1024: break
                
                # Groq
                with open(audio_file, "rb") as f:
                    ts = groq_client.audio.transcriptions.create(
                        file=(audio_file, f.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text", language="nl"
                    )
                
                # Gemini met pauze tegen ResourceExhausted
                st.write("🧠 Even geduld voor de AI...")
                time.sleep(10) # 10 seconden pauze per aflevering
                
                res = gemini_model.generate_content(f"Vat kort samen in het Vlaams: {ts[:10000]}")
                
                # Direct opslaan
                db[entry.title] = {"summary": res.text, "date": entry.published}
                status_code, new_sha = save_to_github(db, current_sha)
                current_sha = new_sha # Update SHA voor volgende item
                
                if os.path.exists(audio_file): os.remove(audio_file)
                st.write("✅ Opgeslagen!")
                
        st.success("Batch voltooid! Herlaad de pagina.")
        st.rerun()

# Selectiebox
selected = st.selectbox("Kies uit archief:", list(db.keys()) if db else ["Geen data"])
if selected != "Geen data":
    st.markdown(f"### {selected}")
    st.write(db[selected]["summary"])
