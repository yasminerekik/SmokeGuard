from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet
import json
import os
import requests
import cv2
import time
import logging
import asyncio
import telegram
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import quote_plus
from filelock import FileLock
from io import BytesIO


# Setup environment and logging
PROJECT_ROOT = Path(__file__).parent.parent
ENV = PROJECT_ROOT / '.env'
load_dotenv(ENV, override=True)
logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, config):
        """Initialize notification services"""
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.config = config
        # Create new event loop for this instance
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._init_services()

    def _init_services(self):
        """Initialize and validate notification providers"""
        # WhatsApp initialization
        if all([os.getenv("CALLMEBOT_API_KEY"), os.getenv("RECEIVER_WHATSAPP_NUMBER")]):
            self.whatsapp_enabled = True
            self.base_url = "https://api.callmebot.com/whatsapp.php"
            logger.info("WhatsApp service initialized")
        else:
            self.whatsapp_enabled = False
            logger.warning("WhatsApp alerts disabled: Missing credentials")

        # Telegram initialization
        if token := os.getenv("TELEGRAM_TOKEN"):
            try:
                self.telegram_bot = FlareGuardBot(
                    token, os.getenv("TELEGRAM_CHAT_ID"))
                # Run all async initialization together
                if not self.loop.is_running():
                    self.loop.run_until_complete(self._init_telegram())
            except Exception as e:
                logger.error(f"Telegram setup failed: {e}")
                self.telegram_bot = None
        else:
            logger.info("Telegram alerts disabled: Missing token")


    async def _init_telegram(self):
        """Async initialization for Telegram"""
        await self.telegram_bot.initialize()
        logger.info("Telegram service initialized")

    def save_frame(self, frame) -> Path:
        """Save detection frame with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = self.config.DETECTED_FIRES_DIR / f'alert_{timestamp}.jpg'
        cv2.imwrite(str(filename), frame)
        return filename

    def upload_image(self, image_path: Path) -> str:
        """Upload image to Imgur CDN"""
        try:
            response = requests.post(
                'https://api.imgur.com/3/upload',
                headers={
                    'Authorization': f'Client-ID {self.config.IMGUR_CLIENT_ID}'},
                files={'image': image_path.open('rb')},
                timeout=10
            )
            response.raise_for_status()
            return response.json()['data']['link']
        except Exception as e:
            logger.error(f"Image upload failed: {str(e)}")
            return None

    def send_alert(self, frame, detection: str = "Fire") -> bool:
        """Non-blocking alert dispatch"""
        image_path = self.save_frame(frame)

        # Submit to background thread
        future = self.executor.submit(
            self._send_alerts_async,
            image_path,
            detection
        )

        # Error logging callback
        future.add_done_callback(
            lambda f: f.exception() and logger.error(
                f"Alert error: {f.exception()}")
        )

        return True  # Immediate success assumption

    def _send_alerts_async(self, image_path, detection):
        """Background alert processing"""
        if self.whatsapp_enabled:
            self._send_whatsapp_alert(image_path, detection)
        if self.telegram_bot:
            self._send_telegram_alert(image_path, detection)

    def _send_whatsapp_alert(self, image_path, detection):
        """Handle WhatsApp notification flow"""
        image_url = self.upload_image(image_path)
        if not image_url:
            logger.error("WhatsApp alert skipped: Image upload failed")
            return False

        message = f"🚨 {detection} Detected! View at {image_url}"
        encoded_msg = quote_plus(message)
        url = f"{self.base_url}?" \
            f"phone={os.getenv('RECEIVER_WHATSAPP_NUMBER')}&" \
            f"text={encoded_msg}&" \
            f"apikey={os.getenv('CALLMEBOT_API_KEY')}"

        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            logger.info("WhatsApp alert delivered")
            return True
        logger.warning(
            f"WhatsApp Alert Attempt failed: HTTP {response.status_code}")
        return False

    def _send_telegram_alert(self, image_path, detection):
        """Handle Telegram notification with proper loop management"""
        try:
            if not self.loop.is_running():
                asyncio.set_event_loop(self.loop)
                return self.loop.run_until_complete(
                    self.telegram_bot.send_alert(
                        image_path=image_path,
                        caption=f"🚨 {detection} Detected!"
                    )
                )
        except Exception as e:
            logger.error(f"Telegram alert failed: {str(e)}")
            return False

    def send_test_message(self):
        """Verify system connectivity"""
        success = False
        if self.whatsapp_enabled:
            test_msg = "🔧 System Test: Fire Detection System Operational"
            success = self._send_callmebot_message(test_msg)
        if self.telegram_bot:
            try:
                test_image = Path(PROJECT_ROOT, 'data', "test_image.png")
                success |= self.loop.run_until_complete(
                    self.telegram_bot.send_test_alert(test_image))
            except Exception as e:
                logger.error(f"Telegram test failed: {e}")
                success = False
        return success

    def _send_callmebot_message(self, message: str) -> bool:
        """Core WhatsApp message sender"""
        encoded_msg = quote_plus(message)
        url = f"{self.base_url}?" \
            f"phone={os.getenv('RECEIVER_WHATSAPP_NUMBER')}&" \
            f"text={encoded_msg}&" \
            f"apikey={os.getenv('CALLMEBOT_API_KEY')}"

        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            logger.info("WhatsApp alert delivered")
            return True
        logger.warning(
            f"WhatsApp Alert Attempt failed: HTTP {response.status_code}")
        return False

    def cleanup(self):
        """Proper cleanup of resources"""
        try:
            self.executor.shutdown(wait=True)
            if hasattr(self, 'loop') and not self.loop.is_closed():
                # Cancel all pending tasks
                for task in asyncio.all_tasks(self.loop):
                    task.cancel()
                # Run loop one final time to complete cancellation
                self.loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(self.loop), return_exceptions=True))
                self.loop.close()
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

    def __del__(self):
        """Ensure cleanup is called"""
        self.cleanup()


class FlareGuardBot:
    def __init__(self, token: str, default_chat_id: str = None):
        self.logger = logging.getLogger(__name__)
        self.token = token
        self.default_chat_id = default_chat_id
        self.bot = telegram.Bot(token=self.token)
        self._init_crypto()
        self.storage_file = Path(__file__).parent / "sysdata.bin"
        self.update_file = Path(__file__).parent / "last_update.bin" 
        self.chat_ids = self._load_chat_ids()

    async def initialize(self):
        """Async initialization sequence"""
        await self._update_chat_ids()

    def _init_crypto(self):
        """Initialize encryption system"""
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise ValueError("ENCRYPTION_KEY environment variable required")
        self.cipher_suite = Fernet(key.encode())

    def _load_chat_ids(self):
        """Load encrypted chat IDs from secure storage with file locking"""
        try:
            if self.storage_file.exists():
                with FileLock(str(self.storage_file) + ".lock"):
                    self.storage_file.chmod(0o600)
                    with open(self.storage_file, "rb") as f:
                        encrypted_data = f.read()
                        decrypted = self.cipher_suite.decrypt(encrypted_data)
                        ids = json.loads(decrypted)
                        if not all(isinstance(i, int) for i in ids):
                            raise ValueError("Invalid chat ID format")
                        return list(set(ids))  # Remove duplicates
            return []
        except Exception as e:
            self.logger.error(f"Failed to load chat IDs: {e}")
            return []

    def _save_chat_ids(self):
        """Securely store chat IDs with encryption and file locking"""
        try:
            with FileLock(str(self.storage_file) + ".lock"):
                encrypted = self.cipher_suite.encrypt(
                    json.dumps(list(set(self.chat_ids))).encode()
                )
                with open(self.storage_file, "wb") as f:
                    f.write(encrypted)
                self.storage_file.chmod(0o600)
        except Exception as e:
            self.logger.error(f"Failed to save chat IDs: {e}")

    def _get_last_update_id(self):
        """Get the encrypted ID of the last processed update"""
        try:
            if self.update_file.exists():
                with FileLock(str(self.update_file) + ".lock"):
                    self.update_file.chmod(0o600)
                    with open(self.update_file, "rb") as f:
                        encrypted_data = f.read()
                        decrypted = self.cipher_suite.decrypt(encrypted_data)
                        return int(decrypted.decode())
        except Exception as e:
            self.logger.error(f"Failed to read last update ID: {e}")
        return 0

    def _save_last_update_id(self, update_id: int):
        """Save the encrypted ID of the last processed update"""
        try:
            with FileLock(str(self.update_file) + ".lock"):
                encrypted = self.cipher_suite.encrypt(str(update_id).encode())
                with open(self.update_file, "wb") as f:
                    f.write(encrypted)
                self.update_file.chmod(0o600)
        except Exception as e:
            self.logger.error(f"Failed to save last update ID: {e}")

    async def _update_chat_ids(self):
        """Discover and store new chat IDs securely with offset handling"""
        try:
            offset = self._get_last_update_id()
            updates = await self.bot.get_updates(offset=offset + 1, timeout=30)

            new_ids = []
            for update in updates:
                if update.message and update.message.chat_id:
                    chat_id = update.message.chat_id
                    if chat_id not in self.chat_ids:
                        new_ids.append(chat_id)
                        self.chat_ids.append(chat_id)
                        self.logger.info(f"New chat ID registered: {chat_id}")

                # Update the offset to the latest processed update
                if update.update_id >= offset:
                    offset = update.update_id
                    self._save_last_update_id(offset)

            if new_ids:
                self._save_chat_ids()
                self.logger.info(f"Saved {len(new_ids)} new chat IDs")
        except Exception as e:
            self.logger.error(f"Chat ID update failed: {e}")

    async def _verify_chat_id(self, chat_id: int) -> bool:
        """Verify if a chat ID is still valid"""
        try:
            await self.bot.send_chat_action(chat_id=chat_id, action="typing")
            return True
        except telegram.error.Unauthorized:
            return False
        except Exception:
            # For other errors, assume the chat is still valid
            return True

    async def cleanup_invalid_chats(self):
        """Remove invalid chat IDs from storage"""
        invalid_ids = []
        for chat_id in self.chat_ids:
            if not await self._verify_chat_id(chat_id):
                invalid_ids.append(chat_id)
                self.logger.info(f"Removing invalid chat ID: {chat_id}")

        if invalid_ids:
            self.chat_ids = [
                id for id in self.chat_ids if id not in invalid_ids]
            self._save_chat_ids()

    async def send_alert(self, image_path: Path, caption: str) -> bool:
        """Send alert to all registered chats with retry logic and invalid chat cleanup"""
        if not image_path.exists():
            self.logger.error(f"Alert image missing: {image_path}")
            return False

        overall_success = False
        failed_chats = []

        # Read image data once
        with open(image_path, 'rb') as f:
            image_data = f.read()

        try:
            for chat_id in self.chat_ids:
                sent = False
                for attempt in range(3):
                    try:
                        # Create new BytesIO for each send attempt
                        photo = BytesIO(image_data)
                        photo.name = 'image.jpg'  # Telegram requires a name

                        async with self.bot:  # Create new session for each chat
                            await self.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo,
                                caption=caption,
                                parse_mode='Markdown',
                                pool_timeout=20
                            )
                        self.logger.info(
                            f"Alert sent to Telegram chat {chat_id}")
                        sent = True
                        overall_success = True
                        break
                    except telegram.error.Unauthorized:
                        self.logger.warning(f"Unauthorized for chat {chat_id}")
                        failed_chats.append(chat_id)
                        break
                    except telegram.error.TimedOut:
                        await asyncio.sleep(2 ** attempt)
                        self.logger.warning(
                            f"Timeout sending to {chat_id}, retry {attempt+1}/3")
                    except telegram.error.NetworkError:
                        await asyncio.sleep(5)
                        self.logger.warning(
                            f"Network error with {chat_id}, retry {attempt+1}/3")
                    except Exception as e:
                        self.logger.error(
                            f"Failed to send to {chat_id}: {str(e)}")
                        if attempt == 2:  # Only add to failed chats after all retries
                            failed_chats.append(chat_id)
                        break

                if not sent:
                    failed_chats.append(chat_id)

            # Clean up invalid chats after sending alerts
            if failed_chats:
                self.chat_ids = [
                    id for id in self.chat_ids if id not in failed_chats]
                self._save_chat_ids()
                self.logger.info(
                    f"Removed {len(failed_chats)} invalid chat IDs")

        except Exception as e:
            self.logger.error(f"Telegram error: {str(e)}")

        return overall_success

    async def send_test_alert(self, test_image: Path):
        """Special method for test alerts"""
        return await self.send_alert(test_image, "🔧 System Test: Service Operational")
