# apps/ai_service/tasks.py
from celery import shared_task
from apps.gso_reports.models import WorkAccomplishmentReport
from .utils import generate_war_description, generate_ipmt_summary


@shared_task
def generate_war_description_task(war_id):
    """
    Celery task: Generate and save an AI description for a Work Accomplishment Report (WAR).
    """
    try:
        war = WorkAccomplishmentReport.objects.get(id=war_id)
        personnel_names = [p.get_full_name() or p.username for p in war.assigned_personnel.all()]

        description = generate_war_description(
            activity_name=war.activity_name,
            unit=war.unit.name if war.unit else "",
            personnel_names=personnel_names,
        )

        war.description = description
        war.save()
        return f"Description generated for WAR {war.id}"

    except WorkAccomplishmentReport.DoesNotExist:
        return f"WAR {war_id} not found"


@shared_task
def generate_ipmt_summary_task(ipmt_id):
    """
    Celery task: Generate and save an AI-based IPMT summary for all linked WARs.
    """
    from apps.gso_reports.models import IPMTDraft  # avoid circular import

    try:
        ipmt = IPMTDraft.objects.get(id=ipmt_id)
        war_descriptions = [war.description or war.activity_name for war in ipmt.reports.all()]

        summary = generate_ipmt_summary(war_descriptions)
        ipmt.accomplishment = summary
        ipmt.save()
        return f"IPMT summary generated for draft {ipmt.id}"

    except IPMTDraft.DoesNotExist:
        return f"IPMT draft {ipmt_id} not found"