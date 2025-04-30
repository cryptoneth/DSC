import json
import time
import os
import random
import requests
import re
import threading
from datetime import datetime
from cryptography.fernet import Fernet
import base64

# Global variables
last_message_id = None
bot_user_id = None
last_ai_response = None
last_bot_message_id = None
bot_running = False
discord_token = None
google_api_key = None

session = requests.Session()

# Files for storing settings
SETTINGS_FILE = "settings.json"
CIPHER_KEY = Fernet.generate_key()
cipher = Fernet(CIPHER_KEY)

def log_message(message):
    """Log message to console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}")

def load_settings():
    """Load settings from settings.json, return None if incomplete"""
    global discord_token, google_api_key
    try:
        if not os.path.exists(SETTINGS_FILE):
            log_message("⚠️ Settings file not found.")
            return None
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        # Decrypt tokens
        if settings.get("discord_token"):
            settings["discord_token"] = cipher.decrypt(base64.b64decode(settings["discord_token"])).decode()
        if settings.get("google_api_key"):
            settings["google_api_key"] = cipher.decrypt(base64.b64decode(settings["google_api_key"])).decode()
        discord_token = settings.get("discord_token")
        google_api_key = settings.get("google_api_key")
        # Validate required fields
        required_fields = [
            "tone", "character_name", "personality", "project_details", "project_keywords",
            "discord_token", "google_api_key", "channel_id", "use_google_ai", "reply_mode",
            "read_delay", "reply_delay"
        ]
        if all(field in settings for field in required_fields):
            if all(key in settings["project_details"] for key in ["name", "description", "key_features"]):
                return settings
        log_message("⚠️ Incomplete settings in file, treating as missing.")
        return None
    except Exception as e:
        log_message(f"⚠️ Error loading settings: {e}")
        return None

def save_settings(settings):
    """Save settings to settings.json"""
    global discord_token, google_api_key
    try:
        save_data = settings.copy()
        # Encrypt tokens
        if save_data.get("discord_token"):
            save_data["discord_token"] = base64.b64encode(cipher.encrypt(save_data["discord_token"].encode())).decode()
        if save_data.get("google_api_key"):
            save_data["google_api_key"] = base64.b64encode(cipher.encrypt(save_data["google_api_key"].encode())).decode()
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        discord_token = settings.get("discord_token")
        google_api_key = settings.get("google_api_key")
        log_message("✅ Settings saved successfully.")
    except Exception as e:
        log_message(f"⚠️ Error saving settings: {e}")

def configure_settings():
    """Prompt for settings or load saved ones"""
    saved_settings = load_settings()
    if saved_settings:
        print("⚙️ Found saved settings in settings.json.")
        choice = input("Do you want to use saved settings or enter new ones? (saved/new): ").strip().lower()
        if choice == "saved":
            log_message("✅ Using saved settings.")
            return saved_settings
    print("⚙️ Configuring new settings...")
    settings = {
        "tone": input("Enter tone (e.g., Balanced Discord slang with smooth conversational flow, dynamically adapt tone to topic and message, professional and clear when needed, always human-like, direct, relatable): ").strip(),
        "character_name": input("Enter character name (e.g., Crypton): ").strip(),
        "personality": input("Enter personality (e.g., Crypto researcher with 7 years experience, part-time trader, programmer, runs Telegram/Twitter with 15k followers, joins promising Web3 projects, loves crypto): ").strip(),
        "project_details": {
            "name": input("Enter project name (e.g., Altius Labs): ").strip(),
            "description": input("Enter project description: ").strip(),
            "key_features": input("Enter key features (comma-separated): ").strip()
        },
        "project_keywords": input("Enter project keywords (comma-separated): ").strip(),
        "discord_token": input("Enter Discord Token: ").strip(),
        "google_api_key": input("Enter Google API Key: ").strip(),
        "channel_id": input("Enter Discord Channel ID: ").strip(),
        "use_google_ai": input("Use Google Gemini AI? (yes/no): ").strip().lower() == "yes",
        "reply_mode": input("Enable Reply Mode? (yes/no): ").strip().lower() == "yes",
        "read_delay": int(input("Enter Read Delay (seconds): ").strip()),
        "reply_delay": int(input("Enter Reply Delay (seconds): ").strip())
    }
    save_settings(settings)
    return settings

def get_rate_limit_info(response):
    """Check rate limit headers"""
    headers = response.headers
    remaining = int(headers.get("X-RateLimit-Remaining", 1))
    reset_after = float(headers.get("X-RateLimit-Reset-After", 0))
    return remaining, reset_after

def send_typing(channel_id):
    """Send typing indicator"""
    headers = {
        'Authorization': f'{discord_token}',
        'User-Agent': 'Mozilla/5.0'
    }
    try:
        response = session.post(f"https://discord.com/api/v9/channels/{channel_id}/typing", headers=headers)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 3)
            log_message(f"⚠️ Typing indicator rate limit hit! Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            return
        log_message("⌨️ Typing indicator sent...")
    except requests.exceptions.RequestException as e:
        log_message(f"⚠️ Typing indicator error: {e}")

def read_personality():
    """Read personality and character name from settings"""
    settings = load_settings()
    return settings["personality"], settings["character_name"]

def read_project_details():
    """Read project details and keywords from settings"""
    settings = load_settings()
    project_details = settings["project_details"]
    keywords = settings["project_keywords"].split(", ")
    return project_details, keywords

def update_project_file():
    """Automatically update project keywords every 24 hours"""
    while True:
        try:
            project_details, _ = read_project_details()
            if not project_details.get('name') or not project_details.get('description'):
                log_message("⚠️ Project name or description missing, skipping keyword update.")
                time.sleep(24 * 60 * 60)
                continue
            prompt_text = f"Current project: {project_details['name']} - {project_details['description']}\nSuggest updated keywords for this project. Keep it short, casual, in English."
            data = {
                'contents': [{
                    'parts': [{'text': prompt_text}]
                }]
            }
            log_message(f"API request payload: {json.dumps(data, indent=2)}")
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={google_api_key}'
            headers = {'Content-Type': 'application/json'}
            response = session.post(url, headers=headers, json=data)
            if response.status_code == 429:  # Rate limit error
                retry_after = response.json().get("retry_after", 60)
                log_message(f"⚠️ Rate limit hit! Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            new_keywords = response.json()['candidates'][0]['content']['parts'][0]['text']
            settings = load_settings()
            settings["project_keywords"] = new_keywords
            save_settings(settings)
            log_message("✅ Project keywords updated successfully.")
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Failed to update project keywords: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
            log_message("⚠️ Skipping keyword update, will retry in 24 hours.")
        time.sleep(24 * 60 * 60)

def is_personal_question(prompt):
    """Detect personal questions"""
    personal_keywords = [
        "who are you", "who's this", "what are you", "tell me about yourself",
        "yourself", "identity", "who is", "about you", "who're you", "who you",
        "what's your deal", "who's that"
    ]
    return any(keyword.lower() in prompt.lower() for keyword in personal_keywords)

def is_project_related(prompt, keywords):
    """Detect project-related questions"""
    return any(keyword.lower() in prompt.lower() for keyword in keywords)

def is_simple_question(prompt):
    """Detect simple questions"""
    if not prompt:
        return False
    prompt = prompt.strip()
    simple_keywords = [
        "hi", "hey", "yo", "what's up", "how's it going", "cool", "okay",
        "sup", "what's good", "hello", "hiya"
    ]
    return len(prompt.split()) <= 3 or any(keyword.lower() in prompt.lower() for keyword in simple_keywords)

def is_comprehensible(message):
    """Check if message is comprehensible"""
    if not message:
        return False
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        "]+", flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub(r'', message).strip()
    return len(cleaned) > 5

def is_technical_question(prompt):
    """Detect technical questions requiring professional tone"""
    technical_keywords = [
        "how does", "explain", "what is", "mechanism", "process", "function",
        "technical", "details", "work", "system", "technology"
    ]
    return any(keyword.lower() in prompt.lower() for keyword in technical_keywords)

def generate_reply(prompt, use_google_ai=True):
    global last_ai_response
    settings = load_settings()
    tone = settings["tone"].lower()
    personality, character_name = read_personality()
    project_details, project_keywords = read_project_details()

    # Base tone prompt from user input
    base_prompt = tone if tone else "Chat like a chill Discord pal, laid-back, friendly, slang-heavy, vibin’ with the crew."

    # Expanded vocabulary for natural, varied responses
    vocab_variations = [
        "yo", "hey", "dude", "bro", "man", "what's good", "lit", "fire", "dope",
        "vibes", "chill", "hype", "wild", "crazy", "poppin'", "on point", "solid",
        "bet", "for real", "no cap", "straight up", "let's go", "big time",
        "ayy", "fam", "tight", "clutch", "banger", "vibe check", "slaps"
    ]
    random_vocab = random.choice(vocab_variations)

    project_info = f"Project: {project_details['name']} - {project_details['description']} (Features: {project_details['key_features']})"

    if use_google_ai:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={google_api_key}'
        headers = {'Content-Type': 'application/json'}
        
        # Dynamic tone adjustments based on message type and content
        if is_personal_question(prompt):
            tone_adjustment = "Use moderate slang, emphasize character personality, keep it friendly and relatable."
            full_prompt = (
                f"{base_prompt}\nYou're {character_name}, {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nQuestion: {prompt}\n"
                f"Answer like a real person, in English, max 20 words, Discord style, "
                f"use varied vocab like '{random_vocab}'. Don't mention project unless asked."
            )
        elif is_project_related(prompt, project_keywords):
            if is_technical_question(prompt):
                tone_adjustment = "Lean professional, clear, and direct with minimal slang, but keep it approachable."
            else:
                tone_adjustment = "Mix heavy slang with clear project details, keep it hype and engaging."
            full_prompt = (
                f"{base_prompt}\nYou're {character_name}, {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\n{project_info}\nQuestion: {prompt}\n"
                f"Answer with project context, in English, max 20 words, Discord style, "
                f"use varied vocab like '{random_vocab}'. Focus on project."
            )
        elif is_simple_question(prompt):
            tone_adjustment = "Max slang, super short and chill, like a quick Discord ping."
            full_prompt = (
                f"{base_prompt}\nYou're {character_name}, {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nQuestion: {prompt}\n"
                f"Answer short, friendly, like a Discord pal, in English, max 10 words, "
                f"use varied vocab like '{random_vocab}'."
            )
        else:
            tone_adjustment = "Balance slang and clarity, lean into character vibe, mention project only if it fits."
            full_prompt = (
                f"{base_prompt}\nYou're {character_name}, {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nOptional context: {project_info}\nQuestion: {prompt}\n"
                f"Answer in English, max 20 words, Discord style, use varied vocab like '{random_vocab}'. "
                f"Mention project only if relevant."
            )

        data = {'contents': [{'parts': [{'text': full_prompt}]}]}
        log_message(f"Sending prompt to Gemini: {full_prompt}")

        for attempt in range(3):
            try:
                response = session.post(url, headers=headers, json=data)
                if response.status_code == 429:  # Rate limit error
                    retry_after = response.json().get("retry_after", 60)
                    log_message(f"⚠️ Rate limit hit! Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                ai_response = response.json()
                response_text = ai_response['candidates'][0]['content']['parts'][0]['text']
                
                # Refined blocked words to avoid AI giveaways only
                blocked_words = [
                    "I am a bot", "I’m a bot", "as an AI", "as a bot", "language model",
                    "artificial intelligence", "AI model", "chatbot", "digital assistant",
                    "I’m programmed", "programmed to", "my creators", "designed to",
                    "I am an AI", "I’m an AI", "machine learning model",
                    "algorithm", "neural network", "processing", "compute", "data analysis",
                    "query processing", "natural language processing", "system response",
                    "I don’t have personal experiences", "I don’t have feelings",
                    "I’m not human", "as a machine", "I’m a program", "I’m software",
                    "I’m a digital entity", "I’m a virtual assistant", "I’m built to",
                    "I’m coded to", "my programming", "my algorithms"
                ]
                for word in blocked_words:
                    response_text = response_text.replace(word, "").replace(word.title(), "").replace(word.upper(), "")
                
                response_text = response_text.strip().split("\n")[0]
                words = response_text.split()
                if len(words) > 20:
                    response_text = " ".join(words[:20])
                response_text = re.sub(r'[.,!?;]', '', response_text)
                response_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', response_text)
                
                if any(word.lower() in response_text.lower() for word in blocked_words):
                    log_message("Response contains forbidden AI-related words, retrying...")
                    continue
                if response_text == last_ai_response:
                    log_message("AI gave same response, retrying...")
                    continue
                last_ai_response = response_text
                return response_text
            except requests.exceptions.RequestException as e:
                log_message(f"⚠️ AI request failed: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    log_message(f"API response: {e.response.text}")
                return f"Whoops {random_vocab} something broke try again later"
    return f"Can't chat now {random_vocab} catch ya later"

def send_message(channel_id, message_text, reply_to=None, reply_mode=True):
    """Send message to Discord"""
    global last_bot_message_id
    headers = {
        'Authorization': f'{discord_token}',
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0'
    }
    payload = {'content': message_text}
    if reply_mode and reply_to:
        payload['message_reference'] = {'message_id': reply_to}

    while True:
        try:
            send_typing(channel_id)
            time.sleep(random.uniform(5, 10))
            response = session.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", json=payload, headers=headers)
            remaining, reset_after = get_rate_limit_info(response)
            if response.status_code == 429:
                retry_after = response.json().get("retry_after", reset_after)
                log_message(f"⚠️ Rate limit hit! Waiting {retry_after} seconds...")
                time.sleep(retry_after + 1)
                continue
            response.raise_for_status()
            last_bot_message_id = response.json().get('id')
            log_message(f"✅ Sent message: {message_text}")
            if remaining == 0:
                log_message(f"⚠️ Rate limit almost hit! Waiting {reset_after} seconds...")
                time.sleep(reset_after)
            break
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Request error: {e}")
            time.sleep(5)

def auto_reply(channel_id, read_delay, reply_delay, use_google_ai, reply_mode):
    global last_message_id, bot_user_id, last_bot_message_id, bot_running
    headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
    try:
        bot_info_response = session.get('https://discord.com/api/v9/users/@me', headers=headers)
        bot_info_response.raise_for_status()
        bot_user_id = bot_info_response.json().get('id')
    except requests.exceptions.RequestException as e:
        log_message(f"Failed to retrieve bot information: {e}")
        return
    threading.Thread(target=update_project_file, daemon=True).start()

    while bot_running:
        try:
            response = session.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=10', headers=headers)
            response.raise_for_status()
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    latest_message = messages[0]
                    message_id = latest_message.get('id')
                    author_id = latest_message.get('author', {}).get('id')
                    message_type = latest_message.get('type', '')
                    referenced_message = latest_message.get('referenced_message', {})
                    if (last_message_id is None or int(message_id) > int(last_message_id)) and author_id != bot_user_id and message_type != 8:
                        if referenced_message and referenced_message.get('author', {}).get('id') == bot_user_id:
                            user_message = latest_message.get('content', '')
                            log_message(f"Received reply: {user_message}")
                            response_text = generate_reply(user_message, use_google_ai)
                            wait_time = reply_delay + random.uniform(5, 10)
                            log_message(f"Waiting {wait_time} seconds before replying")
                            time.sleep(wait_time)
                            send_message(channel_id, response_text, reply_to=message_id if reply_mode else None, reply_mode=reply_mode)
                            last_message_id = message_id
            read_wait = read_delay + random.uniform(10, 20)
            log_message(f"Waiting {read_wait} seconds before checking for new messages")
            time.sleep(read_wait)
        except requests.exceptions.RequestException as e:
            log_message(f"Request error: {e}")
            time.sleep(read_delay)
    log_message("Chatbot stopped")

def main():
    """Main function"""
    global bot_running, discord_token, google_api_key

    # Load or configure settings
    settings = configure_settings()
    discord_token = settings["discord_token"]
    google_api_key = settings["google_api_key"]
    channel_id = settings["channel_id"]
    use_google_ai = settings["use_google_ai"]
    reply_mode = settings["reply_mode"]
    read_delay = settings["read_delay"]
    reply_delay = settings["reply_delay"]

    if not discord_token or not google_api_key or not channel_id:
        log_message("⚠️ Discord Token, Google API Key, and Channel ID are required!")
        return

    bot_running = True
    log_message("✅ Starting chatbot...")
    try:
        auto_reply(channel_id, read_delay, reply_delay, use_google_ai, reply_mode)
    except KeyboardInterrupt:
        bot_running = False
        log_message("✅ Chatbot stopped by user.")

if __name__ == "__main__":
    main()
