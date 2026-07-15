import sys
import os

# Explicitly add the /backend folder to the Python path so app_factory resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_factory import create_app

app = create_app()