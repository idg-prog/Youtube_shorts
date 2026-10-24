import os
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
import googleapiclient.http
from groq import Groq
from openai import OpenAI
import streamlit as st

st.set_page_config(
    page_title="YouTube Shorts Uploader", page_icon="🎬", layout="centered"
)

st.title("🎬 Streamlit YouTube Shorts Automation")
st.markdown(
    "Upload your video files below. The app will transcribe them using **Groq"
    " Whisper** (Free), generate optimized titles & descriptions via AI, and"
    " upload them straight to your YouTube channel!"
)

# --- CHECK SECRETS CONFIGURATION ---
if "youtube" not in st.secrets or "groq" not in st.secrets:
  st.error(
      "❌ Missing configuration! Please check your Streamlit Secrets (`secrets.toml`)."
  )
  st.stop()

# --- MULTIPLE FILE UPLOADER ---
uploaded_files = st.file_uploader(
    "Choose video files to upload",
    type=["mp4", "mov", "mkv", "avi"],
    accept_multiple_files=True,
)

if uploaded_files:
  st.info(f"Loaded {len(uploaded_files)} video(s) ready for processing.")

  if st.button("Start Processing & Uploading", type="primary"):
    # Initialize Clients from st.secrets
    groq_client = Groq(api_key=st.secrets["groq"]["api_key"])

    # Optional OpenRouter setup from secrets
    openrouter_api_key = st.secrets.get("openrouter", {}).get("api_key", "")

    try:
      creds_info = st.secrets["youtube"]
      creds = Credentials(
          token=None,
          refresh_token=creds_info["refresh_token"],
          client_id=creds_info["client_id"],
          client_secret=creds_info["client_secret"],
          token_uri="https://oauth2.googleapis.com/token",
      )
      if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
      youtube_service = googleapiclient.discovery.build(
          "youtube", "v3", credentials=creds
      )
    except Exception as e:
      st.error(f"YouTube Authentication Failed: {e}")
      st.stop()

    # Process each uploaded video one by one
    for idx, uploaded_file in enumerate(uploaded_files):
      st.markdown(f"--- \n### Processing: {uploaded_file.name}")

      # Save uploaded file temporarily to disk for processing
      with tempfile.NamedTemporaryFile(
          delete=False, suffix=os.path.splitext(uploaded_file.name)[1]
      ) as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

      try:
        # 1. Transcribe via Groq Whisper API (Free & Fast)
        with st.spinner("Transcribing audio using free Groq Whisper..."):
          with open(tmp_path, "rb") as audio_file:
            transcript_res = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=audio_file
            )
            transcript_text = transcript_res.text

        st.text_area(
            "Transcript Preview", transcript_text, height=80, key=f"tr_{idx}"
        )

        # 2. Generate Title & Description via AI
        with st.spinner("Generating title & description..."):
          prompt = f"""
                    Based on this transcript, generate a catchy YouTube Short title (max 60 chars, optimized for engagement) and an engaging description with relevant hashtags (#Shorts included).
                    
                    Transcript:
                    {transcript_text}
                    
                    Format strictly as:
                    TITLE: [Your Title]
                    DESCRIPTION: [Your Description]
                    """

          if openrouter_api_key:
            ai_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
            )
            model_name = "anthropic/claude-3.5-sonnet"
          else:
            ai_client = groq_client
            model_name = "llama-3.3-70b-versatile"  # Free on Groq

          response = ai_client.chat.completions.create(
              model=model_name, messages=[{"role": "user", "content": prompt}]
          )
          content = response.choices[0].message.content

          title, description = "Untitled Short", ""
          for line in content.split("\n"):
            if line.startswith("TITLE:"):
              title = line.replace("TITLE:", "").strip()
            elif line.startswith("DESCRIPTION:"):
              description = line.replace("DESCRIPTION:", "").strip()

        st.success(f"Generated Title: {title}")

        # 3. Upload to YouTube
        with st.spinner("Uploading to YouTube..."):
          body = {
              "snippet": {
                  "title": f"{title} #Shorts",
                  "description": description,
                  "tags": ["shorts", "automation"],
                  "categoryId": "22",
              },
              "status": {"privacyStatus": "public"},
          }

          media = googleapiclient.http.MediaFileUpload(
              tmp_path, chunksize=-1, resumable=True
          )
          request = youtube_service.videos().insert(
              part="snippet,status", body=body, media_body=media
          )

          response = None
          while response is None:
            status, response = request.next_chunk()

          video_id = response.get("id")
          st.success(
              f"Successfully Uploaded! Video ID: {video_id} 🔗"
              f" https://youtu.be/{video_id}"
          )

      except Exception as e:
        st.error(f"Error processing {uploaded_file.name}: {e}")

      finally:
        if os.path.exists(tmp_path):
          os.remove(tmp_path)

    st.balloons()
