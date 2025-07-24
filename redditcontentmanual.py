import praw
from moviepy.editor import *
from google.cloud import texttospeech
import os
from PIL import Image # Retained for potential future use, but not for current background
import random
from faster_whisper import WhisperModel # Added for word-level timestamps
import unicodedata
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import re
from dotenv import load_dotenv
from openai import OpenAI  # <-- Add this at the top, replace 'import openai'
import gc
import time

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OpenAI.api_key = OPENAI_API_KEY

os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
# ---- Reddit Setup ---- #
REDDIT_CLIENT_ID = "lId4BZPOYJUTBXhArBnswA" # Replace with your actual ID
REDDIT_CLIENT_SECRET = "rkK0OEceurFnL6xNMNEeN_XZFK1lJg" # Replace with your actual secret
REDDIT_USER_AGENT = "script:ContentMaker:v1.0 (by u/veexer)" # Replace with your user agent
SUBREDDIT = "showerthoughts"
# Polish translations for subreddit names
SUBREDDIT_PL_TRANSLATIONS = {
    "AskReddit": "ZapytajReddita",
    "AskMen": "ZapytajMężczyzn",
    "AskWomen": "ZapytajKobiety",
    "RelationshipAdvice": "PoradyZwiązkowe",
    "confession": "Wyznania",
    "relationships": "Związki",
    "teenagers": "Nastolatkowie",
    "NoStupidQuestions": "NieMaGłupichPytań",
    "TrueOffMyChest": "KamieńZSerca",
    "UnpopularOpinion": "NiepopularnaOpinia",
    "TooAfraidToAsk": "StrachZapytać",
    "WouldYouRather": "CoWolałbyś",
    "showerthoughts": "MyśliSpodPrysznica"
}
# ---- Video Constants ---- #
VIDEO_WIDTH, VIDEO_HEIGHT = 1080, 1920
BACKGROUND_VIDEO_CHOICES = ["MCPARKOUR.mp4", "MCPARKOUR1.mp4","MCPARKOUR2.mp4","MCPARKOUR3.mp4","MCPARKOUR4.mp4","MCPARKOUR5.mp4","MCPARKOUR6.mp4", "SSbackground.mp4","SSBackground2.mp4"]
BACKGROUND_MUSIC_PATH = "Charm - Anno Domini Beats.mp3" # Path to your background music file
USED_THREADS_FILE = "used_threads_pl.txt"

# ---- Audio Speed & Volume Settings ----
TITLE_AUDIO_SPEED = 1.10         # Speed for title TTS
COMMENT_AUDIO_SPEED = 1.10       # Speed for comment TTS
TRANSITION_AUDIO_SPEED = 1.0     # Speed for transition sound
TRANSITION_VOLUME = 0.6          # 60% volume (lowered by 40%)
BG_MUSIC_VOLUME = 0.1            # 10% volume for background music

def safe_remove(filepath, retries=5, delay=0.5):
    """Try to remove a file, retrying if it's locked (Windows MoviePy bug workaround)."""
    for attempt in range(retries):
        try:
            os.remove(filepath)
            return True
        except PermissionError:
            gc.collect()  # Force garbage collection to release file handles
            time.sleep(delay)
        except Exception as e:
            print(f"Error removing {filepath}: {e}")
            break
    print(f"Could not remove temp audio file {filepath}: still locked after {retries} attempts.")
    return False
# ---- Fetch Reddit Content ---- #
def load_used_threads():
    if not os.path.exists(USED_THREADS_FILE):
        return set()
    with open(USED_THREADS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines())

def save_used_thread(title):
    with open(USED_THREADS_FILE, "a", encoding="utf-8") as f:
        f.write(title.strip() + "\n")

