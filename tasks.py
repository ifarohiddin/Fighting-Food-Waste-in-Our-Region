from celery import Celery
import os

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))

@celery_app.task
def send_notification(user_id: str, message: str):
    # Hozircha oddiy print, Firebase keyin qo‘shiladi
    print(f"Notification to {user_id}: {message}")