import streamlit as st
import streamlit.components.v1 as components
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
# Use environment variable if set (for Docker), otherwise use sidebar input
default_api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
API_BASE_URL = st.sidebar.text_input(
    "API Base URL",
    value=default_api_url,
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
if "selected_story_id" not in st.session_state:
    st.session_state.selected_story_id = None
if "loaded_story_data" not in st.session_state:
    st.session_state.loaded_story_data = None
if "loaded_story_id" not in st.session_state:
    st.session_state.loaded_story_id = None
if "switch_to_view_tab" not in st.session_state:
    st.session_state.switch_to_view_tab = False


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


def list_stories(limit: int = 100, offset: int = 0) -> dict:
    """List all stories"""
    url = f"{API_BASE_URL}/api/v1/stories"
    params = {"limit": limit, "offset": offset}
    response = requests.get(url, params=params, timeout=5)
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
# Inject JavaScript at app level to handle tab switching
if st.session_state.switch_to_view_tab:
    st.markdown("""
    <script>
        (function() {
            function clickViewStoryTab() {
                try {
                    const doc = document;
                    // Find View Story tab button
                    const buttons = doc.querySelectorAll('button');
                    for (let btn of buttons) {
                        if ((btn.textContent || btn.innerText || '').trim() === 'View Story') {
                            btn.click();
                            return true;
                        }
                    }
                    // Fallback: click 3rd tab (index 2)
                    const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
                    if (tabs.length >= 3) {
                        tabs[2].click();
                        return true;
                    }
                } catch(e) {
                    console.error('Tab switch error:', e);
                }
                return false;
            }
            // Try with delays
            setTimeout(clickViewStoryTab, 100);
            setTimeout(clickViewStoryTab, 300);
            setTimeout(clickViewStoryTab, 600);
        })();
    </script>
    """, unsafe_allow_html=True)
    st.session_state.switch_to_view_tab = False

tab1, tab2, tab3, tab4 = st.tabs(["Generate Story", "Check Status", "View Story", "All Stories"])

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
    
    # Check if a story was selected from the All Stories tab
    selected_id = st.session_state.selected_story_id
    
    # Story ID input
    story_id_input = st.text_input(
        "Story ID",
        value=str(selected_id) if selected_id else (str(st.session_state.story_data["story_id"]) if st.session_state.story_data and st.session_state.story_data.get("story_id") else ""),
        placeholder="Enter story ID to view",
        help="The story ID from a completed job"
    )
    
    view_button = st.button("Load Story", type="primary")
    
    # Auto-load if story was selected from All Stories tab or button clicked
    should_load = view_button or (selected_id and story_id_input and story_id_input == str(selected_id))
    
    # Check if we need to load a new story
    if should_load:
        if not story_id_input:
            st.warning("Please enter a story ID")
        else:
            # Validate UUID format
            try:
                uuid.UUID(story_id_input)
            except ValueError:
                st.error("Invalid story ID format. Please enter a valid UUID.")
            else:
                try:
                    story_data = get_story(story_id_input)
                    # Store in session state so it persists across reruns
                    st.session_state.loaded_story_data = story_data
                    st.session_state.loaded_story_id = story_id_input
                except requests.exceptions.RequestException as e:
                    st.error(f"Error loading story: {str(e)}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")
    
    # Clear the selection after checking (but keep loaded data)
    if selected_id:
        st.session_state.selected_story_id = None
    
    # Display story if we have loaded data
    # Show story if: we have loaded data AND (input matches loaded ID OR input is empty OR we just loaded it)
    if st.session_state.loaded_story_data:
        # Check if we should show this story (matches current input or no input specified)
        should_show = (
            not story_id_input or  # No input specified, show loaded story
            story_id_input == st.session_state.loaded_story_id or  # Input matches loaded story
            should_load  # We just loaded it
        )
        
        if should_show:
            story_data = st.session_state.loaded_story_data
            
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
            current_story_id = st.session_state.loaded_story_id or story_id_input
            audio_cache_key = f"{current_story_id}_{tts_lang}"
            
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
                        # Resolve relative URLs and local paths to full HTTP URLs
                        # Streamlit requires full HTTP/HTTPS URLs, not local file paths
                        image_url = image['image_url']
                        
                        # If it's already a full HTTP/HTTPS URL, use it as-is
                        if not image_url.startswith(('http://', 'https://')):
                            # Handle old format: storage/images/stories/...
                            if image_url.startswith('storage/images/'):
                                # Convert to API endpoint path
                                relative_path = image_url.replace('storage/images/', '')
                                image_url = f"{API_BASE_URL.rstrip('/')}/api/v1/stories/images/{relative_path}"
                            # If it's a relative URL (starts with /), prepend API base URL
                            elif image_url.startswith('/'):
                                image_url = f"{API_BASE_URL.rstrip('/')}{image_url}"
                            # If it contains stories/, try to construct the API URL
                            elif 'stories/' in image_url:
                                # Extract the part after stories/
                                if 'stories/' in image_url:
                                    parts = image_url.split('stories/', 1)
                                    if len(parts) == 2:
                                        image_url = f"{API_BASE_URL.rstrip('/')}/api/v1/stories/images/stories/{parts[1]}"
                                    else:
                                        image_url = f"{API_BASE_URL.rstrip('/')}/api/v1/stories/images/{image_url}"
                            else:
                                # Unknown format - try to use as API path
                                image_url = f"{API_BASE_URL.rstrip('/')}/api/v1/stories/images/{image_url}"
                        
                        st.image(image_url, width='stretch')
                        with st.expander(f"Image {idx + 1} Details"):
                            st.markdown(f"**Scene:** {image.get('scene_description', 'N/A')}")
                            st.markdown(f"**Prompt Used:** {image.get('prompt_used', 'N/A')}")
                            st.markdown(f"**Order:** {image.get('display_order', 0)}")
            
            # Show full JSON
            with st.expander("View Full Story JSON"):
                st.json(story_data)

# Tab 4: All Stories
with tab4:
    st.header("All Stories")
    st.markdown("Browse and view all created stories")
    
    refresh_button = st.button("🔄 Refresh List", type="secondary")
    
    try:
        with st.spinner("Loading stories..."):
            stories_data = list_stories(limit=100, offset=0)
            stories = stories_data.get("stories", [])
            total = stories_data.get("total", 0)
        
        if total == 0:
            st.info("No stories found. Generate a story in the 'Generate Story' tab!")
        else:
            st.success(f"Found {total} story/stories")
            
            # Display stories in a list
            for idx, story in enumerate(stories):
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"### {story['title']}")
                        st.markdown(f"**Prompt:** {story['prompt'][:100]}{'...' if len(story['prompt']) > 100 else ''}")
                    
                    with col2:
                        st.markdown(f"**Age Group:** {story['age_group']}")
                        st.markdown(f"**Images:** {story['num_images']}")
                    
                    with col3:
                        st.markdown(f"**Created:**")
                        st.markdown(f"{story['created_at'][:10]}")
                        # Button to view story
                        if st.button("View Story", key=f"view_{story['id']}", type="primary"):
                            story_id_str = str(story['id'])
                            st.session_state.selected_story_id = story_id_str
                            st.session_state.story_data = {"story_id": story_id_str}
                            # Pre-load the story so it's ready when they switch tabs
                            try:
                                story_data = get_story(story_id_str)
                                st.session_state.loaded_story_data = story_data
                                st.session_state.loaded_story_id = story_id_str
                            except:
                                pass  # Will load when they switch tabs
                            
                            # Set flag to trigger tab switch on next render
                            st.session_state.switch_to_view_tab = True
                            st.success(f"✅ **Story '{story['title']}' loaded!** Switching to View Story tab...")
                            
                            st.rerun()
                    
                    if idx < len(stories) - 1:
                        st.markdown("---")
    
    except requests.exceptions.RequestException as e:
        st.error(f"Error loading stories: {str(e)}")
        st.info("Make sure the API is running and accessible.")
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>Kids Story Agent - Test Interface</div>",
    unsafe_allow_html=True
)
