import streamlit as st
import feedparser
import os
import requests
import json
import base64
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

# 3. GitHub Functies voor Database (JSON)
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
    requests.put(url, json=payload, headers=headers)

st.set_page_config(page_title="Mij Gedacht Archief", page_icon="🗄️", layout="wide")
st.title("🗄️ Mij Gedacht: Het Volledige Archief")

# Laden van bestaande data
db, current_sha = get_github_db()

# UI: Toon bestaande samenvattingen
if db:
    st.sidebar.header("Reeds geanalyseerd")
    for title in list(db.keys()):
        st.sidebar.write(f"✅ {title}")

# Actie: Scan voor nieuwe afleveringen
if st.button("🚀 Scan & Analyseer Nieuwe Afleveringen"):
    feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
    
    new_entries = [e for e in feed.entries if e.title not in db]
    
    if not new_entries:
        st.success("Alles is up-to-date!")
    else:
        st.info(f"{len(new_entries)} nieuwe afleveringen gevonden. Start verwerking...")
        
        for entry in new_entries[:5]: # Beperkt tot 5 per keer voor stabiliteit
            with st.status(f"Verwerken: {entry.title}") as s:
                audio_url = entry.enclosures[0].href
                audio_file = "temp.mp3"
                
                # 1. Download (max 12MB)
                r = requests.get(audio_url, stream=True)
                with open(audio_file, "wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        f.write(chunk)
                        if os.path.getsize(audio_file) > 12*1024*1024: break
                
                # 2. Groq Transcript
                with open(audio_file, "rb") as f:
                    ts = groq_client.audio.transcriptions.create(
                        file=(audio_file, f.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text", language="nl"
                    )
                
                # 3. Gemini Analyse
                prompt = f"Vat dit fragment van 'Mij Gedacht' kort samen in het Vlaams: {ts[:12000]}"
                res = gemini_model.generate_content(prompt)
                
                # 4. Opslaan in lokale DB en GitHub
                db[entry.title] = {"summary": res.text, "date": entry.published}
                save_to_github(db, current_sha)
                # Update SHA voor de volgende loop
                db, current_sha = get_github_db()
                
                os.remove(audio_file)
                st.write(res.text)
        st.rerun()

# Hoofdvenster: Toon de geselecteerde aflevering
selected = st.selectbox("Kies een aflevering uit het archief:", list(db.keys()) if db else ["Geen data"])
if selected != "Geen data":
    st.markdown(f"### {selected}")
    st.write(db[selected]["summary"])
    st.caption(f"Gepubliceerd op: {db[selected]['date']}")
