"""Celery app and beat schedule (UTC). Task bodies land in later milestones."""

from celery import Celery

from app.settings import get_settings

settings = get_settings()

celery = Celery("rjf", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(timezone="UTC", enable_utc=True, task_acks_late=True)
