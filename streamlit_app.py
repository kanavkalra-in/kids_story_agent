import streamlit as st
import requests
import time
import uuid
from typing import Optional
from dotenv import load_dotenv
import os
from gtts import gTTS
import io
import tempfile
import hashlib

# Load .env file
load_dotenv()

# Configuration
API_BASE_URL = st.sidebar.text_input(
    "API Base URL",
    value="http://localhost:8000",
    help="Base URL of the Kids Story Agent API"
)

st.set_page_config(
    page_title="Kids Story Agent - Test UI",
    page_icon="📚",
    layout="wide",
)

st.title("📚 Kids Story Agent - Test Interface")
st.markdown("Generate children's stories with AI-powered illustrations")

# Initialize session state
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "polling" not in st.session_state:
    st.session_state.polling = False
if "story_data" not in st.session_state:
    st.session_state.story_data = None
if "audio_cache" not in st.session_state:
    st.session_state.audio_cache = {}


def check_api_health() -> bool:
    """Check if API is reachable"""
    response = requests.get(f"{API_BASE_URL}/health", timeout=5)
    return response.status_code == 200


def generate_story(prompt: str, age_group: str, num_illustrations: int, webhook_url: Optional[str] = None) -> dict:
    """Submit story generation request"""
    url = f"{API_BASE_URL}/api/v1/stories/generate"
    payload = {
        "prompt": prompt,
        "age_group": age_group,
        "num_illustrations": num_illustrations,
    }
    if webhook_url:
        payload["webhook_url"] = webhook_url
    
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def get_job_status(job_id: str) -> dict:
    """Get job status"""
    url = f"{API_BASE_URL}/api/v1/stories/jobs/{job_id}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()


def get_story(story_id: str) -> dict:
    """Get completed story"""
    url = f"{API_BASE_URL}/api/v1/stories/{story_id}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()


def generate_audio(text: str, story_id: str, lang: str = "en") -> Optional[bytes]:
    """Generate audio from text using gTTS"""
    try:
        # Create a hash of the text to cache audio
        text_hash = hashlib.md5(f"{story_id}_{text}".encode()).hexdigest()
        
        # Check cache first
        if text_hash in st.session_state.audio_cache:
            return st.session_state.audio_cache[text_hash]
        
        # Generate audio
        tts = gTTS(text=text, lang=lang, slow=False)
        
        # Save to bytes buffer
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_bytes = audio_buffer.read()
        
        # Cache the audio
        st.session_state.audio_cache[text_hash] = audio_bytes
        
        return audio_bytes
    except Exception as e:
        st.error(f"Error generating audio: {str(e)}")
        return None


# Sidebar - API Status
st.sidebar.header("API Status")
if check_api_health():
    st.sidebar.success("✅ API is reachable")
else:
    st.sidebar.error("❌ API is not reachable")
    st.sidebar.info(f"Make sure the API is running at: {API_BASE_URL}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Links")
st.sidebar.markdown(f"- [API Docs]({API_BASE_URL}/docs)")
st.sidebar.markdown(f"- [Health Check]({API_BASE_URL}/health)")

# Main content
tab1, tab2, tab3 = st.tabs(["Generate Story", "Check Status", "View Story"])

