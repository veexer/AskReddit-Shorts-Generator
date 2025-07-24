# Reddit-to-TikTok Video Generator 🚀

Welcome to the **Reddit-to-TikTok Video Generator** – your all-in-one, modular, and hackable Python tool for transforming top Reddit content into engaging, vertical TikTok (or YouTube Shorts) videos, complete with TTS narration, subtitles, and dynamic backgrounds!

## ✨ Features

- **Fetches Top Reddit Posts:** Uses the Reddit API to grab trending threads and their best comments.
- **AI-Powered Rewriting:** Leverages OpenAI to rewrite posts and comments for maximum TikTok engagement.
- **Natural TTS Narration:** Generates high-quality voiceovers using Google Cloud TTS.
- **Word-Level Subtitles:** Syncs subtitles to audio with word-level precision using Faster Whisper.
- **Dynamic Video Creation:** Assembles everything with MoviePy, overlays subtitles, and adds background visuals and music.
- **Highly Customizable:** Swap out backgrounds, TTS engines, or even the source subreddit with ease.
- **Safe & Automated:** Keeps track of used threads, trims silences, and handles temp files like a champ.

## 🛠️ How It Works

1. **Fetches** a top Reddit post and its best comments.
2. **Rewrites** the content for TikTok using OpenAI (GPT-4).
3. **Generates** TTS audio for the title and comments.
4. **Creates** word-synced subtitles.
5. **Composes** a vertical video with dynamic backgrounds, music, and overlays.
6. **Exports** a ready-to-upload TikTok/Shorts video and a tags file for easy posting.

## 🚀 Quick Start

1. **Clone the repo** and install dependencies:
    ```sh
    git clone https://github.com/veexer/AskReddit-Shorts-Generator
    cd AskReddit-Shorts-Generator
    pip install -r requirements.txt
    ```

2. **Set up your API keys** in a `.env` file:
    ```
    OPENAI_API_KEY=your-openai-key
    GOOGLE_APPLICATION_CREDENTIALS=path-to-your-google-credentials.json
    ```

3. **Place your background videos and music** in the project directory (see variables at the top of `Redditcontentlocal.py`).

4. **Run the script:**
    ```sh
    python Redditcontentlocal.py
    ```

5. **Check your output videos** in the configured output directory!

## 🧩 Customization

- **Change Subreddits:** Edit the `SUBREDDIT_CHOICES` list in [`Redditcontentlocal.py`](Redditcontentlocal.py).
- **Swap TTS Engine:** Replace the `text_to_speech_gtts` function with your favorite TTS provider.
- **Backgrounds & Music:** Add your own video/music files and update the paths at the top of the script.
- **Tune Video Length:** Adjust `MAX_VIDEO_DURATION` and `MIN_VIDEO_DURATION` as needed.

## 🤖 Tech Stack

- [Python](https://www.python.org/)
- [PRAW](https://praw.readthedocs.io/) (Reddit API)
- [OpenAI GPT-4](https://platform.openai.com/)
- [Google Cloud TTS](https://cloud.google.com/text-to-speech)
- [MoviePy](https://zulko.github.io/moviepy/)
- [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
- [Pydub](https://github.com/jiaaro/pydub)
- [dotenv](https://pypi.org/project/python-dotenv/)

## 🏆 Why Use This Project?

- **Automate your content pipeline** and never run out of TikTok ideas.
- **Show off your Python chops** with a modular, well-documented codebase.
- **Easily extend or hack** for your own wild content automation dreams.

## 🙌 About the Author

Crafted with care by a developer who loves automation, creative coding, and making the internet a more entertaining place. If you like this project, feel free to [connect on GitHub](https://github.com/veexer) or drop a star!

---

*Go make some viral videos! 😎*
