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
from queue import Queue

# Global variables
last_message_id = None
bot_user_id = None
last_ai_response = None
last_bot_message_id = None
bot_running = False
discord_token = None
google_api_key = None
message_queue = Queue()

session = requests.Session()

# Files for storing settings
SETTINGS_FILE = "settings.json"
CIPHER_KEY = Fernet.generate_key()
cipher = Fernet(CIPHER_KEY)

def log_message(message):
    """Log message to console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}")

def sanitize_input(text):
    """Sanitize input to remove invalid UTF-8 characters"""
    try:
        return text.encode('utf-8', 'ignore').decode('utf-8')
    except Exception as e:
        log_message(f"⚠️ Error sanitizing input: {e}")
        return text

def load_settings():
    """Load settings from settings.json, return None if incomplete or error"""
    global discord_token, google_api_key
    try:
        if not os.path.exists(SETTINGS_FILE):
            log_message("⚠️ Settings file not found.")
            return None
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        # Decrypt tokens
        try:
            if settings.get("discord_token"):
                settings["discord_token"] = cipher.decrypt(base64.b64decode(settings["discord_token"])).decode()
            if settings.get("google_api_key"):
                settings["google_api_key"] = cipher.decrypt(base64.b64decode(settings["google_api_key"])).decode()
        except Exception as e:
            log_message(f"⚠️ Decryption error for tokens: {e}")
            try:
                os.rename(SETTINGS_FILE, f"{SETTINGS_FILE}.bak")
                log_message(f"⚠️ Renamed corrupted settings file to {SETTINGS_FILE}.bak")
            except Exception as rename_e:
                log_message(f"⚠️ Error renaming settings file: {rename_e}")
            return None
        discord_token = settings.get("discord_token")
        google_api_key = settings.get("google_api_key")
        # Validate required fields
        required_fields = [
            "tone", "character_name", "personality", "project_details", "project_keywords",
            "discord_token", "google_api_key", "channel_id", "use_google_ai", "reply_mode",
            "proactive_delay", "random_read_reply_delay", "direct_reply_check_delay"
        ]
        if all(field in settings for field in required_fields):
            if all(key in settings["project_details"] for key in ["name", "description", "key_features"]):
                log_message("✅ Settings loaded successfully.")
                return settings
        log_message("⚠️ Incomplete settings in file, missing required fields.")
        return None
    except json.JSONDecodeError as e:
        log_message(f"⚠️ JSON decode error in settings file: {e}")
        try:
            os.rename(SETTINGS_FILE, f"{SETTINGS_FILE}.bak")
            log_message(f"⚠️ Renamed corrupted settings file to {SETTINGS_FILE}.bak")
        except Exception as rename_e:
            log_message(f"⚠️ Error renaming settings file: {rename_e}")
        return None
    except Exception as e:
        log_message(f"⚠️ Error loading settings: {e}")
        return None

def save_settings(settings):
    """Save settings to settings.json with validation and error handling"""
    global discord_token, google_api_key
    try:
        # Validate required fields before saving
        required_fields = [
            "tone", "character_name", "personality", "project_details", "project_keywords",
            "discord_token", "google_api_key", "channel_id", "use_google_ai", "reply_mode",
            "proactive_delay", "random_read_reply_delay", "direct_reply_check_delay"
        ]
        if not all(field in settings for field in required_fields):
            log_message("⚠️ Cannot save settings: Missing required fields.")
            return False
        if not all(key in settings["project_details"] for key in ["name", "description", "key_features"]):
            log_message("⚠️ Cannot save settings: Missing project details fields.")
            return False
        save_data = settings.copy()
        # Sanitize string inputs to remove invalid UTF-8 characters
        for key in ["tone", "character_name", "personality", "project_keywords", "discord_token", "google_api_key", "channel_id"]:
            if key in save_data and isinstance(save_data[key], str):
                save_data[key] = sanitize_input(save_data[key])
        for key in ["name", "description", "key_features"]:
            if key in save_data["project_details"] and isinstance(save_data["project_details"][key], str):
                save_data["project_details"][key] = sanitize_input(save_data["project_details"][key])
        # Encrypt tokens
        try:
            if save_data.get("discord_token"):
                save_data["discord_token"] = base64.b64encode(cipher.encrypt(save_data["discord_token"].encode())).decode()
            if save_data.get("google_api_key"):
                save_data["google_api_key"] = base64.b64encode(cipher.encrypt(save_data["google_api_key"].encode())).decode()
        except Exception as e:
            log_message(f"⚠️ Encryption error for tokens: {e}")
            return False
        # Try saving with retries
        for attempt in range(3):
            try:
                with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=4)
                discord_token = settings.get("discord_token")
                google_api_key = settings.get("google_api_key")
                log_message("✅ Settings saved successfully.")
                return True
            except PermissionError as e:
                log_message(f"⚠️ Permission error saving settings (attempt {attempt+1}/3): {e}")
                time.sleep(1)
            except Exception as e:
                log_message(f"⚠️ Error saving settings (attempt {attempt+1}/3): {e}")
                time.sleep(1)
        log_message("⚠️ Failed to save settings after retries.")
        return False
    except Exception as e:
        log_message(f"⚠️ Unexpected error saving settings: {e}")
        return False

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
            "name": input("Enter project name (e.g., Altius Labs): ").strip() or "Altius Labs",
            "description": input("Enter project description (press Enter for default): ").strip() or "Altius Labs offers a VM-agnostic modular execution layer for Web3, boosting blockchain speed, slashing costs, and enabling seamless cross-chain interactions. It tackles congestion and scalability by separating execution from the blockchain’s core, supporting any chain like EVM or Solana. With gigagas-per-second performance, it ensures smooth, decentralized DeFi, NFT, and dApp experiences. Built by crypto and HFT experts, Altius empowers a scalable, multi-chain future with secure, user-friendly tech.",
            "key_features": input("Enter key features (comma-separated, press Enter for default): ").strip() or "modular execution layer, high-speed transactions, low-cost transactions, cross-chain interoperability, VM-agnostic compatibility, parallel processing, scalable storage, decentralized design"
        },
        "project_keywords": input("Enter project keywords (comma-separated, press Enter for default): ").strip() or "Web3, blockchain, DeFi, modular execution, cross-chain, scalability, low-cost transactions, VM-agnostic, parallel processing, decentralized, yield farming, dApps",
        "discord_token": input("Enter Discord Token: ").strip(),
        "google_api_key": input("Enter Google API Key: ").strip(),
        "channel_id": input("Enter Discord Channel ID: ").strip(),
        "use_google_ai": input("Use Google Gemini AI? (yes/no): ").strip().lower() == "yes",
        "reply_mode": input("Enable Reply Mode? (yes/no): ").strip().lower() == "yes",
        "proactive_delay": int(input("How many seconds between each proactive message? ").strip()),
        "random_read_reply_delay": int(input("How many seconds to read and reply to a random recent message? ").strip()),
        "direct_reply_check_delay": int(input("How many seconds to wait before replying to someone who replied to me? ").strip())
    }
    if save_settings(settings):
        return settings
    else:
        log_message("⚠️ Failed to save settings, using temporary settings.")
        return settings

def get_rate_limit_info(response):
    """Check rate limit headers"""
    headers = response.headers
    remaining = int(headers.get("X-RateLimit-Remaining", 1))
    reset_after = float(headers.get("X-RateLimit-Reset-After", 0))
    return remaining, reset_after

def send_typing(channel_id):
    """Send typing indicator (reduced frequency to avoid rate limits)"""
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
            return False
        log_message("⌨️ Typing indicator sent...")
        return True
    except requests.exceptions.RequestException as e:
        log_message(f"⚠️ Typing indicator error: {e}")
        return False

def send_message(channel_id, message_text, reply_to=None, reply_mode=True):
    """Send message to Discord with rate limit handling"""
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
            if send_typing(channel_id):
                time.sleep(random.uniform(5, 10))
            response = session.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", json=payload, headers=headers)
            remaining, reset_after = get_rate_limit_info(response)
            if response.status_code == 429:
                retry_after = response.json().get("retry_after", reset_after)
                log_message(f"⚠️ Rate limit hit! Queuing message: {message_text}")
                message_queue.put((channel_id, message_text, reply_to, reply_mode))
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
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
            time.sleep(5)

def process_message_queue():
    """Process queued messages to handle rate limits"""
    while bot_running:
        if not message_queue.empty():
            channel_id, message_text, reply_to, reply_mode = message_queue.get()
            send_message(channel_id, message_text, reply_to, reply_mode)
        time.sleep(1)

def read_personality():
    """Read personality and character name from settings"""
    settings = load_settings()
    if settings is None:
        log_message("⚠️ No valid settings, using default personality.")
        return "Crypto bro", "Crypton"
    return settings["personality"], settings["character_name"]

def read_project_details():
    """Read project details and keywords from settings"""
    settings = load_settings()
    if settings is None:
        log_message("⚠️ No valid settings, using default project details.")
        return {"name": "Unknown", "description": "", "key_features": ""}, ["Web3"]
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
            if response.status_code == 429:
                retry_after = response.json().get("retry_after", 60)
                log_message(f"⚠️ Rate limit hit! Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            new_keywords = response.json()['candidates'][0]['content']['parts'][0]['text']
            settings = load_settings()
            if settings:
                settings["project_keywords"] = new_keywords
                save_settings(settings)
                log_message("✅ Project keywords updated successfully.")
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Failed to update project keywords: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
            log_message("⚠️ Skipping keyword update, will retry in 24 hours.")
        time.sleep(24 * 60 * 60)

def post_proactive_message(channel_id, delay):
    """Post proactive messages at specified interval based on recent messages"""
    while bot_running:
        start_time = time.time()
        try:
            # Fetch recent messages for context (up to 20)
            headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
            response = session.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=20', headers=headers)
            response.raise_for_status()
            messages = response.json()
            context = " ".join([msg.get('content', '') for msg in messages if msg.get('content')])
            project_details, project_keywords = read_project_details()
            personality, _ = read_personality()
            settings = load_settings()
            tone = settings["tone"].lower() if settings else "Balanced Discord slang with smooth conversational flow, dynamically adapt tone to topic and message, professional and clear when needed, always human-like, direct, relatable"
            prompt = (
                f"You're a {personality}. Recent chat: {context[:500]}.\n"
                f"Project: {project_details['name']} - {project_details['description']}.\n"
                f"Tone: {tone}\n"
                f"Generate a short (5-10 words), casual message to join the conversation, "
                f"using Discord slang, relevant to the chat or project, in English. "
                f"Do not use your name or emojis."
            )
            data = {
                'contents': [{
                    'parts': [{'text': prompt}]
                }]
            }
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={google_api_key}'
            response = session.post(url, headers={'Content-Type': 'application/json'}, json=data)
            response.raise_for_status()
            message_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            send_message(channel_id, message_text)
            log_message(f"✅ Posted proactive message: {message_text}")
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Failed to post proactive message: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
        elapsed_time = time.time() - start_time
        remaining_delay = max(0, delay - elapsed_time)
        log_message(f"Waiting {remaining_delay} seconds for next proactive message...")
        time.sleep(remaining_delay)

def reply_to_random_message(channel_id, delay, reply_mode):
    """Read and reply to a random recent message at specified interval"""
    global last_message_id
    while bot_running:
        start_time = time.time()
        try:
            # Fetch recent messages (up to 20)
            headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
            response = session.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=20', headers=headers)
            response.raise_for_status()
            messages = response.json()
            if messages:
                # Select a random message not from the bot
                non_bot_messages = [msg for msg in messages if msg.get('author', {}).get('id') != bot_user_id]
                if non_bot_messages:
                    random_message = random.choice(non_bot_messages)
                    message_id = random_message.get('id')
                    content = random_message.get('content', '')
                    log_message(f"Selected random message ID: {message_id}, Content: {content}")
                    response_text = generate_reply(content, use_google_ai=True)
                    send_message(channel_id, response_text, reply_to=message_id if reply_mode else None, reply_mode=reply_mode)
                    last_message_id = message_id
            else:
                log_message("No messages found for random reply.")
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Failed to reply to random message: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
        elapsed_time = time.time() - start_time
        remaining_delay = max(0, delay - elapsed_time)
        log_message(f"Waiting {remaining_delay} seconds for next random reply...")
        time.sleep(remaining_delay)

def reply_to_direct_replies(channel_id, delay, reply_mode):
    """Check for direct replies to the bot and respond after specified delay"""
    global last_message_id
    while bot_running:
        start_time = time.time()
        try:
            # Fetch recent messages (up to 20)
            headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
            response = session.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=20', headers=headers)
            response.raise_for_status()
            messages = response.json()
            for message in messages:
                message_id = message.get('id')
                author_id = message.get('author', {}).get('id')
                message_type = message.get('type', '')
                content = message.get('content', '')
                referenced_message = message.get('referenced_message', {})
                # Check if message is new, not from bot, and a direct reply to the bot
                if (last_message_id is None or int(message_id) > int(last_message_id)) and author_id != bot_user_id and message_type != 8:
                    if referenced_message and referenced_message.get('author', {}).get('id') == bot_user_id:
                        log_message(f"Received direct reply: {content}")
                        time.sleep(delay)  # Wait before replying
                        response_text = generate_reply(content, use_google_ai=True)
                        if is_bot_accusation(content):
                            response_text = random.choice(bot_denial_responses)
                        send_message(channel_id, response_text, reply_to=message_id if reply_mode else None, reply_mode=reply_mode)
                        last_message_id = message_id
            last_message_id = messages[0].get('id') if messages else last_message_id
        except requests.exceptions.RequestException as e:
            log_message(f"⚠️ Failed to check direct replies: {e}")
            if hasattr(e, 'response') and e.response is not None:
                log_message(f"API response: {e.response.text}")
        elapsed_time = time.time() - start_time
        remaining_delay = max(0, delay - elapsed_time)
        log_message(f"Waiting {remaining_delay} seconds for next direct reply check...")
        time.sleep(remaining_delay)

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

def is_technical_question(prompt):
    """Detect technical questions requiring professional tone"""
    technical_keywords = [
        "how does", "explain", "what is", "mechanism", "process", "function",
        "technical", "details", "work", "system", "technology"
    ]
    return any(keyword.lower() in prompt.lower() for keyword in technical_keywords)

def is_bot_accusation(prompt):
    """Detect if message accuses the bot of being a bot"""
    bot_keywords = [
        "bot", "robot", "AI", "artificial intelligence", "chatbot", "automated",
        "are you a bot", "you're a bot", "is this a bot", "bot or human"
    ]
    return any(keyword.lower() in prompt.lower() for keyword in bot_keywords)

def generate_reply(prompt, use_google_ai=True):
    global last_ai_response
    settings = load_settings()
    tone = settings["tone"].lower() if settings else "Balanced Discord slang with smooth conversational flow, dynamically adapt tone to topic and message, professional and clear when needed, always human-like, direct, relatable"
    personality, character_name = read_personality()
    project_details, project_keywords = read_project_details()

    # Base tone prompt from user input
    base_prompt = tone

    # Expanded vocabulary for natural, varied responses
    vocab_variations = [
        "yo", "hey", "dude", "bro", "man", "what's good", "lit", "fire", "dope",
        "vibes", "chill", "hype", "wild", "crazy", "poppin'", "on point", "solid",
        "bet", "for real", "no cap", "straight up", "let's go", "big time",
        "ayy", "fam", "tight", "clutch", "banger", "vibe check", "slaps"
    ]
    random_vocab = random.choice(vocab_variations)

    # 100 varied denial responses for bot accusations
    bot_denial_responses = [
        f"Nah, I’m {character_name}, you trippin’ bruh!",
        f"Bruh, {character_name}’s real, chill out!",
        f"Yo, no bot here, just {character_name}!",
        f"Ayy, {character_name} ain’t no bot, fam!",
        f"Pfft, you think {character_name}’s a bot? Wild!",
        f"Man, I’m {character_name}, you buggin’!",
        f"Chill, {character_name}’s legit, no cap!",
        f"No way, {character_name}’s real, you cappin’!",
        f"What?! I’m {character_name}, not a bot!",
        f"Fam, {character_name} ain’t robotic, relax!",
        f"Get real, I’m {character_name}, you tweakin’!",
        f"Ha, {character_name}’s no bot, you clownin’!",
        f"Nope, just {character_name}, you wildin’!",
        f"Bruh, I’m {character_name}, no bot vibes!",
        f"Yo, {character_name}’s the man, you buggin’!",
        f"Ayy, no bot, I’m {character_name}, chill!",
        f"Pfft, {character_name}’s real, you trippin’!",
        f"Man, {character_name} ain’t no bot, bruh!",
        f"Chill out, I’m {character_name}, you cappin’!",
        f"No bot, fam, just {character_name}, relax!",
        f"What, you think {character_name}’s a bot? Nah!",
        f"Nah, {character_name}’s legit, you slippin’!",
        f"Bruh, no bot here, I’m {character_name}!",
        f"Yo, I’m {character_name}, you wildin’ fam!",
        f"Ayy, {character_name}’s real, stop clownin’!",
        f"Pfft, I’m {character_name}, no bot nonsense!",
        f"Man, {character_name}’s vibes, you buggin’!",
        f"Chill, I’m {character_name}, no bot, bruh!",
        f"No way, {character_name} ain’t robotic, you good?",
        f"Fam, I’m {character_name}, you tweakin’!",
        f"Get it straight, {character_name}’s no bot!",
        f"Ha, you cappin’? I’m {character_name}, fam!",
        f"Nope, {character_name}’s real, you trippin’!",
        f"Bruh, I’m {character_name}, you slippin’!",
        f"Yo, no bot vibes, just {character_name}!",
        f"Ayy, {character_name}’s the real deal, chill!",
        f"Pfft, you wild! I’m {character_name}, not bot!",
        f"Man, I’m {character_name}, you clownin’ or what?",
        f"Chill, {character_name}’s legit, you wildin’!",
        f"No bot here, I’m {character_name}, no cap!",
        f"What?! {character_name}’s real, you buggin’!",
        f"Nah, I’m {character_name}, stop playin’!",
        f"Bruh, {character_name} ain’t no bot, relax!",
        f"Yo, I’m {character_name}, you cappin’ hard!",
        f"Ayy, no bot, just {character_name}, you good?",
        f"Pfft, {character_name}’s no bot, you tweakin’!",
        f"Man, {character_name}’s real, you trippin’!",
        f"Chill out, I’m {character_name}, you slippin’!",
        f"No way, {character_name}’s vibes, you buggin’!",
        f"Fam, I’m {character_name}, no bot nonsense!",
        f"Get real, {character_name}’s no bot, bruh!",
        f"Ha, you wild! {character_name}’s no bot!",
        f"Nope, I’m {character_name}, you trippin’!",
        f"Bruh, {character_name}’s real, you buggin’!",
        f"Yo, I’m {character_name}, no bot vibes!",
        f"Ayy, no bot, just {character_name}, relax!",
        f"Pfft, {character_name}’s no bot, you wild!",
        f"Man, I’m {character_name}, you cappin’!",
        f"Chill, I’m {character_name}, you slippin’!",
        f"No bot, {character_name}’s real, you tweakin’!",
        f"What?! {character_name}’s legit, you buggin’!",
        f"Nah, I’m {character_name}, you wildin’!",
        f"Bruh, no bot, I’m {character_name}, fam!",
        f"Yo, {character_name}’s no bot, you good?",
        f"Ayy, I’m {character_name}, you trippin’!",
        f"Pfft, {character_name}’s real, you cappin’!",
        f"Man, I’m {character_name}, no bot nonsense!",
        f"Chill, {character_name}’s no bot, you wild!",
        f"No way, I’m {character_name}, you slippin’!",
        f"Fam, I’m {character_name}’s legit, you buggin’!",
        f"Get real, I’m {character_name}, you tweakin’!",
        f"Ha, I’m {character_name}, no bot, bruh!",
        f"Nope, I’m {character_name}, you wildin’!",
        f"Bruh, I’m {character_name}, you cappin’!",
        f"Yo, {character_name}’s no bot, relax!"
    ]

    project_info = f"Project: {project_details['name']} - {project_details['description']} (Features: {project_details['key_features']})"

    if use_google_ai:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={google_api_key}'
        headers = {'Content-Type': 'application/json'}
        
        # Dynamic tone adjustments based on message type and content
        if is_personal_question(prompt):
            tone_adjustment = "Use moderate slang, emphasize character personality, keep it friendly and relatable."
            full_prompt = (
                f"{base_prompt}\nYou're a {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nQuestion: {prompt}\n"
                f"Answer like a real person, in English, max 10 words, Discord style, "
                f"use varied vocab like '{random_vocab}'. Do not use your name unless necessary."
            )
        elif is_project_related(prompt, project_keywords):
            if is_technical_question(prompt):
                tone_adjustment = "Lean professional, clear, and direct with minimal slang, but keep it approachable."
            else:
                tone_adjustment = "Mix heavy slang with clear project details, keep it hype and engaging."
            full_prompt = (
                f"{base_prompt}\nYou're a {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\n{project_info}\nQuestion: {prompt}\n"
                f"Answer with project context, in English, max 10 words, Discord style, "
                f"use varied vocab like '{random_vocab}'. Do not use your name unless necessary."
            )
        elif is_simple_question(prompt):
            tone_adjustment = "Max slang, super short and chill, like a quick Discord ping."
            full_prompt = (
                f"{base_prompt}\nYou're a {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nQuestion: {prompt}\n"
                f"Answer short, friendly, like a Discord pal, in English, max 5 words, "
                f"use varied vocab like '{random_vocab}'. Do not use your name."
            )
        else:
            tone_adjustment = "Balance slang and clarity, lean into character vibe, mention project only if it fits."
            full_prompt = (
                f"{base_prompt}\nYou're a {personality}. Never break character. Never mention being a bot or AI.\n"
                f"Tone: {tone_adjustment}\nOptional context: {project_info}\nQuestion: {prompt}\n"
                f"Answer in English, max 10 words, Discord style, use varied vocab like '{random_vocab}'. "
                f"Do not use your name unless necessary."
            )

        data = {'contents': [{'parts': [{'text': full_prompt}]}]}
        log_message(f"Sending prompt to Gemini: {full_prompt}")

        for attempt in range(3):
            try:
                response = session.post(url, headers=headers, json=data)
                if response.status_code == 429:
                    retry_after = response.json().get("retry_after", 60)
                    log_message(f"⚠️ Rate limit hit! Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                ai_response = response.json()
                response_text = ai_response['candidates'][0]['content']['parts'][0]['text']
                
                # Refined blocked words to avoid AI giveaways
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
                if len(words) > 10:
                    response_text = " ".join(words[:10])
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

def auto_reply(channel_id, random_read_reply_delay, direct_reply_check_delay, use_google_ai, reply_mode):
    global last_message_id, bot_user_id, last_bot_message_id, bot_running
    headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
    try:
        bot_info_response = session.get('https://discord.com/api/v9/users/@me', headers=headers)
        bot_info_response.raise_for_status()
        bot_user_id = bot_info_response.json().get('id')
        log_message(f"✅ Bot user ID: {bot_user_id}")
        # Send short, non-clichéd initial message
        welcome_messages = [
            "What’s the Web3 buzz?",
            "Any crypto heat?",
            "Web3’s poppin’, what’s good?",
            "Yo, what’s cookin’ in Web3?"
        ]
        welcome_message = random.choice(welcome_messages)
        send_message(channel_id, welcome_message)
    except requests.exceptions.RequestException as e:
        log_message(f"⚠️ Failed to retrieve bot information: {e}")
        if hasattr(e, 'response') and e.response is not None:
            log_message(f"API response: {e.response.text}")
        return
    settings = load_settings()
    proactive_delay = settings["proactive_delay"] if settings else 3600
    threading.Thread(target=update_project_file, daemon=True).start()
    threading.Thread(target=process_message_queue, daemon=True).start()
    threading.Thread(target=post_proactive_message, args=(channel_id, proactive_delay), daemon=True).start()
    threading.Thread(target=reply_to_random_message, args=(channel_id, random_read_reply_delay, reply_mode), daemon=True).start()
    threading.Thread(target=reply_to_direct_replies, args=(channel_id, direct_reply_check_delay, reply_mode), daemon=True).start()

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
    random_read_reply_delay = settings["random_read_reply_delay"]
    direct_reply_check_delay = settings["direct_reply_check_delay"]

    if not discord_token or not google_api_key or not channel_id:
        log_message("⚠️ Discord Token, Google API Key, and Channel ID are required!")
        return

    bot_running = True
    log_message("✅ Starting chatbot...")
    try:
        auto_reply(channel_id, random_read_reply_delay, direct_reply_check_delay, use_google_ai, reply_mode)
        while bot_running:
            time.sleep(1)  # Keep main thread alive
    except KeyboardInterrupt:
        bot_running = False
        log_message("✅ Chatbot stopped by user.")

if __name__ == "__main__":
    main()
