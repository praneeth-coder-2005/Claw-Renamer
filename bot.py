# main_bot.py
import logging
import os
import re
import requests
import telebot
from telebot import types
from urllib.parse import urlparse
from time import time
import config  # Import the config file
from math import ceil

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Initialize bot with the token from config
bot = telebot.TeleBot(config.TOKEN)

# Global settings (Can be persistent if you want)
settings = {
    "rename_mode": "manual",  # or "auto"
    "prefix": "",
    "suffix": "",
    "upload_type": "media",
}

# Dictionary to store file downloading progress data
downloading_progress = {}


@bot.message_handler(commands=["start"])
def start(message):
    """Sends a welcome message with instructions."""
    bot.reply_to(
        message,
        "Hi! I'm an Auto Rename Bot.\n\n"
        "Send me a file or a download link, and I'll rename and send it back to you.\n\n"
        "You can use /settings to see your current settings and modify rename mode.\n"
        "To rename it with manual rename mode, just add the renamed file name after the file or the link, separated by space",
    )


@bot.message_handler(commands=["settings"])
def settings_command(message):
    """Displays current settings."""
    message_text = (
        "Current Settings:\n\n"
        f"Rename Mode: {settings['rename_mode']}\n"
        f"Prefix: {settings['prefix'] or 'None'}\n"
        f"Suffix: {settings['suffix'] or 'None'}\n"
        f"Upload Type: {settings['upload_type']}\n\n"
        "Use /rename_mode to change rename mode."
    )
    bot.reply_to(message, message_text)


@bot.message_handler(commands=["rename_mode"])
def rename_mode_command(message):
    """Allows user to set rename mode."""
    args = message.text.split()[1:]
    if args and args[0].lower() in ["manual", "auto"]:
        settings["rename_mode"] = args[0].lower()
        bot.reply_to(message, f"Rename mode set to {settings['rename_mode']}.")
    else:
        bot.reply_to(
            message, "Invalid rename mode. Use /rename_mode manual or /rename_mode auto"
        )


def sanitize_filename(filename):
    """Sanitizes the filename by removing or replacing invalid characters"""
    # Define a regular expression to match invalid filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    # Remove or replace invalid characters
    filename = re.sub(invalid_chars, '', filename)
    # Truncate very long filenames
    filename = filename[:200]  # Ensure filepaths on all OS are under 255 chars
    return filename