def fetch_reddit_post():
    N = 7  # Number of comments you want in your video
    MAX_COMMENT_LEN = 250
    used_threads = load_used_threads()
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )
    SUBREDDIT_CHOICES = [
        "showerthoughts", "AskReddit", "AskMen", "AskWomen", "RelationshipAdvice",
        "confession", "relationships", "teenagers", "NoStupidQuestions",
        "TrueOffMyChest", "UnpopularOpinion", "TooAfraidToAsk", "WouldYouRather"
    ]
    subreddit_name = random.choice(SUBREDDIT_CHOICES)
    print(f"Fetching from subreddit: r/{subreddit_name}")

    posts = list(reddit.subreddit(subreddit_name).top(time_filter="week", limit=20))
    if not posts:
        print("No posts found.")
        return None, None, [], subreddit_name

    def title_has_image(title):
        title_lower = title.lower()
        image_keywords = ['.jpg', '.jpeg', '.png', '.gif', 'imgur.com', 'i.redd.it', 'http', 'https', 'pic.twitter.com']
        return any(keyword in title_lower for keyword in image_keywords)

    for post in posts:
        if post.title.strip() not in used_threads and not title_has_image(post.title):
            top_post = post
            break
    else:
        for post in posts:
            if post.title.strip() not in used_threads:
                top_post = post
                break
        else:
            print("No new posts found that haven't been used before.")
            return None, None, [], subreddit_name

    comments = []
    comment_map = {}
    parent_map = {}
    if hasattr(top_post.comments, 'list'):
        top_post.comments.replace_more(limit=0)
        all_comments = [
            c for c in top_post.comments.list()
            if isinstance(c, praw.models.Comment)
            and c.body
            and not c.stickied
            and len(c.body) < MAX_COMMENT_LEN
        ]
        all_comments.sort(key=lambda c: getattr(c, 'score', 0), reverse=True)
        top_comments_pool = all_comments[:25]
        # Build maps for parent-child relationships
        for c in top_comments_pool:
            cid = c.id
            parent_id = c.parent_id.split('_')[-1] if hasattr(c, 'parent_id') else None
            comment_map[cid] = c
            parent_map[cid] = parent_id

        # Helper to recursively add parent before child
        def add_with_parents(cid, added, result):
            pid = parent_map.get(cid)
            if pid and pid in comment_map and pid not in added:
                add_with_parents(pid, added, result)
            if cid not in added:
                c = comment_map[cid]
                author = c.author.name if c.author else '[deleted]'
                result.append(f"{author}: {c.body}")
                added.add(cid)

        added = set()
        result = []
        for c in top_comments_pool:
            add_with_parents(c.id, added, result)
            if len(result) >= N:
                break
        comments = result[:N]
        if not comments:
            print("Not enough comments found. Skipping thread.")
            save_used_thread(top_post.title)  # <--- Save original title if skipping!
            return None, None, [], subreddit_name
    else:
        print("Could not retrieve comment list.")
        save_used_thread(top_post.title)  # <--- Save original title if skipping!
        return None, None, [], subreddit_name

    return top_post.title, top_post.selftext, comments, subreddit_name

# ---- TTS Generation ---- #
from google.cloud import texttospeech

def text_to_speech_gtts(text, filename):
    """Generate TTS using Google Cloud TTS with a natural WaveNet voice."""
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code="pl-PL",
        name="pl-PL-Wavenet-B"  # Best for AskReddit style!
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.08  # Slightly faster, tweak if you want!
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        with open(filename, "wb") as out:
            out.write(response.audio_content)
        return True
    except Exception as e:
        print(f"Error generating TTS for '{text[:30]}...': {e}")
        return False

# ---- Faster Whisper Functions (from backup.py) ---- #
def get_word_timestamps(audio_path):
    """Transcribe audio and return word-level timestamps using faster-whisper."""
    # Consider making model a global variable or passing it to avoid reloading
    # For simplicity here, loading it each time.
    # Common models: "tiny", "base", "small", "medium", "large-v2"
    # "base" is a good starting point for balance.
    try:
        # Suppress excessive logging from faster-whisper if possible
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, word_timestamps=True)
        word_timings = []
        for segment in segments:
            for word in segment.words:
                word_timings.append({
                    "word": word.word,
                    "start": word.start,
                    "end": word.end
                })
        return word_timings
    except Exception as e:
        print(f"Error getting word timestamps for {audio_path}: {e}")
        return []

# --- Helper for colored username in subtitles ---
def make_highlighted_subtitle(sentence, highlight_idx, highlight_color="#FF4567", base_color="white", highlight_bg_color="black", username_color="#00BFFF"):
    # Split on first colon to separate username
    if ':' in sentence:
        username, rest = sentence.split(':', 1)
        username_words = username.split()
        rest_words = rest.strip().split()
        words = username_words + [':'] + rest_words
        username_len = len(username_words) + 1  # +1 for the colon
    else:
        words = sentence.split()
        username_len = 0

    styled = []
    for i, word in enumerate(words):
        clean_word = word.strip(".,?!")
        if i < username_len:
            color = username_color
        else:
            color = base_color
        if i == highlight_idx:
            styled.append(f"<span foreground='{highlight_color}' background='{highlight_bg_color}'>{clean_word}</span>")
        else:
            styled.append(f"<span foreground='{color}'>{clean_word}</span>")
    return " ".join(styled)

