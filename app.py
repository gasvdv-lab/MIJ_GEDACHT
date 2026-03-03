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
    st.error(f"Sleutels missen: {e}")
    st.stop()

# 2. Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Functies met harde foutmeldingen
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
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    json_string = json.dumps(data, indent=4)
    content_base64 = base64.b64encode(json_string.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": f"Update archief: {len(data)} items",
        "content": content_base64
    }
    if sha:
        payload["sha"] = sha
    
    # DEBUG: Toon status voor verzending
    st.warning(f"Verzenden naar GitHub: {GITHUB_REPO}...")
    
    resp = requests.put(url, json=payload, headers=headers)
    
    if resp.status_code in [200, 201]:
        st.success("🎉 GitHub heeft de data ONTVANGEN!")
        return resp.json()["content"]["sha"]
    else:
        st.error(f"❌ GITHUB WEIGERT OPSLAG! Code: {resp.status_code}")
        st.write(resp.json())
        return sha

# --- INTERFACE ---
st.set_page_config(page_title="Mij Gedacht AI", page_icon="🎙️")
st.title("🎙️ Mij Gedacht AI")

db, current_sha = get_github_db()

# Zoekbalk
query = st.text_input("Vraag iets aan de conciërge:")
if query and db:
    context_text = "\n".join([f"{k}: {v['summary']}" for k, v in db.items()])
    res = gemini_model.generate_content(f"Vlaamse conciërge antwoordt op: {query}\nContext: {context_text[:15000]}")
    st.chat_message("assistant").write(res.text)

# Beheer in zijbalk
with st.sidebar:
    st.header("⚙️ Beheer")
    st.write(f"Database items: {len(db)}")
    
    if st.button("🔄 Start Scan"):
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Verwerken: {entry.title}"):
                # 1. Download
                audio_url = entry.enclosures[0].href
                r = requests.get(audio_url)
                with open("temp.mp3", "wb") as f:
                    f.write(r.content)
                
                # 2. Transcribe
                with open("temp.mp3", "rb") as f:
                    ts = groq_client.audio.transcriptions.create(
                        file=("temp.mp3", f.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text", language="nl"
                    )
                
                # 3. AI Analyse
                res = gemini_model.generate_content(f"Vat kort samen in Vlaams: {ts[:8000]}")
                summary = res.text
                
                # 4. Toevoegen aan lokale DB
                db[entry.title] = {"summary": summary, "date": entry.published}
                
                # 5. Opslaan (Hier moet de foutmelding komen)
                new_sha = save_to_github(db, current_sha)
                
                if new_sha != current_sha:
                    st.balloons()
                    time.sleep(3)
                    st.rerun()
        else:
            st.info("Geen nieuwe afleveringen.")