def format_size(size_bytes):
    """Formats bytes into human-readable size (KiB, MiB, GiB)"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes / 1024:.2f} KiB"
    elif size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.2f} MiB"
    else:
        return f"{size_bytes / 1024**3:.2f} GiB"

def progress_bar_callback(current_bytes, total_bytes, message, filename: str):
    """Callback function to show a complete progress bar for downloading.

    Args:
        current_bytes (int): The number of bytes downloaded so far.
        total_bytes (int): The total size of the file to be downloaded.
        message (types.Message): The Telegram message object.
        filename (str): The filename of the file being downloaded.
    """
    if filename not in downloading_progress:
        downloading_progress[filename] = {
            "start_time": time(),
            "prev_percentage": 0,
        }

    percent = int(current_bytes / total_bytes * 100)
    if percent > downloading_progress[filename]["prev_percentage"]:
        downloading_progress[filename]["prev_percentage"] = percent
        elapsed_time = time() - downloading_progress[filename]["start_time"]
        speed = current_bytes / elapsed_time if elapsed_time else 0
        if speed>0:
          eta_seconds = (total_bytes - current_bytes) / speed
        else:
          eta_seconds = 0
        
        eta = format_time(eta_seconds)
        processed = format_size(current_bytes)
        total = format_size(total_bytes)
        speed_formatted = format_size(speed)+"/s"

        progress_bar = "▰" * (percent // 10) + "▢" * (10 - (percent // 10))
        msg = (
            f"Downloading...\n"
            f"[{progress_bar}] {percent:.2f}%\n"
            f"Processed: {processed} of {total}\n"
            f"Speed: {speed_formatted} | ETA: {eta}"
        )
        if percent == 100:
            msg += "\nFinished downloading!"
        bot.edit_message_text(
            text=msg,
            chat_id=message.chat.id,
            message_id=message.message_id + 1,
        )
def format_time(seconds):
  """Formats seconds to hours, minutes, and seconds"""
  if seconds < 60:
      return f"{seconds:.0f}s"
  elif seconds < 3600:
     minutes = seconds // 60
     seconds = seconds % 60
     return f"{minutes:.0f}m {seconds:.0f}s"
  else:
     hours = seconds // 3600
     minutes = (seconds % 3600) // 60
     seconds = seconds % 60
     return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"

def download_file(
    message, file_url: str, new_file_name: str = None
) -> str | None:
    """Downloads a file from a URL and returns the local path to it."""
    try:
        parsed_url = urlparse(file_url)
        # Try to use original filename, otherwise a generic name
        if new_file_name:
            filename = sanitize_filename(new_file_name)
        else:
            path = parsed_url.path
            filename = path.split("/")[-1] if path else "downloaded_file"
            filename = sanitize_filename(filename)
        if not filename:
            filename = "downloaded_file"
        
        if not filename.lower().endswith(('.jpg','.jpeg', '.png', '.pdf', '.txt', '.mp4', '.avi', '.mkv', '.mov', '.mp3', '.wav', '.ogg', '.zip', '.rar','.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')):
            filename = filename+".txt"

        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0

            # Create initial progress message
            msg = f"Downloading {filename}..."
            if total_size:
                msg += f"\nSize: {format_size(total_size)}"
            progress_msg = bot.send_message(
                chat_id=message.chat.id, text=msg
            )

            # Construct the local file path
            local_filename = os.path.join("downloads", filename)
            os.makedirs(os.path.dirname(local_filename), exist_ok=True)  # Ensure directory exists

            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                          progress_bar_callback(downloaded, total_size, message, filename)
        if total_size:
          del downloading_progress[filename]
        # Delete progress message if download complete
        if total_size:
            bot.delete_message(
                chat_id=message.chat.id, message_id=progress_msg.message_id
            )
        return local_filename
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading from {file_url}: {e}")
        bot.reply_to(
            message, f"Sorry, could not download the file from {file_url}."
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading file: {e}")
        bot.reply_to(
            message, "An unexpected error occurred while downloading the file."
        )
        return None

def get_file_path(file_id, bot_token):
    """Constructs the file path from the file ID without bot.get_file"""
    try:
        response = requests.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        file_path_result = response.json()
        if file_path_result["ok"]:
            return file_path_result["result"]["file_path"]
        else:
          logger.error(f"Error getting file path {file_path_result}")
          return None
    except requests.exceptions.RequestException as e:
          logger.error(f"Error constructing the telegram file path: {e}")
          return None

@bot.message_handler(func=lambda message: True, content_types=["text", "document"])
def process_file(message):
    """Handles incoming files or links."""

    message_text = message.text
    file_name_from_message = None
    file_url = None
    if message.document:
        file_id = message.document.file_id
        filename = message.document.file_name
        if message_text and message_text!=filename:
            splitted_message = message_text.split(" ",1)
            if len(splitted_message)>1:
               file_name_from_message = splitted_message[1]
        file_path = get_file_path(file_id,config.TOKEN)
        if file_path:
            file_url = f"https://api.telegram.org/file/bot{config.TOKEN}/{file_path}"
        else:
            bot.reply_to(message, "Sorry, could not process the file from telegram.")
            return

    elif message_text and re.match(r'https?://\S+', message_text):
        splitted_message = message_text.split(" ", 1)
        if len(splitted_message) > 1:
            file_url = splitted_message[0]
            file_name_from_message = splitted_message[1]
        else:
            file_url = splitted_message[0]
    else:
        bot.reply_to(message, "Please send a file or a valid download link.")
        return

    if file_url:
        if not isinstance(file_url, str):
            bot.reply_to(message, "Please send a valid download link or file.")
            return
        local_file_path = download_file(message, file_url, file_name_from_message)
    else:
        local_file_path = file_url

    if local_file_path is None:
        return

    try:
        # Rename Logic
        filename = os.path.basename(local_file_path)
        file_ext = os.path.splitext(filename)[1]
        if settings["rename_mode"] == "manual":
           if file_name_from_message:
                renamed_file = sanitize_filename(file_name_from_message)
           else:
               renamed_file = sanitize_filename(filename)
           if not renamed_file.lower().endswith(file_ext.lower()):
                renamed_file += file_ext
        elif settings["rename_mode"] == "auto":
            renamed_file = sanitize_filename(filename)
            if settings["prefix"]:
                renamed_file = f"{settings['prefix']}{renamed_file}"
            if settings["suffix"]:
                renamed_file = f"{renamed_file}{settings['suffix']}"

        renamed_file_path = os.path.join("downloads",renamed_file)
        os.rename(local_file_path,renamed_file_path)
        
        # Upload File
        try:
            if settings["upload_type"] == "media":
                with open(renamed_file_path, "rb") as f:
                    bot.send_document(
                        chat_id=message.chat.id,
                        document=f,
                        filename=renamed_file,
                    )
        except Exception as upload_error:
            logger.error(f"Error during upload: {upload_error}")
            bot.reply_to(
                message, "Error uploading the file. Please try again."
            )
            return

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        bot.reply_to(message, "An unexpected error occurred.")
    finally:
        if local_file_path and os.path.exists(renamed_file_path):
          os.remove(renamed_file_path)

def main():
    """Start the bot."""
    bot.infinity_polling()


if __name__ == "__main__":
    main()
