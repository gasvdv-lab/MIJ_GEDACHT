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
    st.error("⚠️ Configuratie niet compleet in Streamlit Secrets.")
    st.stop()

# 2. Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Functies met verbeterde foutafhandeling voor opslaan
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
    content_json = json.dumps(data, indent=4)
    content_base64 = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": "Archief bijwerken met maximaal volume",
        "content": content_base64
    }
    if sha:
        payload["sha"] = sha
        
    resp = requests.put(url, json=payload, headers=headers)
    if resp.status_code in [200, 201]:
        return resp.json().get("content", {}).get("sha")
    else:
        st.error(f"GitHub Opslagfout: {resp.status_code} - {resp.text}")
        return sha

# --- UI CONFIGURATIE ---
st.set_page_config(page_title="Mij Gedacht AI", page_icon="🎙️", layout="centered")

if os.path.exists("logo.png"):
    st.image("logo.png", width=200)
elif os.path.exists("foto.png"):
    st.image("foto.png", width=200)
else:
    st.image("https://i1.sndcdn.com/avatars-I7oN87f2iIuImsC0-E2M1XQ-t500x500.jpg", width=200)

st.markdown("<h1 style='margin-top: -20px;'>Mij Gedacht AI</h1>", unsafe_allow_html=True)

db, current_sha = get_github_db()

# --- DE ZOEKFUNCTIE (MAXIMAAL VOLUME) ---
query = st.text_input("Vraag de conciërge iets:", placeholder="Stel je vraag...")
if query and db:
    with st.spinner("De conciërge diept het archief uit..."):
        # We voeren Gemini nu een enorme hoeveelheid context (100k karakters)
        context = "\n".join([f"{k}: {v['summary']}" for k, v in db.items()])
        try:
            full_prompt = f"Antwoord zeer uitgebreid en in sappig Vlaams: {query}\n\nContext uit alle afleveringen:\n{context[:100000]}"
            res = gemini_model.generate_content(full_prompt)
            st.chat_message("assistant").write(res.text)
        except Exception:
            st.error("Google quota bereikt. Probeer het over een tijdje opnieuw.")

# --- BEHEER (MEER TIJD & GROTERE FILES) ---
with st.sidebar:
    st.header("⚙️ Geavanceerd Beheer")
    st.write(f"Items in database: {len(db)}")
    
    if st.button("🔄 Start Diepe Scan (Max Volume)"):
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Grote analyse: {entry.title}"):
                # We downloaden nu tot 24.5MB (strak tegen de Groq limiet aan voor max tijd)
                r = requests.get(entry.enclosures[0].href, stream=True)
                audio_file = "temp.mp3"
                with open(audio_file, "wb") as f:
                    size = 0
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            size += len(chunk)
                            if size > 24.5 * 1024 * 1024: 
                                break
                
                try:
                    # Transcriptie via Groq
                    with open(audio_file, "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=(audio_file, f),
                            model="whisper-large-v3-turbo",
                            response_format="text", 
                            language="nl"
                        )
                    
                    # Gemini analyseert nu tot 120.000 karakters tekst voor de samenvatting
                    res = gemini_model.generate_content(
                        f"Maak een extreem gedetailleerde, lange samenvatting in sappig Vlaams. "
                        f"Benoem alle namen, grappen en verhalen die je hoort: {ts[:120000]}"
                    )
                    
                    db[entry.title] = {"summary": res.text, "date": entry.published}
                    save_to_github(db, current_sha)
                    
                    if os.path.exists(audio_file): os.remove(audio_file)
                    st.success("✅ Diepe scan opgeslagen in GitHub!")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Fout: {e}")
        else:
            st.info("Geen nieuwe afleveringen.")
