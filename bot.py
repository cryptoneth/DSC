import json
import time
import os
import random
import requests
import re
import threading
import hmac
import hashlib
import base64
from datetime import datetime
from cryptography.fernet import Fernet
import uuid

# Global variables
last_message_id = None
bot_user_id = None
last_ai_response = None
last_bot_message_id = None
bot_running = False
discord_token = None
google_api_key = None
wordpress_api_url = "https://sinalentor.ir/wp-json/custom/v1/validate-license"  # Replace with your WordPress URL

# Hardcoded LICENSE_SECRET_KEY with base64
encoded_license_key = "TXpXdmczR05RUU5oS2lJRktSNXNNZHZ2WnMwazB6d2I="  # Your WordPress secret key in base64
try:
    license_key = base64.b64decode(encoded_license_key).decode('utf-8')
except Exception as e:
    print(f"⚠️ Error decoding LICENSE_SECRET_KEY: {e}")
    license_key = "your-secret-key"

session = requests.Session()

# Files for storing activation and settings
ACTIVATION_FILE = "activation.dat"
SETTINGS_FILE = "settings.json"
CIPHER_KEY = Fernet.generate_key()
cipher = Fernet(CIPHER_KEY)

def log_message(message):
    """Log message to console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}")

def get_hardware_id():
    """Get Hardware ID"""
    return str(uuid.getnode())

def generate_license_key(hardware_id):
    """Generate license key with HMAC"""
    return base64.urlsafe_b64encode(
        hmac.new(license_key.encode(), hardware_id.encode(), hashlib.sha256).digest()
    ).decode()

def validate_license_locally():
    """Check local activation"""
    try:
        if not os.path.exists(ACTIVATION_FILE):
            log_message("⚠️ Activation file not found.")
            return False
        with open(ACTIVATION_FILE, 'rb') as f:
            encrypted_data = f.read()
        decrypted_data = cipher.decrypt(encrypted_data).decode()
        data = json.loads(decrypted_data)
        if data['hardware_id'] == get_hardware_id() and data['activated']:
            log_message("✅ Local activation verified.")
            return True
        log_message("⚠️ Invalid activation data.")
        return False
    except Exception as e:
        log_message(f"⚠️ Error reading activation file: {e}")
        return False

def save_activation():
    """Save activation status"""
    try:
        data = {'hardware_id': get_hardware_id(), 'activated': True}
        encrypted_data = cipher.encrypt(json.dumps(data).encode())
        with open(ACTIVATION_FILE, 'wb') as f:
            f.write(encrypted_data)
        log_message("✅ Activation file saved.")
    except Exception as e:
        log_message(f"⚠️ Error saving activation file: {e}")

def validate_license_online(license_key_input):
    """Validate license with WordPress server"""
    hardware_id = get_hardware_id()
    headers = {
        'Authorization': f'Bearer {license_key}',
        'Content-Type': 'application/json'
    }
    try:
        response = session.post(wordpress_api_url, json={
            'license_key': license_key_input,
            'hardware_id': hardware_id
        }, headers=headers)
        response.raise_for_status()
        result = response.json()
        if result.get('valid'):
            save_activation()
            log_message("✅ License validated successfully!")
            return True
        else:
            log_message(f"⚠️ Invalid license key: {result.get('message')}")
            return False
    except Exception as e:
        log_message(f"⚠️ License validation failed: {e}")
        return False

def load_settings():
    """Load settings from settings.json"""
    global discord_token, google_api_key
    default_settings = {
        "personality": {
            "fa": "من یه کریپتو بازم که دیوونه بلاک‌چین و توکنه! همیشه آماده‌ام درباره دیفای و NFT گپ بزنم و چیزای باحال بگم.",
            "en": "I'm a crypto bro who's crazy about blockchain and tokens! Always ready to chat about DeFi and NFTs with some cool vibes.",
            "id": "Saya pecinta kripto yang tergila-gila dengan blockchain dan token! Selalu siap ngobrol tentang DeFi dan NFT dengan gaya santai."
        },
        "project_prompt": {
            "fa": "پاسخ‌ها باید درباره پروژه‌های کریپتویی مثل دیفای، NFT و بلاک‌چین باشه. اطلاعات دقیق بده، ولی صمیمی و یه کم عامیانه.",
            "en": "Responses should be about crypto projects like DeFi, NFTs, and blockchain. Give accurate info, but keep it chill and a bit casual.",
            "id": "Jawaban harus tentang proyek kripto seperti DeFi, NFT, dan blockchain. Berikan info akurat, tapi tetap santai dan sedikit kasual."
        },
        "project_keywords": {
            "fa": "کریپتو, بلاک‌چین, توکن, دیفای, NFT",
            "en": "crypto, blockchain, token, DeFi, NFT",
            "id": "kripto, blockchain, token, DeFi, NFT"
        },
        "discord_token": "",
        "google_api_key": "",
        "channel_id": "",
        "language": "en",
        "use_google_ai": True,
        "reply_mode": True,
        "read_delay": 10,
        "reply_delay": 5
    }
    try:
        if not os.path.exists(SETTINGS_FILE):
            log_message("⚠️ Settings file not found, using defaults.")
            return default_settings
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        # Decrypt tokens
        if settings.get("discord_token"):
            settings["discord_token"] = cipher.decrypt(base64.b64decode(settings["discord_token"])).decode()
        if settings.get("google_api_key"):
            settings["google_api_key"] = cipher.decrypt(base64.b64decode(settings["google_api_key"])).decode()
        discord_token = settings.get("discord_token")
        google_api_key = settings.get("google_api_key")
        return settings
    except Exception as e:
        log_message(f"⚠️ Error loading settings: {e}")
        return default_settings

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
    """Configure settings via terminal"""
    settings = load_settings()
    if os.path.exists(SETTINGS_FILE) and settings.get("discord_token") and settings.get("google_api_key"):
        log_message("✅ Using existing settings.")
        return settings

    print("⚙️ Configuring settings for the first time...")
    settings = {
        "personality": {
            "fa": input("Personality Prompt (Persian, press Enter for default): ") or "من یه کریپتو بازم که دیوونه بلاک‌چین و توکنه! همیشه آماده‌ام درباره دیفای و NFT گپ بزنم و چیزای باحال بگم.",
            "en": input("Personality Prompt (English, press Enter for default): ") or "I'm a crypto bro who's crazy about blockchain and tokens! Always ready to chat about DeFi and NFTs with some cool vibes.",
            "id": input("Personality Prompt (Indonesian, press Enter for default): ") or "Saya pecinta kripto yang tergila-gila dengan blockchain dan token! Selalu siap ngobrol tentang DeFi dan NFT dengan gaya santai."
        },
        "project_prompt": {
            "fa": input("Project Prompt (Persian, press Enter for default): ") or "پاسخ‌ها باید درباره پروژه‌های کریپتویی مثل دیفای، NFT و بلاک‌چین باشه. اطلاعات دقیق بده، ولی صمیمی و یه کم عامیانه.",
            "en": input("Project Prompt (English, press Enter for default): ") or "Responses should be about crypto projects like DeFi, NFTs, and blockchain. Give accurate info, but keep it chill and a bit casual.",
            "id": input("Project Prompt (Indonesian, press Enter for default): ") or "Jawaban harus tentang proyek kripto seperti DeFi, NFT, dan blockchain. Berikan info akurat, tapi tetap santai dan sedikit kasual."
        },
        "project_keywords": {
            "fa": input("Project Keywords (Persian, comma-separated, press Enter for default): ") or "کریپتو, بلاک‌چین, توکن, دیفای, NFT",
            "en": input("Project Keywords (English, comma-separated, press Enter for default): ") or "crypto, blockchain, token, DeFi, NFT",
            "id": input("Project Keywords (Indonesian, comma-separated, press Enter for default): ") or "kripto, blockchain, token, DeFi, NFT"
        },
        "discord_token": input("Enter Discord Token: ").strip(),
        "google_api_key": input("Enter Google API Key: ").strip(),
        "channel_id": input("Enter Discord Channel ID: ").strip(),
        "language": input("Enter Response Language (fa, en, id): ").strip() or "en",
        "use_google_ai": input("Use Google Gemini AI? (yes/no): ").strip().lower() == "yes",
        "reply_mode": input("Enable Reply Mode? (yes/no): ").strip().lower() == "yes",
        "read_delay": int(input("Enter Read Delay (seconds, default 10): ") or 10),
        "reply_delay": int(input("Enter Reply Delay (seconds, default 5): ") or 5)
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

def read_personality(language="en"):
    """Read personality from settings"""
    settings = load_settings()
    return settings["personality"].get(language, "I'm a crypto bro who's crazy about blockchain and tokens! Always ready to chat about DeFi and NFTs with some cool vibes.")

def read_project_prompt(language="en"):
    """Read project prompt and keywords from settings"""
    settings = load_settings()
    prompt = settings["project_prompt"].get(language, "Responses should be about crypto projects like DeFi, NFTs, and blockchain. Give accurate info, but keep it chill and a bit casual.")
    keywords = settings["project_keywords"].get(language, " erő, blockchain, token, DeFi, NFT").split(", ")
    return prompt, keywords

def update_project_file():
    """Automatically update project prompt every 24 hours (for English)"""
    while True:
        try:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={google_api_key}'
            headers = {'Content-Type': 'application/json'}
            current_prompt, _ = read_project_prompt(language="en")
            data = {
                'contents': [{
                    'parts': [{
                        'text': f"Current project prompt: {current_prompt}\nPlease write an updated prompt for crypto projects, including project details and keywords. Keep it short and casual, in English."
                    }]
                }]
            }
            response = session.post(url, headers=headers, json=data)
            response.raise_for_status()
            new_prompt = response.json()['candidates'][0]['content']['parts'][0]['text']
            settings = load_settings()
            settings["project_prompt"]["en"] = new_prompt
            settings["project_keywords"]["en"] = "crypto, blockchain, token, DeFi, NFT"
            save_settings(settings)
            log_message("✅ Project prompt updated successfully.")
        except Exception as e:
            log_message(f"⚠️ Failed to update project prompt: {e}")
        time.sleep(24 * 60 * 60)

def is_personal_question(prompt):
    """Detect personal questions"""
    personal_keywords = [
        "تو کی هستی", "هویت", "خودت", "ربات", "هوش مصنوعی", 
        "چه کسی", "درباره تو", "تو چی هستی", "از خودت",
        "who are you", "identity", "yourself", "bot", "artificial intelligence",
        "who is", "about you", "what are you",
        "siapa kamu", "identitas", "dirimu", "robot", "kecerdasan buatan",
        "siapa", "tentang kamu", "apa kamu"
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
        "سلام", "خوبی", "بنازم", "چطوره", "هی", "اوکی", "باحال",
        "hi", "how's it going", "cool", "hey", "okay",
        "halo", "apa kabar", "keren", "hai", "ok"
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
    cleaned = emoji_pattern.sub(r'', message). Kurtz
    return len(cleaned) > 5

def generate_reply(prompt, use_google_ai=True, language="en"):
    global last_ai_response
    personality = read_personality(language)
    project_prompt, project_keywords = read_project_prompt(language)
    base_prompt = {
        "fa": "Youre a cool crypto bro who chats about blockchain tokens and DeFi in a chill and friendly way Keep responses short 15 to 20 words casual and informal no punctuation no emojis in Persian",
        "en": "Youre a cool crypto bro who chats about blockchain tokens and DeFi in a chill and friendly way Keep responses short 15 to 20 words casual and informal no punctuation no emojis",
        "id": "Kamu penggemar kripto keren yang ngobrol tentang blockchain token dan DeFi santai ramah Jawaban singkat 15 sampai 20 kata akrab kasual tanpa tanda baca tanpa emoji dalam Bahasa Indonesia"
    }

    if use_google_ai:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={google_api_key}'
        headers = {'Content-Type': 'application/json'}
        
        if is_personal_question(prompt):
            full_prompt = f"{base_prompt[language]}\nYour personality: {personality}\nQuestion: {prompt}\nAnswer as if youre a real person dont mention being a bot or AI keep it in {language == 'fa' and 'Persian' or language == 'en' and 'English' or 'Indonesian'} friendly and casual"
        elif is_project_related(prompt, project_keywords):
            full_prompt = f"{base_prompt[language]}\nProject prompt: {project_prompt}\nQuestion: {prompt}\nAnswer with accurate crypto info friendly and casual in {language == 'fa' and 'Persian' or language == 'en' and 'English' or 'Indonesian'}"
        elif is_simple_question(prompt):
            full_prompt = f"{base_prompt[language]}\nQuestion: {prompt}\nAnswer very short and friendly like a cool friend in {language == 'fa' and 'Persian' or language == 'en' and 'English' or 'Indonesian'}"
        else:
            full_prompt = f"{base_prompt[language]}\nQuestion: {prompt}\nAnswer friendly with a crypto vibe in {language == 'fa' and 'Persian' or language == 'en' and 'English' or 'Indonesian'} and a bit casual"

        data = {'contents': [{'parts': [{'text': full_prompt}]}]}
        log_message(f"Sending prompt to Gemini {full_prompt}")

        for attempt in range(3):
            try:
                response = session.post(url, headers=headers, json=data)
                response.raise_for_status()
                ai_response = response.json()
                response_text = ai_response['candidates'][0]['content']['parts'][0]['text']
                blocked_words = [
                    "من یک ربات هستم", "به عنوان یک مدل هوش مصنوعی", 
                    "من یک مدل زبانی هستم", "برنامه کامپیوتری", "هوش مصنوعی",
                    "پردازش", "زنجیره بلوکی", "تحلیل داده", "الگوریتم", 
                    "ههه", "جوک", "شوخی", "😄", "😂", "😜",
                    "I am a bot", "as an AI model", "language model", 
                    "artificial intelligence", "processing", "algorithm", 
                    "haha", "joke", "lol",
                    "Saya robot", "sebagai model AI", "kecerdasan buatan",
                    "pemrosesan", "algoritma", "haha", "lelucon"
                ]
                for word in blocked_words:
                    response_text = response_text.replace(word, "")
                response_text = response_text.strip().split("\n")[0]
                words = response_text.split()
                if len(words) > 20:
                    response_text = " ".join(words[:20])
                elif len(words) < 15:
                    response_text = response_text + " crypto vibes cool stuff blockchain tokens"
                response_text = re.sub(r'[.,!?;]', '', response_text)
                response_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', response_text)
                if any(word.lower() in response_text.lower() for word in blocked_words):
                    log_message("Response contains forbidden or robotic words retrying")
                    continue
                if response_text == last_ai_response:
                    log_message("AI provided the same response retrying")
                    continue
                last_ai_response = response_text
                return response_text
            except requests.exceptions.RequestException as e:
                log_message(f"AI request failed {e}")
                return {
                    "fa": "مشکلی پیش اومد بعدا امتحان کن کریپتو باحاله",
                    "en": "Something went wrong try later crypto is cool",
                    "id": "Ada masalah coba lagi nanti kripto itu keren"
                }[language]
    return {
        "fa": "نشد جواب بدم بعدا امتحان کن کریپتو باحاله",
        "en": "Couldnt respond try later crypto is cool",
        "id": "Tidak bisa menjawab coba lagi nanti kripto keren"
    }[language]

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

def auto_reply(channel_id, read_delay, reply_delay, use_google_ai, reply_mode, language):
    global last_message_id, bot_user_id, last_bot_message_id, bot_running
    headers = {'Authorization': f'{discord_token}', 'User-Agent': 'Mozilla/5.0'}
    try:
        bot_info_response = session.get('https://discord.com/api/v9/users/@me', headers=headers)
        bot_info_response.raise_for_status()
        bot_user_id = bot_info_response.json().get('id')
    except requests.exceptions.RequestException as e:
        log_message(f"Failed to retrieve bot information {e}")
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
                            log_message(f"Received reply {user_message}")
                            response_text = generate_reply(user_message, use_google_ai, language)
                            wait_time = reply_delay + random.uniform(5, 10)
                            log_message(f"Waiting {wait_time} seconds before replying")
                            time.sleep(wait_time)
                            send_message(channel_id, response_text, reply_to=message_id if reply_mode else None, reply_mode=reply_mode)
                            last_message_id = message_id
            read_wait = read_delay + random.uniform(10, 20)
            log_message(f"Waiting {read_wait} seconds before checking for new messages")
            time.sleep(read_wait)
        except requests.exceptions.RequestException as e:
            log_message(f"Request error {e}")
            time.sleep(read_delay)
    log_message("Chatbot stopped")

def main():
    """Main function"""
    global bot_running, discord_token, google_api_key

    # Check license
    if not validate_license_locally():
        license_key_input = input("Please enter your license key: ").strip()
        if not license_key_input:
            log_message("⚠️ License key cannot be empty!")
            return
        if not validate_license_online(license_key_input):
            return

    # Load or configure settings
    settings = configure_settings()
    discord_token = settings["discord_token"]
    google_api_key = settings["google_api_key"]
    channel_id = settings["channel_id"]
    language = settings["language"]
    use_google_ai = settings["use_google_ai"]
    reply_mode = settings["reply_mode"]
    read_delay = settings["read_delay"]
    reply_delay = settings["reply_delay"]

    if not discord_token or not google_api_key:
        log_message("⚠️ Discord Token and Google API Key are required!")
        return

    bot_running = True
    log_message("✅ Starting chatbot...")
    try:
        auto_reply(channel_id, read_delay, reply_delay, use_google_ai, reply_mode, language)
    except KeyboardInterrupt:
        bot_running = False
        log_message("✅ Chatbot stopped by user.")

if __name__ == "__main__":
    main()
