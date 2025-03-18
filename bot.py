import os
import time
import asyncio
import tempfile
import subprocess
from typing import List, Optional, Union
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import MessageNotModified
import humanize

# API credentials
API_ID = 28271744
API_HASH = "1df4d2b4dc77dc5fd65622f9d8f6814d"
BOT_TOKEN = "7466186150:AAH3OyHD5MUYW6YzPfQHFtL-uZUHNNDZKBM"

# Initialize the Pyrogram client
app = Client(
    "screenshot_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Progress animation frames
PROGRESS_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]

class ProgressMessage:
    """Class to handle progress message updates with animations"""
    def __init__(self, message: Message, total_steps: int = 3):
        self.message = message
        self.current_step = 0
        self.total_steps = total_steps
        self.animation_task = None
        self.stop_animation = False
        self.current_text = ""
    
    async def _animate(self, text: str):
        """Animate the progress message"""
        i = 0
        while not self.stop_animation:
            try:
                frame = PROGRESS_FRAMES[i % len(PROGRESS_FRAMES)]
                await self.message.edit_text(f"{text} {frame}")
                i += 1
                await asyncio.sleep(0.5)
            except MessageNotModified:
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Animation error: {e}")
                await asyncio.sleep(1)
    
    async def update(self, text: str, animate: bool = True):
        """Update the progress message with new text"""
        self.current_text = text
        
        # Stop any existing animation
        if self.animation_task:
            self.stop_animation = True
            try:
                await self.animation_task
            except:
                pass
            self.stop_animation = False
        
        # Start new animation or just update text
        if animate:
            self.animation_task = asyncio.create_task(self._animate(text))
        else:
            await self.message.edit_text(text)
    
    async def complete_step(self, completion_text: str):
        """Mark current step as complete and move to next step"""
        self.current_step += 1
        progress_bar = "▰" * self.current_step + "▱" * (self.total_steps - self.current_step)
        await self.update(f"{completion_text}\n\nProgress: {progress_bar} ({self.current_step}/{self.total_steps})", animate=False)
    
    async def finish(self, final_text: str):
        """Finish the progress updates"""
        if self.animation_task:
            self.stop_animation = True
            try:
                await self.animation_task
            except:
                pass
        await self.message.edit_text(final_text)


def get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video file using ffprobe
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Duration of the video in seconds
    """
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        video_path
    ]
    
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        duration = float(output.decode('utf-8').strip())
        return duration
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting video duration: {e}")
        return 0.0


async def extract_screenshots(
    video_path: str, 
    num_screenshots: int,
    progress_callback=None
) -> List[str]:
    """
    Extract screenshots from a video file using ffmpeg
    
    Args:
        video_path: Path to the video file
        num_screenshots: Number of screenshots to extract
        progress_callback: Optional callback function for progress updates
        
    Returns:
        List of paths to the extracted screenshots
    """
    # Get video duration
    duration = get_video_duration(video_path)
    if duration <= 0:
        raise ValueError("Could not determine video duration")
    
    # Create temporary directory for screenshots
    temp_dir = tempfile.mkdtemp()
    screenshot_paths = []
    
    # Calculate timestamps for screenshots
    if num_screenshots > 1:
        # Distribute screenshots evenly across the video
        interval = duration / (num_screenshots + 1)
        timestamps = [(i + 1) * interval for i in range(num_screenshots)]
    else:
        # If only one screenshot, take it from the middle
        timestamps = [duration / 2]
    
    # Extract screenshots
    for i, timestamp in enumerate(timestamps):
        if progress_callback:
            await progress_callback(i, num_screenshots)
        
        # Format timestamp for ffmpeg (HH:MM:SS.mmm)
        hours, remainder = divmod(timestamp, 3600)
        minutes, seconds = divmod(remainder, 60)
        timestamp_str = f"{int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}"
        
        # Output path for this screenshot
        screenshot_path = os.path.join(temp_dir, f"screenshot_{i+1}.jpg")
        
        # FFmpeg command to extract the screenshot
        cmd = [
            "ffmpeg",
            "-ss", timestamp_str,
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            screenshot_path
        ]
        
        # Run the command
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            screenshot_paths.append(screenshot_path)
        except subprocess.CalledProcessError as e:
            print(f"Error extracting screenshot at {timestamp_str}: {e}")
    
    return screenshot_paths


@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Handle the /start command"""
    await message.reply_text(
        "👋 Welcome to the Screenshot Generator Bot!\n\n"
        "Send me any video file, and I'll generate screenshots for you.\n\n"
        "Just upload a video and tell me how many screenshots you want!"
    )


@app.on_message(filters.command("help"))
async def help_command(client, message):
    """Handle the /help command"""
    await message.reply_text(
        "📋 **How to use this bot:**\n\n"
        "1. Send me any video file\n"
        "2. I'll analyze the file and show you its details\n"
        "3. Tell me how many screenshots you want (1-10)\n"
        "4. I'll generate and send the screenshots to you\n\n"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/help - Show this help message"
    )