# Tab 1: Generate Story
with tab1:
    st.header("Generate a New Story")
    
    with st.form("story_form"):
        prompt = st.text_area(
            "Story Prompt",
            placeholder="e.g., A brave little mouse goes on an adventure to find a magical cheese",
            height=100,
            help="Describe the story you want to generate"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            age_group = st.selectbox(
                "Target Age Group",
                options=["3-5", "6-8", "9-12"],
                index=1,
                help="Select the target age group for the story"
            )
        
        with col2:
            num_illustrations = st.slider(
                "Number of Illustrations",
                min_value=1,
                max_value=10,
                value=3,
                help="Number of images to generate"
            )
        
        webhook_url = st.text_input(
            "Webhook URL (Optional)",
            placeholder="https://your-app.com/webhook",
            help="Optional webhook URL to receive completion notification"
        )
        
        submitted = st.form_submit_button("Generate Story", type="primary")
        
        if submitted:
            if not prompt.strip():
                st.error("Please enter a story prompt")
            else:
                with st.spinner("Submitting story generation request..."):
                    result = generate_story(
                        prompt=prompt,
                        age_group=age_group,
                        num_illustrations=num_illustrations,
                        webhook_url=webhook_url if webhook_url else None
                    )
                
                st.session_state.job_id = result["job_id"]
                st.success(f"✅ Story generation started!")
                st.info(f"**Job ID:** `{result['job_id']}`")
                st.info(f"**Status:** {result['status']}")
                st.info(f"**Message:** {result['message']}")
                
                # Auto-switch to status tab
                st.session_state.polling = True

# Tab 2: Check Status
with tab2:
    st.header("Check Job Status")
    
    # Job ID input
    job_id_input = st.text_input(
        "Job ID",
        value=str(st.session_state.job_id) if st.session_state.job_id else "",
        placeholder="Enter job ID to check status",
        help="The job ID returned when you submitted a story generation request"
    )
    
    col1, col2 = st.columns([1, 4])
    
    with col1:
        check_button = st.button("Check Status", type="primary")
    
    with col2:
        auto_poll = st.checkbox("Auto-poll (every 5 seconds)", value=st.session_state.polling)
        st.session_state.polling = auto_poll
    
    if check_button or (auto_poll and job_id_input):
        if not job_id_input:
            st.warning("Please enter a job ID")
        else:
            # Validate UUID format
            uuid.UUID(job_id_input)
            
            status_data = get_job_status(job_id_input)
            
            # Display status
            status = status_data["status"]
            
            if status == "pending":
                st.info("⏳ **Status:** Pending - Story generation is queued")
            elif status == "processing":
                st.warning("🔄 **Status:** Processing - Story is being generated")
            elif status == "completed":
                st.success("✅ **Status:** Completed - Story is ready!")
                if status_data.get("story_id"):
                    st.info(f"**Story ID:** `{status_data['story_id']}`")
                    st.session_state.story_data = {"story_id": status_data["story_id"]}
            elif status == "failed":
                st.error("❌ **Status:** Failed")
                if status_data.get("error"):
                    st.error(f"**Error:** {status_data['error']}")
            
            # Show details
            with st.expander("View Full Status Details"):
                st.json(status_data)
            
            # Auto-polling
            if auto_poll and status in ["pending", "processing"]:
                time.sleep(5)
                st.rerun()

# Tab 3: View Story
with tab3:
    st.header("View Completed Story")
    
    # Story ID input
    story_id_input = st.text_input(
        "Story ID",
        value=str(st.session_state.story_data["story_id"]) if st.session_state.story_data and st.session_state.story_data.get("story_id") else "",
        placeholder="Enter story ID to view",
        help="The story ID from a completed job"
    )
    
    view_button = st.button("Load Story", type="primary")
    
    if view_button or (story_id_input and st.session_state.story_data and st.session_state.story_data.get("story_id") == story_id_input):
        if not story_id_input:
            st.warning("Please enter a story ID")
        else:
            # Validate UUID format
            uuid.UUID(story_id_input)
            
            story_data = get_story(story_id_input)
            
            # Display story
            st.markdown(f"## {story_data['title']}")
            st.markdown(f"**Age Group:** {story_data['age_group']}")
            st.markdown(f"**Created:** {story_data['created_at']}")
            
            st.markdown("---")
            
            # Text-to-Speech Section
            st.markdown("### 🔊 Listen to Story")
            col1, col2 = st.columns([1, 3])
            
            with col1:
                generate_audio_btn = st.button("🎵 Generate Audio", type="secondary")
            
            with col2:
                # Language selection
                tts_lang = st.selectbox(
                    "Language",
                    options=["en", "es", "fr", "de", "it", "pt"],
                    format_func=lambda x: {
                        "en": "English",
                        "es": "Spanish",
                        "fr": "French",
                        "de": "German",
                        "it": "Italian",
                        "pt": "Portuguese"
                    }.get(x, x),
                    index=0,
                    label_visibility="collapsed"
                )
            
            # Generate and display audio
            audio_generated = st.session_state.get("audio_generated", {})
            audio_cache_key = f"{story_id_input}_{tts_lang}"
            
            if generate_audio_btn:
                full_text = f"{story_data['title']}. {story_data['content']}"
                
                with st.spinner("Generating audio... This may take a moment."):
                    audio_bytes = generate_audio(full_text, audio_cache_key, lang=tts_lang)
                
                if audio_bytes:
                    audio_generated[audio_cache_key] = True
                    st.session_state["audio_generated"] = audio_generated
                    st.audio(audio_bytes, format="audio/mp3", autoplay=False)
                    st.success("✅ Audio generated! Click play to listen to the story.")
                else:
                    st.error("Failed to generate audio. Please try again.")
            elif audio_cache_key in audio_generated:
                # Show previously generated audio
                full_text = f"{story_data['title']}. {story_data['content']}"
                audio_bytes = generate_audio(full_text, audio_cache_key, lang=tts_lang)
                if audio_bytes:
                    st.audio(audio_bytes, format="audio/mp3", autoplay=False)
                    st.info("💡 Audio is ready. Click play to listen.")
            
            st.markdown("---")
            st.markdown("### Story Content")
            st.markdown(story_data['content'])
            
            st.markdown("---")
            st.markdown(f"### Illustrations ({len(story_data['images'])} images)")
            
            # Display images in a grid
            if story_data['images']:
                cols = st.columns(min(3, len(story_data['images'])))
                for idx, image in enumerate(story_data['images']):
                    col = cols[idx % len(cols)]
                    with col:
                        st.image(image['image_url'], width='stretch')
                        with st.expander(f"Image {idx + 1} Details"):
                            st.markdown(f"**Scene:** {image.get('scene_description', 'N/A')}")
                            st.markdown(f"**Prompt Used:** {image.get('prompt_used', 'N/A')}")
                            st.markdown(f"**Order:** {image.get('display_order', 0)}")
            
            # Show full JSON
            with st.expander("View Full Story JSON"):
                st.json(story_data)

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>Kids Story Agent - Test Interface</div>",
    unsafe_allow_html=True
)
