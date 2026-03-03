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
    if resp.status_code in [200, 201]:
        return resp.json().get("content", {}).get("sha", sha)
    return sha

st.set_page_config(page_title="Mij Gedacht Archief", page_icon="🗄️", layout="wide")
st.title("🗄️ Mij Gedacht: Het Volledige Archief")

db, current_sha = get_github_db()

st.sidebar.header("Archief Status")
st.sidebar.write(f"Items in database: {len(db)}")

if st.button("🚀 Scan & Analyseer (Max 2 per keer)"):
    feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
    new_entries = [e for e in feed.entries if e.title not in db]
    
    if not new_entries:
        st.success("Alles is up-to-date!")
    else:
        # We doen er maar 2 tegelijk om de Free Tier te ontzien
        for entry in new_entries[:2]:
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
                        file=(audio_file, file.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text", language="nl"
                    )
                
                # Gemini met Slimme Retry
                st.write("🧠 AI analyseert (met rustpauze)...")
                summary_text = ""
                for attempt in range(3): # Max 3 pogingen
                    try:
                        time.sleep(20) # Ruime pauze van 20 sec
                        res = gemini_model.generate_content(f"Vat kort samen in het Vlaams: {ts[:8000]}")
                        summary_text = res.text
                        break
                    except Exception as e:
                        if "429" in str(e) or "ResourceExhausted" in str(e):
                            st.warning(f"Google is moe (poging {attempt+1}/3). 30 sec pauze...")
                            time.sleep(30)
                        else:
                            raise e
                
                if summary_text:
                    db[entry.title] = {"summary": summary_text, "date": entry.published}
                    current_sha = save_to_github(db, current_sha)
                    st.write("✅ Succesvol opgeslagen!")
                
                if os.path.exists(audio_file): os.remove(audio_file)
                
        st.success("Batch klaar! Herlaad de pagina.")
        st.rerun()

# Archief tonen
selected = st.selectbox("Kies een aflevering:", sorted(list(db.keys()), reverse=True) if db else ["Geen data"])
if selected != "Geen data":
    st.markdown(f"### {selected}")
    st.write(db[selected]["summary"])
