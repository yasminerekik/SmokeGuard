"""
Fire Detection System
A real-time fire detection and notification system using computer vision.
"""

#Il initialise le package Fire Detection System en exposant certaines classes et fonctions importantes au moment de l'importation.

from .config import Config, setup_logging
from .fire_detector import Detector
from .notification_service import NotificationService

__all__ = [
    'Config',
    'setup_logging',
    'Detector',
    'NotificationService',
]
