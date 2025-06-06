#Permet de declarer les variables de .env et verifie les correspondences et aussi permet gerer les enregistrements des captures de detection 
import os
from dotenv import load_dotenv
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV = PROJECT_ROOT / '.env'
load_dotenv(ENV, override=True)


def setup_logging():
    log_dir = PROJECT_ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        filename=log_dir / 'fire_detection.log',
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)




class Config:
    RECEIVER_WHATSAPP_NUMBER = os.getenv('RECEIVER_WHATSAPP_NUMBER')
    IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')

    PROJECT_ROOT = Path(__file__).parent.parent
    MODEL_PATH = PROJECT_ROOT / 'models' / 'best_nano_111.pt'
    VIDEO_SOURCE = PROJECT_ROOT / 'data' / 'police_car_fire_ccvt.mp4'
    DETECTED_FIRES_DIR = PROJECT_ROOT / 'detected_fires'

    ALERT_COOLDOWN = 45  

    @classmethod
    def validate(cls):
        missing_vars = []
        for var in cls.__dict__:
            if not var.startswith('__') and getattr(cls, var) is None:
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"Missing environment variables: {', '.join(missing_vars)}")

        # Create necessary directories
        cls.DETECTED_FIRES_DIR.mkdir(exist_ok=True)

        if not cls.VIDEO_SOURCE.exists():
            raise FileNotFoundError(
                f"Video source missing: {cls.VIDEO_SOURCE}")
