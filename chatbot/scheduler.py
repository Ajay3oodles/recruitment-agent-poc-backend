from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from chatbot.tasks import reindex_cascade

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")

    scheduler.add_job(
        reindex_cascade,
        trigger=CronTrigger(hour=2, minute=0),  # Runs at 2:00 AM daily
        id="reindex_cascade",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()