@app.on_message(filters.video | filters.document)
async def handle_file(client, message):
    """Handle video or document files"""
    # Check if it's a video
    is_video = bool(message.video)
    file_id = message.video.file_id if is_video else message.document.file_id
    file_name = message.video.file_name if is_video and hasattr(message.video, 'file_name') else message.document.file_name
    
    # If document but not video, check mime type
    if not is_video and message.document:
        mime_type = message.document.mime_type or ""
        is_video = mime_type.startswith("video/")
    
    if not is_video:
        await message.reply_text(
            "⚠️ This doesn't appear to be a video file.\n"
            "Please send a video file to generate screenshots."
        )
        return
    
    # Get file details
    file_size = message.video.file_size if is_video else message.document.file_size
    duration = message.video.duration if is_video else None
    
    # Format file details
    file_info = f"📁 **File Analysis**\n\n"
    file_info += f"**File Name:** {file_name or 'Unknown'}\n"
    file_info += f"**File Size:** {humanize.naturalsize(file_size)}\n"
    
    if duration:
        minutes, seconds = divmod(duration, 60)
        file_info += f"**Duration:** {minutes}m {seconds}s\n"
    
    file_info += f"**File Type:** {'Video' if is_video else 'Document'}\n\n"
    file_info += "How many screenshots would you like? (1-10)"
    
    # Store file_id in user data for later use
    if not hasattr(client, 'user_data'):
        client.user_data = {}
    client.user_data[message.from_user.id] = {"file_id": file_id, "is_video": is_video}
    
    # Send file details and ask for number of screenshots
    await message.reply_text(file_info)


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help"]))
async def handle_screenshot_count(client, message):
    """Handle user input for number of screenshots"""
    # Get user data
    if not hasattr(client, 'user_data'):
        client.user_data = {}
    
    user_data = client.user_data.get(message.from_user.id)
    if not user_data or "file_id" not in user_data:
        await message.reply_text(
            "Please send a video file first before specifying the number of screenshots."
        )
        return
    
    # Parse number of screenshots
    try:
        num_screenshots = int(message.text.strip())
        if num_screenshots < 1 or num_screenshots > 10:
            raise ValueError("Number out of range")
    except ValueError:
        await message.reply_text(
            "Please enter a valid number between 1 and 10."
        )
        return
    
    # Initialize progress message
    progress_msg = await message.reply_text("Starting process...")
    progress_handler = ProgressMessage(progress_msg)
    
    try:
        # Update progress - Downloading
        await progress_handler.update("⬇️ Downloading video file...", animate=True)
        
        # Download the file
        file_id = user_data["file_id"]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            temp_path = temp_file.name
        
        await client.download_media(file_id, file_name=temp_path)
        await progress_handler.complete_step("✅ Video downloaded successfully")
        
        # Update progress - Generating screenshots
        await progress_handler.update("🖼️ Generating screenshots...", animate=True)
        
        # Extract screenshots
        async def update_screenshot_progress(current, total):
            percent = int((current / total) * 100)
            await progress_handler.update(f"🖼️ Generating screenshots... {percent}%", animate=False)
        
        screenshot_paths = await extract_screenshots(
            temp_path, 
            num_screenshots,
            progress_callback=update_screenshot_progress
        )
        
        await progress_handler.complete_step(f"✅ Generated {len(screenshot_paths)} screenshots")
        
        # Update progress - Uploading screenshots
        await progress_handler.update("📤 Uploading screenshots...", animate=True)
        
        # Send screenshots
        for i, screenshot_path in enumerate(screenshot_paths):
            await client.send_photo(
                message.chat.id,
                screenshot_path,
                caption=f"Screenshot {i+1}/{len(screenshot_paths)}"
            )
        
        await progress_handler.complete_step("✅ Screenshots uploaded successfully")
        
        # Final message
        await progress_handler.finish(
            f"✅ **Process completed!**\n\n"
            f"Successfully generated and sent {len(screenshot_paths)} screenshots."
        )
        
    except Exception as e:
        # Handle errors
        await progress_handler.finish(f"❌ Error: {str(e)}\n\nPlease try again with a different video.")
    finally:
        # Clean up temporary files
        try:
            if 'temp_path' in locals():
                os.unlink(temp_path)
            
            if 'screenshot_paths' in locals():
                for path in screenshot_paths:
                    if os.path.exists(path):
                        os.unlink(path)
                
                # Remove temp directory
                temp_dir = os.path.dirname(screenshot_paths[0]) if screenshot_paths else None
                if temp_dir and os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
        except Exception as e:
            print(f"Error cleaning up: {e}")


# Run the bot
if __name__ == "__main__":
    print("Starting Screenshot Generator Bot...")
    app.run()