# --- Update create_word_synced_subtitles to use the new make_highlighted_subtitle ---
def create_word_synced_subtitles(audio_path, sentence, video_width, offset=0, color='white'):
    word_timings = get_word_timestamps(audio_path)
    audio_duration = AudioFileClip(audio_path).duration
    subtitle_font = r"C:\Windows\Fonts\NotoSans-Regular.ttf"  # or 'Arial'

    if not word_timings:
        txt = sanitize_text(sentence)
        if not txt.strip():
            txt = "..."  # fallback for empty text
        return [
            TextClip(
                txt,
                fontsize=120,
                color=color,
                font=subtitle_font,
                stroke_color='black',
                stroke_width=10,
                bg_color='rgba(0,0,0,0.7)',
                size=(video_width * 0.85, None),
                method='pango',
                align='center',
                print_cmd=False
            ).set_position(('center', 'center')).set_duration(audio_duration).set_start(offset)
        ]

    if ':' in sentence:
        username, rest = sentence.split(':', 1)
        username = username.strip()
        rest = rest.strip()
        username_words = username.split()
        rest_words = rest.split()
        words = username_words + [':'] + rest_words
        username_len = len(username_words) + 1
    else:
        words = sentence.split()
        username_len = 0

    clips = []
    for idx, word_info in enumerate(word_timings):
        word = words[username_len + idx] if (username_len + idx) < len(words) else ""
        txt = sanitize_text(word)
        if not txt.strip():
            print(f"[DEBUG] Skipping empty word at idx {idx}")
            continue  # Skip creating a TextClip for empty text!
        start = word_info["start"]
        end = word_info["end"]
        duration = max(0.01, end - start)

        # Dynamically set font size based on word length
        if len(txt) > 10:
            fontsize = 80  # Smaller font for long words
        else:
            fontsize = 120  # Default font size

        txt_clip = TextClip(
            txt,
            fontsize=fontsize,
            color=color,
            font=subtitle_font,
            stroke_color='black',
            stroke_width=10,
            bg_color='rgba(0,0,0,0.7)',
            size=(video_width * 0.90, None),
            method='pango',
            align='center',
            print_cmd=False
        ).set_start(start + offset).set_duration(duration).set_position(('center', 'center'))
        clips.append(txt_clip)
    return clips


# ---- Create Video ---- #
MAX_VIDEO_DURATION = 120  # seconds
MIN_VIDEO_DURATION = 30  # seconds

