import os
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
import googleapiclient.http
from openai import OpenAI
import streamlit as st

st.set_page_config(
    page_title="YouTube Shorts AI Uploader", page_icon="🚀", layout="centered"
)

st.title("🎬 AI YouTube Shorts Generator & Uploader")
st.markdown(
    "Upload your raw videos. This app transcribes them using **Groq Whisper**"
    " (Free), generates titles & descriptions via AI, and uploads them straight"
    " to your YouTube channel!"
)

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("API & Credentials")
groq_api_key = st.sidebar.text_input(
    "Groq API Key (Free tier)",
    type="password",
    help="Get a free key from console.groq.com",
)
openrouter_api_key = st.sidebar.text_input(
    "OpenRouter API Key (Optional)", type="password"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### YouTube Authentication")
has_youtube_secrets = (
    "youtube" in st.secrets
    and "refresh_token" in st.secrets["youtube"]
)
if has_youtube_secrets:
  st.sidebar.success("✅ YouTube Secrets Configured")
else:
  st.sidebar.error("❌ YouTube Secrets missing in Streamlit settings!")

# --- MAIN UPLOAD SECTION ---
uploaded_files = st.file_uploader(
    "Select Video Files (MP4, MOV, MKV)",
    type=["mp4", "mov", "mkv", "avi"],
    accept_multiple_files=True,
)

if uploaded_files:
  st.info(f"Loaded {len(uploaded_files)} video(s) ready for processing.")

  if st.button("Start Processing & Uploading", type="primary"):
    if not groq_api_key:
      st.error("Please provide your Groq API Key in the sidebar.")
      st.stop()

    if not has_youtube_secrets:
      st.error(
          "YouTube credentials not configured in Streamlit Secrets. Check setup"
          " instructions."
      )
      st.stop()

    # Initialize Clients
    groq_client = OpenAI(
        base_url="https://api.groq.com/openai/v1", api_key=groq_api_key
    )

    # Setup YouTube service using Streamlit Secrets
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
      st.error(f"Failed to authenticate YouTube API: {e}")
      st.stop()

    # Process each video sequentially
    for idx, uploaded_file in enumerate(uploaded_files):
      st.markdown(f"--- \nProcessing **{uploaded_file.name}**")

      # Save file to a temporary runner path
      with tempfile.NamedTemporaryFile(
          delete=False, suffix=os.path.splitext(uploaded_file.name)[1]
      ) as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

      try:
        # 1. Transcribe via Groq Whisper API (Free & Fast)
        with st.spinner("Transcribing video audio..."):
          with open(tmp_path, "rb") as audio_file:
            transcript_res = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo", file=audio_file
            )
            transcript_text = (
                transcript_res.text
                if hasattr(transcript_res, "text")
                else transcript_res["text"]
            )

        st.text_area(
            "Transcript Preview", transcript_text, height=90, key=f"tr_{idx}"
        )

        # 2. Generate Title & Description
        with st.spinner("Generating YouTube Shorts title & description..."):
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
                  "tags": ["shorts", "automation", "ai"],
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

          st.success(
              f"Uploaded Successfully! Video ID: {response.get('id')} 🔗"
              f" https://youtu.be/{response.get('id')}"
          )

      except Exception as e:
        st.error(f"Error processing {uploaded_file.name}: {e}")

      finally:
        if os.path.exists(tmp_path):
          os.remove(tmp_path)

    st.balloons()
