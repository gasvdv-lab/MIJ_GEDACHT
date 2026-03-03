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
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {
        "message": "Archief bijwerken",
        "content": base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")
    }
    if sha: payload["sha"] = sha
    requests.put(url, json=payload, headers=headers)

# Layout
st.set_page_config(page_title="Mij Gedacht AI", page_icon="🕵️", layout="centered")

st.title("🕵️ De Mij Gedacht Conciërge")
st.write("Stel een vraag over de podcast en ik zoek het voor je uit.")

db, current_sha = get_github_db()

# --- AI ZOEKMACHINE ---
query = st.text_input("Wat wil je weten?", placeholder="Stel hier je vraag...")

if query:
    if not db:
        st.warning("Het archief is nog leeg.")
    else:
        with st.spinner("Het archief doorzoeken..."):
            context_text = "\n".join([f"Aflevering {k}: {v['summary']}" for k, v in db.items()])
            prompt = f"Je bent de Mij Gedacht AI-conciërge. Gebruik enkel dit archief om de vraag in het Vlaams te beantwoorden: {context_text[:15000]}\n\nVraag: {query}"
            
            try:
                response = gemini_model.generate_content(prompt)
                st.chat_message("assistant").write(response.text)
            except Exception as e:
                st.error(f"Fout: {e}")

# --- BEHEER (Zijbalk) ---
with st.sidebar:
    st.header("⚙️ Systeembeheer")
    st.caption(f"Archief: {len(db)} afleveringen")
    
    with st.expander("Data importeren"):
        if st.button("🔄 Scan nieuwe aflevering"):
            feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
            new_entries = [e for e in feed.entries if e.title not in db]
            
            if new_entries:
                entry = new_entries[0]
                with st.status(f"Analyseren: {entry.title}") as status:
                    # Download
                    audio_url = entry.enclosures[0].href
                    r = requests.get(audio_url, stream=True)
                    with open("temp.mp3", "wb") as f:
                        for chunk in r.iter_content(1024*1024):
                            f.write(chunk)
                            if os.path.getsize("temp.mp3") > 12*1024*1024: break
                    
                    # Groq
                    st.write("🤖 Transcriberen...")
                    with open("temp.mp3", "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=("temp.mp3", f.read()),
                            model="whisper-large-v3-turbo",
                            response_format="text", language="nl"
                        )
                    
                    # Gemini met automatische herhaling bij limiet
                    st.write("🧠 Samenvatten...")
                    summary_text = None
                    for i in range(5): # Max 5 pogingen
                        try:
                            res = gemini_model.generate_content(f"Maak een gedetailleerde samenvatting in het Vlaams van dit podcast fragment: {ts[:8000]}")
                            summary_text = res.text
                            break
                        except Exception as e:
                            if "429" in str(e) or "ResourceExhausted" in str(e):
                                st.warning(f"Limiet bereikt. Wachten op Google (poging {i+1})...")
                                time.sleep(65) # Wacht iets langer dan een minuut
                            else:
                                raise e
                    
                    if summary_text:
                        db[entry.title] = {"summary": summary_text, "date": entry.published}
                        save_to_github(db, current_sha)
                        st.success("Opgeslagen!")
                        time.sleep(2)
                        st.rerun()
                    
                    if os.path.exists("temp.mp3"): os.remove("temp.mp3")
            else:
                st.info("Geen nieuwe afleveringen.")
