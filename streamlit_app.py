import streamlit as st
import requests
import time
import uuid
from typing import Optional
from dotenv import load_dotenv
import os
from gtts import gTTS
import io
import hashlib
from app.utils.url import convert_local_path_to_url

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

# For browser-facing URLs (images/videos), use localhost if we're in Docker
# This allows the browser to access the API even when Streamlit is in a container
BROWSER_API_BASE_URL = os.getenv("BROWSER_API_BASE_URL", "http://localhost:8000")
# If API_BASE_URL is the internal Docker service name, use localhost for browser
if API_BASE_URL.startswith("http://api:") or API_BASE_URL.startswith("https://api:"):
    BROWSER_API_BASE_URL = API_BASE_URL.replace("api:", "localhost:")


st.set_page_config(
    page_title="Kids Story Agent - Test UI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
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
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def generate_story(prompt: str, age_group: str, num_illustrations: int, 
                  generate_images: bool = True, generate_videos: bool = False,
                  webhook_url: Optional[str] = None) -> dict:
    """Submit story generation request"""
    url = f"{API_BASE_URL}/api/v1/stories/generate"
    payload = {
        "prompt": prompt,
        "age_group": age_group,
        "num_illustrations": num_illustrations,
        "generate_images": generate_images,
        "generate_videos": generate_videos,
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


def list_rejected_stories(limit: int = 100, offset: int = 0) -> dict:
    """List all rejected stories"""
    url = f"{API_BASE_URL}/api/v1/stories/rejected"
    params = {"limit": limit, "offset": offset}
    response = requests.get(url, params=params, timeout=5)
    response.raise_for_status()
    return response.json()


def generate_audio(text: str, story_id: str, lang: str = "en") -> Optional[bytes]:
    """Generate audio from text using gTTS"""
    try:
        # Create a hash of the text to cache audio
        text_hash = hashlib.sha256(f"{story_id}_{text}".encode()).hexdigest()
        
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
if st.session_state.switch_to_view_tab:
    st.info("Story loaded! Switch to the **View Story** tab to see it.")
    st.session_state.switch_to_view_tab = False

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Generate Story", "Check Status", "View Story", "All Stories", "📋 Review Queue", "❌ Rejected Stories"])

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
                help="Number of images/videos to generate"
            )
        
        # Checkboxes for generation options - INSIDE the form
        st.markdown("---")
        st.markdown("#### 📸 Media Generation Options")
        st.markdown("Select which media types you want to generate:")
        
        col_check1, col_check2 = st.columns(2)
        with col_check1:
            generate_images = st.checkbox(
                "🖼️ **Generate Images**",
                value=True,
                key="form_generate_images",
                help="Enable image generation using DALL-E 3"
            )
        with col_check2:
            generate_videos = st.checkbox(
                "🎬 **Generate Videos**",
                value=False,
                key="form_generate_videos",
                help="Enable video generation using Sora (max 10 seconds per video)"
            )
        
        # Show warning if neither is selected
        if not generate_images and not generate_videos:
            st.warning("⚠️ **Warning:** Please select at least one media type (Images or Videos) to generate.")
        
        st.markdown("---")
        
        webhook_url = st.text_input(
            "Webhook URL (Optional)",
            placeholder="https://your-app.com/webhook",
            help="Optional webhook URL to receive completion notification"
        )
        
        submitted = st.form_submit_button("Generate Story", type="primary")
        
        if submitted:
            if not prompt.strip():
                st.error("Please enter a story prompt")
            elif not generate_images and not generate_videos:
                st.error("⚠️ Please select at least one media type (Images or Videos) to generate.")
            else:
                with st.spinner("Submitting story generation request..."):
                    result = generate_story(
                        prompt=prompt,
                        age_group=age_group,
                        num_illustrations=num_illustrations,
                        generate_images=generate_images,
                        generate_videos=generate_videos,
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
            
            # Display images
            if story_data.get('images'):
                st.markdown(f"### Illustrations ({len(story_data['images'])} images)")
                cols = st.columns(min(3, len(story_data['images'])))
                for idx, image in enumerate(story_data['images']):
                    col = cols[idx % len(cols)]
                    with col:
                        # Resolve relative URLs and local paths to full HTTP URLs
                        # Use BROWSER_API_BASE_URL for browser-accessible URLs
                        image_url = convert_local_path_to_url(
                            image['image_url'],
                            "image",
                            api_base_url=BROWSER_API_BASE_URL
                        )
                        # Replace internal Docker service URLs with browser-accessible URLs
                        if image_url.startswith("http://api:") or image_url.startswith("https://api:"):
                            image_url = image_url.replace("http://api:", "http://localhost:").replace("https://api:", "https://localhost:")
                        st.image(image_url, width='stretch')
                        with st.expander(f"Image {idx + 1} Details"):
                            st.markdown(f"**Scene:** {image.get('scene_description', 'N/A')}")
                            st.markdown(f"**Prompt Used:** {image.get('prompt_used', 'N/A')}")
                            st.markdown(f"**Order:** {image.get('display_order', 0)}")
            
            # Display videos
            if story_data.get('videos'):
                st.markdown("---")
                st.markdown(f"### Videos ({len(story_data['videos'])} videos)")
                cols = st.columns(min(3, len(story_data['videos'])))
                for idx, video in enumerate(story_data['videos']):
                    col = cols[idx % len(cols)]
                    with col:
                        # Resolve relative URLs and local paths to full HTTP URLs
                        video_url = convert_local_path_to_url(
                            video['video_url'],
                            "video",
                            api_base_url=BROWSER_API_BASE_URL
                        )
                        # Replace internal Docker service URLs with browser-accessible URLs
                        if video_url.startswith("http://api:") or video_url.startswith("https://api:"):
                            video_url = video_url.replace("http://api:", "http://localhost:").replace("https://api:", "https://localhost:")
                        st.video(video_url)
                        with st.expander(f"Video {idx + 1} Details"):
                            st.markdown(f"**Scene:** {video.get('scene_description', 'N/A')}")
                            st.markdown(f"**Prompt Used:** {video.get('prompt_used', 'N/A')}")
                            st.markdown(f"**Order:** {video.get('display_order', 0)}")
            
            # Show full JSON
            with st.expander("View Full Story JSON"):
                st.json(story_data)

# Tab 4: Approved Stories
with tab4:
    st.header("✅ Approved Stories")
    st.markdown("Browse and view all approved and published stories")
    
    refresh_button = st.button("🔄 Refresh List", type="secondary", key="refresh_approved_stories")
    
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
                            except Exception:
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

# Tab 5: Review Queue
with tab5:
    st.header("📋 Review Queue")
    st.markdown("Approve or reject stories before they are published.")

    def fetch_pending_reviews():
        """Fetch stories pending human review from the API."""
        try:
            resp = requests.get(
                f"{API_BASE_URL}/api/v1/reviews/pending",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching reviews: {e}")
            return None

    def fetch_review_detail(job_id: str):
        """Fetch the full review package for a story."""
        try:
            resp = requests.get(
                f"{API_BASE_URL}/api/v1/reviews/{job_id}",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching review detail: {e}")
            return None

    def submit_decision(job_id: str, decision: str, comment: str = "", reviewer_id: str = ""):
        """Submit a review decision (approve/reject)."""
        try:
            resp = requests.post(
                f"{API_BASE_URL}/api/v1/reviews/{job_id}/decide",
                json={"decision": decision, "comment": comment, "reviewer_id": reviewer_id},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error submitting decision: {e}")
            return None

    def regenerate_story_api(job_id: str):
        """Request regeneration of a rejected story."""
        try:
            resp = requests.post(
                f"{API_BASE_URL}/api/v1/reviews/{job_id}/regenerate",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            st.error(f"Error regenerating story: {e}")
            return None

    # Reviewer identity
    reviewer_id = st.text_input("Your Reviewer ID", value="reviewer_1", key="reviewer_id_input")

    # Refresh
    if st.button("🔄 Refresh Review Queue", type="secondary", key="refresh_review_queue"):
        st.rerun()

    pending = fetch_pending_reviews()
    if pending is None:
        st.info("Unable to load review queue. Ensure the API is running.")
    elif pending["total"] == 0:
        st.success("🎉 No stories pending review!")
    else:
        st.info(f"**{pending['total']}** stories awaiting review")

        for item in pending["reviews"]:
            job_id = str(item["job_id"])

            with st.expander(
                f"{'🚫' if item['num_hard_violations'] > 0 else '✅'} "
                f"{item.get('story_title') or 'Untitled'} — "
                f"Age {item['age_group']} — "
                f"Score {item.get('overall_eval_score', 'N/A')}/10 — "
                f"{item['num_hard_violations']} hard, {item['num_soft_violations']} soft",
                expanded=False,
            ):
                st.markdown(f"**Job ID:** `{job_id}`")
                st.markdown(f"**Prompt:** {item['prompt'][:200]}")
                st.markdown(f"**Created:** {item['created_at']}")
                st.markdown(f"**Images:** {item.get('num_images', 0)} | **Videos:** {item.get('num_videos', 0)}")

                # Load full detail
                if st.button("Load Full Review", key=f"load_review_{job_id}"):
                    detail = fetch_review_detail(job_id)
                    if detail:
                        st.session_state[f"review_detail_{job_id}"] = detail

                detail = st.session_state.get(f"review_detail_{job_id}")
                if detail:
                    # ─── Evaluation Scores ───
                    eval_scores = detail.get("evaluation_scores")
                    if eval_scores:
                        st.markdown("#### 📊 Evaluation Scores")
                        score_cols = st.columns(5)
                        labels = [
                            ("Moral", "moral_score"),
                            ("Theme", "theme_appropriateness"),
                            ("Emotion", "emotional_positivity"),
                            ("Age Fit", "age_appropriateness"),
                            ("Education", "educational_value"),
                        ]
                        for col, (label, key) in zip(score_cols, labels):
                            with col:
                                val = eval_scores.get(key, 0)
                                st.metric(label, f"{val}/10")
                        st.markdown(f"**Overall:** {eval_scores.get('overall_score', 'N/A')}/10")
                        if eval_scores.get("evaluation_summary"):
                            st.info(eval_scores["evaluation_summary"])

                    # ─── Guardrail Summary ───
                    st.markdown("#### 🛡️ Guardrail Report")
                    if detail.get("guardrail_summary"):
                        st.text(detail["guardrail_summary"])

                    violations = detail.get("violations", [])
                    if violations:
                        for v in violations:
                            severity_icon = "🚫" if v["severity"] == "hard" else "⚠️"
                            st.markdown(
                                f"{severity_icon} **{v['guardrail_name']}** "
                                f"({v['media_type']}"
                                f"{' #' + str(v['media_index']) if v.get('media_index') is not None else ''}) "
                                f"— conf: {v['confidence']:.2f} — {v.get('detail', '')}"
                            )

                    # ─── Story Text ───
                    if detail.get("story_text"):
                        st.markdown("#### 📖 Story")
                        st.markdown(detail["story_text"])

                    # ─── Images ───
                    if detail.get("image_urls"):
                        st.markdown("#### 🖼️ Images")
                        img_cols = st.columns(min(3, len(detail["image_urls"])))
                        for idx, url in enumerate(detail["image_urls"]):
                            with img_cols[idx % len(img_cols)]:
                                resolved = convert_local_path_to_url(url, "image", api_base_url=BROWSER_API_BASE_URL)
                                # Replace internal Docker service URLs with browser-accessible URLs
                                if resolved.startswith("http://api:") or resolved.startswith("https://api:"):
                                    resolved = resolved.replace("http://api:", "http://localhost:").replace("https://api:", "https://localhost:")
                                st.image(resolved, caption=f"Image {idx + 1}")

                    # ─── Videos ───
                    if detail.get("video_urls"):
                        st.markdown("#### 🎬 Videos")
                        vid_cols = st.columns(min(3, len(detail["video_urls"])))
                        for idx, url in enumerate(detail["video_urls"]):
                            with vid_cols[idx % len(vid_cols)]:
                                resolved = convert_local_path_to_url(url, "video", api_base_url=BROWSER_API_BASE_URL)
                                # Replace internal Docker service URLs with browser-accessible URLs
                                if resolved.startswith("http://api:") or resolved.startswith("https://api:"):
                                    resolved = resolved.replace("http://api:", "http://localhost:").replace("https://api:", "https://localhost:")
                                st.video(resolved)

                    # ─── Decision Buttons ───
                    st.markdown("---")
                    comment = st.text_area(
                        "Review Comment (optional)",
                        key=f"comment_{job_id}",
                        placeholder="Add any notes for your review...",
                    )

                    btn_cols = st.columns(3)
                    with btn_cols[0]:
                        if st.button("✅ Approve", key=f"approve_{job_id}", type="primary"):
                            result = submit_decision(job_id, "approved", comment, reviewer_id)
                            if result:
                                st.success(f"✅ {result.get('message', 'Approved!')}")
                                # Clean up
                                if f"review_detail_{job_id}" in st.session_state:
                                    del st.session_state[f"review_detail_{job_id}"]
                                time.sleep(1)
                                st.rerun()

                    with btn_cols[1]:
                        if st.button("❌ Reject", key=f"reject_{job_id}", type="secondary"):
                            result = submit_decision(job_id, "rejected", comment, reviewer_id)
                            if result:
                                st.warning(f"❌ {result.get('message', 'Rejected.')}")
                                if f"review_detail_{job_id}" in st.session_state:
                                    del st.session_state[f"review_detail_{job_id}"]
                                time.sleep(1)
                                st.rerun()

                    with btn_cols[2]:
                        if st.button("🔄 Reject & Regenerate", key=f"regen_{job_id}"):
                            # First reject
                            rej_result = submit_decision(job_id, "rejected", comment, reviewer_id)
                            if rej_result:
                                # Then regenerate
                                regen_result = regenerate_story_api(job_id)
                                if regen_result:
                                    st.info(
                                        f"🔄 New job created: `{regen_result['new_job_id']}` "
                                        f"(linked to original `{job_id}`)"
                                    )
                                if f"review_detail_{job_id}" in st.session_state:
                                    del st.session_state[f"review_detail_{job_id}"]
                                time.sleep(1)
                                st.rerun()

# Tab 6: Rejected Stories
with tab6:
    st.header("❌ Rejected Stories")
    st.markdown("View all stories that were rejected (by LLM/guardrails or human reviewers)")
    
    refresh_button = st.button("🔄 Refresh List", type="secondary", key="refresh_rejected_stories")
    
    try:
        with st.spinner("Loading rejected stories..."):
            rejected_data = list_rejected_stories(limit=100, offset=0)
            rejected_stories = rejected_data.get("stories", [])
            total = rejected_data.get("total", 0)
        
        if total == 0:
            st.info("No rejected stories found.")
        else:
            st.success(f"Found {total} rejected story/stories")
            
            # Display rejected stories in a list
            for idx, story in enumerate(rejected_stories):
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"### {story.get('story_title', 'Untitled Story')}")
                        st.markdown(f"**Prompt:** {story.get('prompt', '')[:100]}{'...' if len(story.get('prompt', '')) > 100 else ''}")
                        
                        # Display rejection reason
                        rejection_reason = story.get('rejection_reason', 'unknown')
                        if rejection_reason == 'llm_guardrail':
                            st.markdown("**Rejection Type:** 🤖 LLM/Guardrail")
                        elif rejection_reason == 'human':
                            st.markdown("**Rejection Type:** 👤 Human")
                        elif rejection_reason == 'timeout':
                            st.markdown("**Rejection Type:** ⏰ Timeout")
                        else:
                            st.markdown(f"**Rejection Type:** {rejection_reason or 'Unknown'}")
                        
                        # Display comment/reason
                        comment = story.get('comment', '')
                        if comment:
                            st.markdown(f"**Reason/Comment:** {comment}")
                        else:
                            st.markdown("*No comment provided*")
                    
                    with col2:
                        st.markdown(f"**Age Group:** {story.get('age_group', 'N/A')}")
                        st.markdown(f"**Created:**")
                        created_at = story.get('created_at', '')
                        if created_at:
                            st.markdown(f"{created_at[:10] if isinstance(created_at, str) else str(created_at)[:10]}")
                        
                        reviewed_at = story.get('reviewed_at')
                        if reviewed_at:
                            st.markdown(f"**Reviewed:**")
                            st.markdown(f"{reviewed_at[:10] if isinstance(reviewed_at, str) else str(reviewed_at)[:10]}")
                        
                        reviewer_id = story.get('reviewer_id')
                        if reviewer_id:
                            st.markdown(f"**Reviewer:** {reviewer_id}")
                    
                    with col3:
                        job_id = story.get('job_id')
                        if job_id:
                            # Button to view job details
                            if st.button("View Details", key=f"view_rejected_{job_id}", type="primary"):
                                st.info(f"Job ID: `{job_id}` - Use 'Check Status' tab to view job details")
                    
                    # Display story content and images in an expandable section
                    story_content = story.get('story_content')
                    image_urls = story.get('image_urls', [])
                    
                    if story_content or image_urls:
                        with st.expander(f"📖 View Story Content & Images", expanded=False):
                            if story_content:
                                st.markdown("### Story Content")
                                st.markdown(story_content)
                                st.markdown("---")
                            
                            if image_urls:
                                st.markdown(f"### Generated Images ({len(image_urls)} images)")
                                # Display images in columns
                                img_cols = st.columns(min(3, len(image_urls)))
                                for img_idx, img_url in enumerate(image_urls):
                                    with img_cols[img_idx % len(img_cols)]:
                                        # Convert to browser-accessible URL
                                        browser_url = convert_local_path_to_url(
                                            img_url,
                                            "image",
                                            api_base_url=BROWSER_API_BASE_URL
                                        )
                                        # Replace internal Docker service URLs
                                        if browser_url.startswith("http://api:") or browser_url.startswith("https://api:"):
                                            browser_url = browser_url.replace("http://api:", "http://localhost:").replace("https://api:", "https://localhost:")
                                        st.image(browser_url, caption=f"Image {img_idx + 1}", use_container_width=True)
                            elif story_content:
                                st.info("No images were generated for this story.")
                            else:
                                st.info("Story content and images are not available for this rejected story.")
                    
                    if idx < len(rejected_stories) - 1:
                        st.markdown("---")
    
    except requests.exceptions.RequestException as e:
        st.error(f"Error loading rejected stories: {str(e)}")
        st.info("Make sure the API is running and accessible.")
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")


# Footer
st.markdown("---")
st.caption("Kids Story Agent - Test Interface")
