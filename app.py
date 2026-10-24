import os
import subprocess
import tempfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
import googleapiclient.http
from groq import Groq
from openai import OpenAI
import streamlit as st
import yt_dlp

st.set_page_config(
    page_title="YouTube Shorts Auto-Uploader & Downloader", page_icon="🎬", layout="centered"
)

st.title("🎬 YouTube Shorts Automated Uploader & Downloader")

# --- CREATE TABS ---
tab1, tab2 = st.tabs(["📤 Auto-Uploader", "📥 Video Downloader"])

# ==========================================
# TAB 1: AUTO-UPLOADER (Original Functionality)
# ==========================================
with tab1:
    st.markdown(
        "Upload your video files. The app will extract compressed audio, transcribe"
        " via **Groq Whisper**, and upload them to YouTube!"
    )

    # --- CONFIGURATION CHECK ---
    if "youtube" not in st.secrets or "groq" not in st.secrets:
        st.error("❌ Missing `[youtube]` or `[groq]` credentials in Streamlit Secrets.")
    else:
        # --- FILE UPLOADER ---
        uploaded_files = st.file_uploader(
            "Select video files (MP4, MOV, MKV)",
            type=["mp4", "mov", "mkv", "avi"],
            accept_multiple_files=True,
            key="uploader_tab1"
        )

        if uploaded_files:
            st.info(f"Loaded {len(uploaded_files)} video(s) ready for processing.")

            if st.button("Start Processing & Uploading", type="primary", key="btn_tab1"):
                groq_client = Groq(api_key=st.secrets["groq"]["api_key"])
                openrouter_api_key = st.secrets.get("openrouter", {}).get("api_key", "")

                # Authenticate YouTube
                try:
                    yt_secrets = st.secrets["youtube"]
                    creds = Credentials(
                        token=None,
                        refresh_token=yt_secrets["refresh_token"],
                        client_id=yt_secrets["client_id"],
                        client_secret=yt_secrets["client_secret"],
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

                for idx, uploaded_file in enumerate(uploaded_files):
                    st.markdown(f"--- \n### Processing: `{uploaded_file.name}`")

                    # Save full video temporarily
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=os.path.splitext(uploaded_file.name)[1]
                    ) as tmp_video:
                        tmp_video.write(uploaded_file.read())
                        video_path = tmp_video.name

                    audio_path = video_path + ".mp3"

                    try:
                        # 1. Extract & Compress Audio to MP3 using ffmpeg
                        with st.spinner("Extracting & compressing audio..."):
                            cmd = [
                                "ffmpeg",
                                "-y",
                                "-i",
                                video_path,
                                "-vn",
                                "-acodec",
                                "libmp3lame",
                                "-ar",
                                "16000",
                                "-ac",
                                "1",
                                "-b:a",
                                "64k",
                                audio_path,
                            ]
                            subprocess.run(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                check=True,
                            )

                        # 2. Transcribe via Groq Whisper API
                        with st.spinner("Transcribing audio via Groq Whisper..."):
                            with open(audio_path, "rb") as audio_file:
                                transcript_res = groq_client.audio.transcriptions.create(
                                    model="whisper-large-v3-turbo", file=audio_file
                                )
                                transcript_text = transcript_res.text

                        st.text_area(
                            "Transcript Preview", transcript_text, height=80, key=f"tr_{idx}"
                        )

                        # 3. Generate Title & Description via AI
                        with st.spinner("Generating SEO Title & Description..."):
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
                                model_name = "nvidia/nemotron-3-ultra-550b-a55b:free"
                            else:
                                ai_client = groq_client
                                model_name = "nvidia/nemotron-3.5-lightning:free"

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

                        # 4. Upload original video file to YouTube
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
                                video_path, chunksize=-1, resumable=True
                            )
                            request = youtube_service.videos().insert(
                                part="snippet,status", body=body, media_body=media
                            )

                            response = None
                            while response is None:
                                status, response = request.next_chunk()

                            video_id = response.get("id")
                            st.success(
                                f"Uploaded Successfully! Video ID: {video_id} 🔗"
                                f" https://youtu.be/{video_id}"
                            )

                    except Exception as e:
                        st.error(f"Error processing file: {e}")

                    finally:
                        if os.path.exists(video_path):
                            os.remove(video_path)
                        if os.path.exists(audio_path):
                            os.remove(audio_path)

                st.balloons()


# ==========================================
# TAB 2: VIDEO DOWNLOADER (New Functionality)
# ==========================================
with tab2:
    st.markdown("📥 **Download videos from YouTube or supported platforms using `yt-dlp`**")
    
    video_url = st.text_input("Enter Video URL (YouTube, TikTok, etc.)", placeholder="https://www.youtube.com/watch?v=...")
    
    if st.button("Download Video", type="primary", key="btn_download"):
        if not video_url:
            st.warning("⚠️ Please enter a valid URL.")
        else:
            with tempfile.TemporaryDirectory() as tmpdirname:
                output_template = os.path.join(tmpdirname, '%(title)s.%(ext)s')
                
                ydl_opts = {
                    'format': 'best',
                    'outtmpl': output_template,
                    'noplaylist': True,
                }
                
                try:
                    with st.spinner("Downloading video... Please wait."):
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info_dict = ydl.extract_info(video_url, download=True)
                            filename = ydl.prepare_filename(info_dict)
                    
                    st.success("Download complete!")
                    
                    # Provide a download button for the user to save the file locally
                    with open(filename, "rb") as f:
                        file_bytes = f.read()
                        st.download_button(
                            label="💾 Save Video to Device",
                            data=file_bytes,
                            file_name=os.path.basename(filename),
                            mime="video/mp4"
                        )
                except Exception as e:
                    st.error(f"❌ Failed to download video: {e}")
