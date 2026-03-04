import streamlit as st
import feedparser
import os
import requests
import json
import base64
import time
from datetime import datetime
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except Exception:
    st.error("⚠️ Configuratie-fout in Secrets. Controleer GITHUB_REPO en GITHUB_TOKEN.")
    st.stop()

# 2. Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# 3. GitHub Sync
def get_latest_github_state():
    # Verwijder eventuele spaties uit GITHUB_REPO
    repo = GITHUB_REPO.strip()
    url = f"https://api.github.com/repos/{repo}/contents/database.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Cache-Control": "no-cache"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        elif resp.status_code == 404:
            add_log("Waarschuwing: database.json niet gevonden op GitHub. Nieuw bestand wordt aangemaakt bij opslaan.")
            return {}, None
    except Exception as e:
        add_log(f"GitHub ophaal fout: {e}")
    return {}, None

def save_to_github_max(data):
    repo = GITHUB_REPO.strip()
    url = f"https://api.github.com/repos/{repo}/contents/database.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Altijd de meest recente SHA ophalen net voor het opslaan
    current_state = requests.get(url, headers=headers)
    sha = None
    if current_state.status_code == 200:
        sha = current_state.json().get("sha")
    
    content_json = json.dumps(data, indent=4)
    content_b64 = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": f"Deep Scan Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha
    
    resp = requests.put(url, json=payload, headers=headers)
    if resp.status_code not in [200, 201]:
        st.session_state.last_error = f"GitHub Error {resp.status_code}: {resp.text}"
        return False
    return True

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    if 'scan_logs' not in st.session_state:
        st.session_state.scan_logs = []
    st.session_state.scan_logs.append(f"[{ts}] {msg}")

# --- UI ---
st.set_page_config(page_title="Mij Gedacht AI - MAX", layout="centered")

# Initialiseer database bij start
if 'db' not in st.session_state:
    st.session_state.db, _ = get_latest_github_state()

st.title("🎙️ Mij Gedacht AI (Deep Scan)")

query = st.text_input("Vraag de conciërge iets:", placeholder="Stel een vraag...")
if query and st.session_state.db:
    with st.spinner("Zoeken..."):
        context = "\n\n".join([f"AFLEVERING: {k}\nVERSLAG: {v['summary']}" for k, v in st.session_state.db.items()])
        res = gemini_model.generate_content(f"Antwoord in sappig Vlaams: {query}\n\nContext:\n{context[:200000]}")
        st.info(res.text)

with st.sidebar:
    st.header("🚀 Beheer")
    if st.button("🔥 START DIEPE SCAN"):
        st.session_state.scan_logs = []
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        
        # Controleer of we data hebben
        db = st.session_state.db
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Scan: {entry.title}") as status:
                add_log(f"Start download van {entry.title}...")
                r = requests.get(entry.enclosures[0].href, stream=True)
                audio_file = "temp.mp3"
                with open(audio_file, "wb") as f:
                    size = 0
                    for chunk in r.iter_content(chunk_size=131072):
                        f.write(chunk)
                        size += len(chunk)
                        if size > 24.8 * 1024 * 1024: break
                
                try:
                    add_log("Verzenden naar Groq...")
                    with open(audio_file, "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=(audio_file, f), 
                            model="whisper-large-v3-turbo", 
                            response_format="text", 
                            language="nl"
                        )
                    
                    add_log(f"Gemini analyseert {len(ts)} tekens...")
                    res = gemini_model.generate_content(
                        f"Schrijf een extreem uitgebreid verslag van deze podcast in sappig Vlaams: {ts[:500000]}"
                    )
                    
                    add_log("Synchroniseren met GitHub...")
                    db[entry.title] = {"summary": res.text, "date": entry.published}
                    
                    if save_to_github_max(db):
                        st.session_state.db = db
                        add_log("✅ Succesvol opgeslagen!")
                        status.update(label="Voltooid!", state="complete")
                        if os.path.exists(audio_file): os.remove(audio_file)
                        time.sleep(2)
                        st.rerun()
                    else:
                        add_log(f"❌ Opslag mislukt: {st.session_state.get('last_error', 'Onbekende fout')}")
                except Exception as e:
                    add_log(f"ERROR: {e}")
        else:
            st.info("Geen nieuwe afleveringen.")

    if 'scan_logs' in st.session_state:
        st.divider()
        for log in reversed(st.session_state.scan_logs):
            st.caption(log)