def create_video(title, comments):
    color_palette = [
        "#FF4500", "#00BFFF", "#FFD700", "#32CD32",
        "#FF69B4", "#FFFFFF", "#00FFFF", "#FFA500",
    ]

    BACKGROUND_VIDEO_CHOICES = [
        "MCPARKOUR.mp4", "MCPARKOUR1.mp4", "MCPARKOUR2.mp4", "MCPARKOUR3.mp4",
        "MCPARKOUR4.mp4", "MCPARKOUR5.mp4", "MCPARKOUR6.mp4", "SSbackground.mp4", "SSBackground2.mp4"
    ]
    background_video_path = random.choice(BACKGROUND_VIDEO_CHOICES)
    if not os.path.exists(background_video_path):
        print(f"Error: Background video '{background_video_path}' not found. Please place it in the project directory.")
        return
    print(f"Using background video: {background_video_path}")

    background_video_full = VideoFileClip(background_video_path)

    background_music_clip = None
    if os.path.exists(BACKGROUND_MUSIC_PATH):
        background_music_clip = AudioFileClip(BACKGROUND_MUSIC_PATH)
    else:
        print(f"Warning: Background music '{BACKGROUND_MUSIC_PATH}' not found. Continuing without music.")

    # Prepare the sped-up transition sound
    transition_path = r"C:\Users\veexe\Documents\code\EDITING\transition.mp3"
    transition_fast_path = r"C:\Users\veexe\Documents\code\EDITING\transition_fast.mp3"
    speedup_transition(transition_path, transition_fast_path, speed=TRANSITION_AUDIO_SPEED)
    transition_audio_clip = AudioFileClip(transition_fast_path).volumex(TRANSITION_VOLUME)
    transition_duration = transition_audio_clip.duration

    cumulative_comment_audio_duration = 0
    tts_audio_clips_to_concat = []
    all_comment_audio_clips = []
    all_comment_subtitle_clips = []
    audio_files_to_cleanup = [transition_fast_path]

    # --- Handle Title Audio ---
    title_audio_path = "temp_title.mp3"
    title_audio_clip = None
    title_duration = 0

    if title:
        print(f"Processing title audio: {title[:60]}...")
        if text_to_speech_gtts(title, title_audio_path):
            audio_files_to_cleanup.append(title_audio_path)
            spedup_title_audio_path = "temp_title_fast.mp3"
            speedup_audio(title_audio_path, spedup_title_audio_path, speed=TITLE_AUDIO_SPEED)
            audio_files_to_cleanup.append(spedup_title_audio_path)
            try:
                title_audio_clip = AudioFileClip(spedup_title_audio_path)
                title_duration = title_audio_clip.duration
            except Exception as e:
                print(f"Error loading audio for title: {e}. Title audio will be skipped.")
                title_audio_clip = None

    if title_audio_clip:
        tts_audio_clips_to_concat.append(title_audio_clip)
        tts_audio_clips_to_concat.append(transition_audio_clip)
        cumulative_comment_audio_duration += title_duration + transition_duration

    url_or_file_pattern = re.compile(
        r"(https?://|www\.|\.jpg|\.jpeg|\.png|\.gif|\.bmp|\.mp4|\.avi|\.mov|\.webm|\.pdf|\.doc|\.xls|\.ppt|\.zip|\.rar|\.7z|\.tar|\.gz|imgur\.com|i\.redd\.it|pic\.twitter\.com)",
        re.IGNORECASE
    )

    for i, comment_text in enumerate(comments):
        if url_or_file_pattern.search(comment_text):
            continue

        print(f"Processing comment {i+1}/{len(comments)}: {comment_text[:60]}...")
        audio_path = f"temp_comment_{i}.mp3"

        # Only pass the comment (not username) to TTS
        if ':' in comment_text:
            _, comment_body = comment_text.split(':', 1)
            tts_text = comment_body.strip()
        else:
            tts_text = comment_text

        if not text_to_speech_gtts(tts_text, audio_path):
            continue

        spedup_audio_path = f"temp_comment_{i}_fast.mp3"
        speedup_audio(audio_path, spedup_audio_path, speed=COMMENT_AUDIO_SPEED)
        trimmed_audio_path = f"temp_comment_{i}_fast_trimmed.mp3"
        trim_silence(spedup_audio_path, trimmed_audio_path)
        audio_files_to_cleanup.extend([audio_path, spedup_audio_path, trimmed_audio_path])
        audio_path = trimmed_audio_path

        try:
            current_audio_clip = AudioFileClip(audio_path)
            comment_duration = current_audio_clip.duration
            if comment_duration <= 0:
                current_audio_clip.close()
                continue
        except Exception as e:
            continue

        # Check if adding this comment would exceed max duration
        projected_duration = cumulative_comment_audio_duration + comment_duration + transition_duration
        if projected_duration > MAX_VIDEO_DURATION:
            current_audio_clip.close()
            break  # Stop adding more comments

        comment_color = color_palette[i % len(color_palette)]

        subtitle_clips = create_word_synced_subtitles(
            audio_path,
            comment_text,
            VIDEO_WIDTH,
            offset=cumulative_comment_audio_duration,
            color=comment_color
        )

        all_comment_subtitle_clips.extend(subtitle_clips)
        all_comment_audio_clips.append(current_audio_clip)
        tts_audio_clips_to_concat.append(transition_audio_clip)
        tts_audio_clips_to_concat.append(current_audio_clip)
        cumulative_comment_audio_duration = projected_duration

    # After loop, check if total duration is at least MIN_VIDEO_DURATION
    if cumulative_comment_audio_duration < MIN_VIDEO_DURATION:
        print(f"Video too short ({cumulative_comment_audio_duration:.2f}s). Skipping.")
        background_video_full.close()
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file): os.remove(aud_file)
        return

    # Combine audio clips: Title audio first, followed by comment audio (TTS track)
    if tts_audio_clips_to_concat:
        final_audio_clip = concatenate_audioclips(tts_audio_clips_to_concat)
    else:
        print("No TTS audio clips generated. Cannot create video.")
        background_video_full.close()
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file): os.remove(aud_file)
        return

    total_video_duration = final_audio_clip.duration

    # --- Ensure last subtitle isn't cut off ---
    if all_comment_subtitle_clips:
        last_sub_end = max([clip.end for clip in all_comment_subtitle_clips])
        if last_sub_end > total_video_duration:
            print(f"[INFO] Extending video duration from {total_video_duration:.2f}s to {last_sub_end + 0.1:.2f}s to fit last subtitle.")
            total_video_duration = last_sub_end + 0.1

    # --- Handle Title Text Clip (visible for the whole video) ---
    title_text_clip = None
    if title and total_video_duration > 0:
        if title.startswith("[r/"):
            end_idx = title.find("]")
            if end_idx != -1:
                subreddit_part = title[:end_idx+1]
                rest_title = title[end_idx+1:].strip()
            else:
                subreddit_part = ""
                rest_title = title
        else:
            subreddit_part = ""
            rest_title = title

        colored_title = f"<span foreground='#FF4500'>{subreddit_part}</span> <span foreground='white'>{rest_title}</span>"
        colored_title = sanitize_text(colored_title)

        title_text_clip = TextClip(
            colored_title,
            fontsize=60,
            font='Noto-Sans',
            stroke_color='black',
            stroke_width=3,
            bg_color='rgba(0,0,0,0.6)',
            size=(VIDEO_WIDTH * 0.85, None),
            method='pango',
            align='center',
            print_cmd=False
        ).set_position(('center', 'top')).set_duration(total_video_duration)

    # --- Background Video Handling ---
    if total_video_duration <= 0:
        print("Total video duration is zero or less. Cannot create video.")
        background_video_full.close()
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file): os.remove(aud_file)
        if final_audio_clip: final_audio_clip.close()
        return

    slide_background_clip = None
    if background_video_full.duration < total_video_duration:
        num_loops = int(total_video_duration / background_video_full.duration) + 1
        looped_bg_clips_list = [background_video_full.copy() for _ in range(num_loops)]
        looped_bg_clips_list = [
            bg_clip.resize(width=VIDEO_WIDTH, height=VIDEO_HEIGHT).set_position("center")
            for bg_clip in looped_bg_clips_list
        ]
        temp_bg_concat = concatenate_videoclips(looped_bg_clips_list, method="chain")
        if temp_bg_concat is not None:
            slide_background_clip = temp_bg_concat.subclip(0, total_video_duration)
            temp_bg_concat.close()
        else:
            print("Failed to concatenate background video clips.")
        for clip_copy in looped_bg_clips_list:
            try:
                clip_copy.close()
            except Exception as e:
                print(f"Error closing copied clip: {e}")
    else:
        slide_background_clip = background_video_full.subclip(0, total_video_duration)

    print(f"[DEBUG] background_video_full.duration: {background_video_full.duration}")
    print(f"[DEBUG] total_video_duration: {total_video_duration}")
    print(f"[DEBUG] slide_background_clip: {slide_background_clip}")
    print(f"[DEBUG] type(slide_background_clip): {type(slide_background_clip)}")

    if slide_background_clip is None:
        print("Error: slide_background_clip is None. Cannot proceed with video creation.")
        print(f"Debug info: background_video_full.duration={background_video_full.duration}, total_video_duration={total_video_duration}")
        background_video_full.close()
        if background_music_clip: background_music_clip.close()
        if final_audio_clip: final_audio_clip.close()
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file): os.remove(aud_file)
        return

    slide_background_clip = slide_background_clip.resize(width=VIDEO_WIDTH, height=VIDEO_HEIGHT).set_position("center")

    # --- Secondary Background (Visual Stimulation) ---
    ADDITIONAL_BG_CHOICES = ["add1.mp4", "add2.mp4", "add3.mp4", "add4.mp4"]
    additional_bg_path = random.choice(ADDITIONAL_BG_CHOICES)
    additional_bg_clip = None
    if os.path.exists(additional_bg_path):
        additional_bg_clip_full = VideoFileClip(additional_bg_path).subclip(0, min(background_video_full.duration, total_video_duration))
        if additional_bg_clip_full.duration < total_video_duration:
            num_loops = int(total_video_duration / additional_bg_clip_full.duration) + 1
            looped_clips = [additional_bg_clip_full.copy() for _ in range(num_loops)]
            temp_bg = concatenate_videoclips(looped_clips, method="chain")
            additional_bg_clip_full = temp_bg.subclip(0, total_video_duration)
            temp_bg.close()
            for clip in looped_clips:
                try:
                    clip.close()
                except Exception as e:
                    print(f"Error closing additional bg clip copy: {e}")
        target_width = int(VIDEO_WIDTH * 0.8)
        target_height = int(VIDEO_HEIGHT * 0.3)
        additional_bg_clip = additional_bg_clip_full.resize(width=target_width)
        if additional_bg_clip.h > target_height:
            y_center = additional_bg_clip.h // 2
            additional_bg_clip = additional_bg_clip.crop(
                x_center=target_width // 2,
                y_center=y_center,
                width=target_width,
                height=target_height
            )
        additional_bg_clip = additional_bg_clip.set_position(
            ("center", VIDEO_HEIGHT - target_height)
        )
    else:
        print(f"Warning: Additional background video '{additional_bg_path}' not found. Skipping.")

    if background_music_clip:
        if background_music_clip.duration < total_video_duration:
            num_music_loops = int(total_video_duration / background_music_clip.duration) + 1
            looped_music_clips = [background_music_clip.copy() for _ in range(num_music_loops)]
            temp_music_concat = concatenate_audioclips(looped_music_clips)
            bg_music_for_video = temp_music_concat.subclip(0, total_video_duration)
            temp_music_concat.close()
            for clip_copy in looped_music_clips:
                try:
                    clip_copy.close()
                except Exception as e:
                    print(f"Error closing copied music clip: {e}")
        else:
            bg_music_for_video = background_music_clip.subclip(0, total_video_duration)

        bg_music_for_video = bg_music_for_video.volumex(BG_MUSIC_VOLUME)
        final_audio_clip = CompositeAudioClip([final_audio_clip, bg_music_for_video])

    # --- Add TikTok follow animation (greenscreen removal) ---
    follow_path = "comments_of_gold.mp4"
    follow_clip = None

    if os.path.exists(follow_path) and total_video_duration > 0:
        raw_follow = VideoFileClip(follow_path).subclip(0, min(total_video_duration, VideoFileClip(follow_path).duration))
        # Remove green background with a strong filter
        follow_clip = raw_follow.fx(vfx.mask_color, color=[0,255,0], thr=150, s=15)
        # Make it huge and centered at the bottom
        follow_clip = follow_clip.resize(width=1300)
        follow_clip = follow_clip.set_position(("center", "bottom"))
        follow_clip = follow_clip.set_start(0).set_duration(total_video_duration)
    else:
        print("comment_of_gold.mp4 not found or total video duration is zero, skipping follow animation.")

    elements_for_final_composite = [slide_background_clip]
    if title_text_clip:
        elements_for_final_composite.append(title_text_clip)
    if follow_clip:
        elements_for_final_composite.append(follow_clip)
    elements_for_final_composite.extend(all_comment_subtitle_clips)

    if not elements_for_final_composite:
        print("No elements to composite. Exiting video creation.")
        background_video_full.close()
        if background_music_clip: background_music_clip.close()
        if final_audio_clip: final_audio_clip.close()
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file): os.remove(aud_file)
        return

    final_video = CompositeVideoClip(elements_for_final_composite, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    final_video = final_video.set_audio(final_audio_clip)
    final_video = final_video.set_duration(total_video_duration)

    output_dir = r"D:\autoedit\60\RedditPL"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    output_filename = os.path.join(output_dir, "reddit_video_output_1.mp4")
    count = 1
    while os.path.exists(output_filename):
        count += 1
        output_filename = os.path.join(output_dir, f"reddit_video_output_{count}.mp4")

    try:
        print(f"Writing final video to {output_filename}...")
        final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
        print("Video generation complete!")
    except Exception as e:
        print(f"Error writing final video file: {e}")
    finally:
        # Close all open video/audio clips before deleting files!
        for clip in [background_video_full, background_music_clip, final_audio_clip, title_audio_clip, transition_audio_clip]:
            if clip:
                try:
                    clip.close()
                except Exception as e:
                    print(f"Error closing clip: {e}")

        for clip in all_comment_audio_clips:
            try:
                clip.close()
            except Exception as e:
                print(f"Error closing comment audio clip: {e}")

        for clip in elements_for_final_composite:
            try:
                clip.close()
            except Exception as e:
                print(f"Error closing composite element: {e}")

        # Remove references to help garbage collection
        del background_video_full, background_music_clip, final_audio_clip, title_audio_clip, transition_audio_clip
        del all_comment_audio_clips, elements_for_final_composite

        # Force garbage collection to release file handles
        gc.collect()
        time.sleep(0.2)  # Give Windows a moment to catch up

        # Now it's safe to delete temp files!
        for aud_file in audio_files_to_cleanup:
            if os.path.exists(aud_file):
                safe_remove(aud_file)

def sanitize_text(text):
    replacements = {
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '–': '-', '—': '-', '…': '...',
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    # Remove only control characters, keep all printable Unicode (including Polish)
    text = ''.join(ch for ch in text if ch.isprintable())
    return " ".join(str(text).split())

def speedup_audio(input_path, output_path, speed):
    from moviepy.editor import AudioFileClip, vfx
    audio = AudioFileClip(input_path)
    faster_audio = audio.fx(vfx.speedx, speed)
    faster_audio.write_audiofile(output_path, logger=None)
    audio.close()
    faster_audio.close()

def speedup_transition(input_path, output_path, speed):
    from moviepy.editor import AudioFileClip, vfx
    audio = AudioFileClip(input_path)
    faster_audio = audio.fx(vfx.speedx, speed)
    faster_audio.write_audiofile(output_path, logger=None)
    audio.close()
    faster_audio.close()

def trim_silence(input_path, output_path, silence_thresh=-40, min_silence_len=250):
    audio = AudioSegment.from_file(input_path, format="mp3")
    nonsilent_ranges = detect_nonsilent(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
    if nonsilent_ranges:
        start_trim = nonsilent_ranges[0][0]
        end_trim = nonsilent_ranges[-1][1]
        trimmed_audio = audio[start_trim:end_trim]
    else:
        trimmed_audio = audio
    trimmed_audio.export(output_path, format="mp3")

def translate_content_to_polish(title, op_message, comments):
    prompt = (
        "Rewrite the following Reddit post (title, OP message, and comments) for a video script in Polish language. "
        "1. The TITLE should be rewritten as a strong hook that grabs attention, while keeping the OP's tone and staying relevant to the original title and message. "
        "2. Remove all emotes (like 😊, 😂, etc.) from the entire output, as TTS cannot read them. "
        "3. Do NOT mention TikTok or video unless the original title or message does. "
        "4. Maintain the original context and meaning, but feel free to use humor, slang, or informal language typical for Reddit (but don't overdo it). "
        "5. End with an additional comment containing a question or encouragement for viewers to comment their opinion on the topic. "
        "6. Make sure the rewritten content flows naturally and feels like something a real Redditor would say. "
        "7. Ensure the content sounds as if written by a Polish Reddit user using natural Polish language, slang and humor, while keeping the original context. "
        "8. Don't include any usernames in the comments, just the message itself. "
        "9. Suggest a short, catchy, filesystem-safe filename for the TikTok video (no special characters, max 60 chars, use underscores or dashes, no spaces). "
        "10. Suggest a list of 5 ideal TikTok tags/hashtags (as a list of strings, no # needed). "
        "Return your response ONLY as a JSON with the following fields: 'title', 'op_message', 'comments' (list), 'tiktok_filename', 'tiktok_tags' (list):\n\n"
        f"Title: {title}\n"
        f"OP: {op_message}\n"
        f"Comments:\n" +
        "\n".join([f"{i+1}. {c}" for i, c in enumerate(comments)])
    )

    import json
    import re

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model="gpt-4.1",
        input=[
            {
                "role": "system",
                "content": "You're a creative, funny Reddit script writer for video content, who captures the essence of Polish internet culture."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        text={
            "format": {
                "type": "text"
            }
        },
        temperature=0.4,
        max_output_tokens=2048,
        top_p=1,
        store=True
    )
    content = response.output.text
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return (
                data['title'],
                data.get('op_message', ''),
                extract_comments(data.get('comments', [])),
                data.get('tiktok_filename', 'reddit_video'),
                data.get('tiktok_tags', [])
            )
        except Exception as e:
            print("JSON decode error:", e)
            print("Raw OpenAI response:", match.group(0))
            return title, op_message, comments, "reddit_video", []
    else:
        print("Could not parse OpenAI response!")
        print("Raw OpenAI response:", content)
        return title, op_message, comments, "reddit_video", []

def extract_comments(comments):
    extracted = []
    for c in comments:
        if isinstance(c, dict):
            # Handle {"username": "...", "message": "..."} 
            if "username" in c and "message" in c:
                extracted.append(str(c['message']))
            # Handle {"1": "user: message"} or {"2": "user: message"}
            elif len(c) == 1:
                val = list(c.values())[0]
                # Remove username if present
                if ':' in val:
                    val = val.split(':', 1)[1].strip()
                extracted.append(str(val))
            else:
                # Fallback: join all values, remove usernames if present
                msg = " ".join(str(v) for v in c.values())
                if ':' in msg:
                    msg = msg.split(':', 1)[1].strip()
                extracted.append(msg)
        else:
            # Remove username if present
            val = str(c)
            if ':' in val:
                val = val.split(':', 1)[1].strip()
            extracted.append(val)
    return extracted

def replace_subreddit_mentions(text, en_name, pl_name):
    """Replace all r/EnglishSubreddit with r/PolishSubreddit in the given text."""
    if not text:
        return text
    return text.replace(f"r/{en_name}", f"r/{pl_name}")



if __name__ == "__main__":
    x = 30  # <-- Set how many successful videos you want to generate
    generated = 0
    attempts = 0
    while generated < x:
        attempts += 1
        print(f"\n--- Attempt {attempts} | Successful videos: {generated}/{x} ---")
        try:
            post_title, op_message, top_comments, subreddit_name = fetch_reddit_post()
            if post_title or top_comments:
                if post_title and len(post_title) > 200:
                    print("Skipped thread due to long title.")
                    save_used_thread(post_title)
                    continue

                print("Translating content to Polish via OpenAI...")
                translated_title, translated_op_message, translated_comments, tiktok_filename, tiktok_tags = translate_content_to_polish(
                    post_title, op_message, top_comments
                )

                pl_subreddit = SUBREDDIT_PL_TRANSLATIONS.get(subreddit_name, subreddit_name)
                translated_title = replace_subreddit_mentions(translated_title, subreddit_name, pl_subreddit)
                if translated_op_message:
                    translated_op_message = replace_subreddit_mentions(translated_op_message, subreddit_name, pl_subreddit)
                translated_comments = [
                    replace_subreddit_mentions(c, subreddit_name, pl_subreddit) for c in translated_comments
                ]

                display_title = f"[r/{pl_subreddit}] {translated_title}" if translated_title else ""
                if translated_op_message and translated_op_message.strip():
                    op_comment = f"OP: {translated_op_message.strip()}"
                    comments_for_video = [op_comment] + translated_comments
                else:
                    comments_for_video = translated_comments

                # --- Save video with TikTok filename and tags ---
                output_dir = r"D:\autoedit\60\RedditPL"
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                safe_filename = "".join(c for c in tiktok_filename if c.isalnum() or c in ('_', '-')).rstrip()
                base_filename = safe_filename[:60] or "reddit_video"
                video_path = os.path.join(output_dir, f"{base_filename}.mp4")
                tags_path = os.path.join(output_dir, f"{base_filename}_tags.txt")

                create_video(display_title, comments_for_video)

                with open(tags_path, "w", encoding="utf-8") as f:
                    f.write(f"Title: {translated_title}\n")
                    f.write("Tags: " + ", ".join(f"#{tag}" for tag in tiktok_tags) + "\n")

                if post_title:
                    save_used_thread(post_title)
                generated += 1
            else:
                print("Failed to fetch any Reddit content.")
        except Exception as e:
            print(f"Error during video generation attempt {attempts}: {e}")
            print("Don't worry, skipping to the next one! 🚀")
            import traceback
            traceback.print_exc()
            continue
