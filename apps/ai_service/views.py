# apps/ai_service/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import AIReportSummary
from apps.gso_reports.models import WorkAccomplishmentReport, IPMTDraft
from .tasks import generate_war_description_task, generate_ipmt_summary_task


@login_required
def ai_summary_list(request):
    """
    List all AI-generated summaries (for Director / GSO staff).
    """
    summaries = AIReportSummary.objects.select_related("report", "generated_by").all().order_by("-created_at")
    return render(request, "ai_service/ai_summary_list.html", {"summaries": summaries})


@login_required
def ai_summary_detail(request, report_id):
    """
    View AI-generated summaries for a specific Work Accomplishment Report (WAR).
    """
    report = get_object_or_404(WorkAccomplishmentReport, id=report_id)
    summaries = report.ai_summaries.all()
    return render(request, "ai_service/ai_summary_detail.html", {"report": report, "summaries": summaries})


@login_required
def generate_ai_summary(request, report_id):
    """
    Trigger Celery task to generate AI summary for a WAR.
    """
    report = get_object_or_404(WorkAccomplishmentReport, id=report_id)

    if request.method == "POST":
        generate_war_description_task.delay(report.id)  # async task
        messages.success(request, f"AI summary generation started for WAR #{report.id}.")
        return redirect("ai_service:ai_summary_detail", report_id=report.id)

    return render(request, "ai_service/generate_ai_summary.html", {"report": report})


@login_required
def generate_ipmt_ai_summary(request, ipmt_id):
    """
    Trigger Celery task to generate AI summary for an IPMT draft.
    """
    ipmt = get_object_or_404(IPMTDraft, id=ipmt_id)

    if request.method == "POST":
        generate_ipmt_summary_task.delay(ipmt.id)  # async task
        messages.success(request, f"AI summary generation started for IPMT draft #{ipmt.id}.")
        return redirect("gso_reports:ipmt_detail", ipmt_id=ipmt.id)

    return render(request, "ai_service/generate_ipmt_summary.html", {"ipmt": ipmt})
