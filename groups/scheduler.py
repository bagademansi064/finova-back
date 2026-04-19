import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
from .models import Discussion, TradePoll
from market.tasks import sync_market_data, sync_market_fundamentals

logger = logging.getLogger(__name__)

def cleanup_expired_proposals():
    """Cancel POOLING/VOTING proposals that have expired due to insufficient funding."""
    now = timezone.now()
    
    # Check for POOLING proposals that passed expires_at
    expired_proposals = Discussion.objects.filter(
        status='pooling',
        expires_at__lt=now
    )
    
    count = expired_proposals.count()
    if count > 0:
        # We don't automatically refund here because the funds are in the pooled GroupWallet.
        # But we do close the proposal to free the group to propose something else.
        expired_proposals.update(status='cancelled')
        print(f"[Scheduler] Cancelled {count} unfunded expired proposals.")

def auto_resolve_polls():
    """Automatically resolve active polls that have passed their voting deadline."""
    now = timezone.now()
    expired_polls = TradePoll.objects.filter(
        status='active',
        voting_deadline__lt=now
    )
    
    count = expired_polls.count()
    if count > 0:
        for poll in expired_polls:
            poll.resolve()
        print(f"[Scheduler] Auto-resolved {count} expired trade polls.")

def start():
    scheduler = BackgroundScheduler()
    scheduler.add_jobstore(DjangoJobStore(), "default")
    
    scheduler.add_job(
        cleanup_expired_proposals,
        trigger=IntervalTrigger(minutes=1),  # Check every 1 minute
        id="cleanup_expired_proposals",
        max_instances=1,
        replace_existing=True,
    )
    
    scheduler.add_job(
        auto_resolve_polls,
        trigger=IntervalTrigger(seconds=30),  # Check every 30 seconds for quick trade execution
        id="auto_resolve_polls",
        max_instances=1,
        replace_existing=True,
    )
    
    scheduler.add_job(
        sync_market_data,
        trigger=IntervalTrigger(minutes=1),  # Sync Market every 1 minute
        id="sync_market_data",
        max_instances=1,
        replace_existing=True,
    )
    
    scheduler.add_job(
        sync_market_fundamentals,
        trigger=IntervalTrigger(hours=6),  # Heavy Pacer every 6 hours
        id="sync_market_fundamentals",
        max_instances=1,
        replace_existing=True,
    )
    
    try:
        scheduler.start()
        print("[Scheduler] Started background jobs.")
    except Exception as e:
        print(f"[Scheduler] Failed to start scheduler: {e}")
