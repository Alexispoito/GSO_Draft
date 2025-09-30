# apps/gso_reports/utils.py
from django.utils import timezone
from datetime import datetime
from apps.gso_requests.models import ServiceRequest
from .models import WorkAccomplishmentReport, ActivityName, SuccessIndicator, IPMTDraft
import io
import calendar
import pandas as pd


# -------------------------------
# Normalize Reports (for Accomplishment Report)
# -------------------------------
def normalize_report(obj):
    if isinstance(obj, ServiceRequest):
        assigned = obj.assigned_personnel.all()
        personnel_list = [p.get_full_name() or p.username for p in assigned] if assigned.exists() else ["Unassigned"]

        return {
            "type": "ServiceRequest",
            "source": "Live",
            "requesting_office": obj.department.name if obj.department else "",
            "description": obj.description,
            "unit": obj.unit.name if obj.unit else "",
            "date": obj.created_at,
            "personnel": personnel_list,
            "status": obj.status,
            "rating": getattr(obj, "rating", None),
        }

    elif isinstance(obj, WorkAccomplishmentReport):
        date_value = obj.date_started
        if isinstance(date_value, datetime) and timezone.is_naive(date_value):
            date_value = timezone.make_aware(date_value)
        elif not isinstance(date_value, datetime):
            date_value = timezone.make_aware(datetime.combine(date_value, datetime.min.time()))

        assigned = obj.assigned_personnel.all()
        personnel_list = [p.get_full_name() or p.username for p in assigned] if assigned.exists() else ["Unassigned"]

        return {
            "type": "WorkAccomplishmentReport",
            "source": "Live" if obj.request else "Migrated",
            "requesting_office": obj.request.department.name if obj.request and obj.request.department else getattr(obj, "requesting_office", ""),
            "description": obj.description,
            "unit": obj.request.unit.name if obj.request and obj.request.unit else (obj.unit.name if obj.unit else ""),
            "date": date_value,
            "personnel": personnel_list,
            "status": obj.status or "Completed",
            "rating": getattr(obj, "rating", None),
        }


# -------------------------------
# Activity Name Mapper
# -------------------------------
def map_activity_name(description: str):
    if not description:
        return ActivityName.objects.filter(name="Miscellaneous").first()

    description = description.lower()

    for activity in ActivityName.objects.all():
        if any(kw in description for kw in activity.keyword_list()):
            return activity

    return ActivityName.objects.filter(name="Miscellaneous").first()


def map_activity_name_from_reports(service_request):
    task_reports_text = " ".join([t.report_text for t in service_request.reports.all()])
    return map_activity_name(task_reports_text) or map_activity_name(service_request.description)


# -------------------------------
# Collect IPMT Reports (Indicator → Accomplishment → Remarks)
# -------------------------------
def collect_ipmt_reports(year: int, month_num: int, unit_name: str = None, personnel_names: list = None):
    """
    Collect IPMT preview rows:
    - All active SuccessIndicators for the unit
    - Prefill Actual Accomplishments from WAR AI description if available
    - Prefill Remarks from IPMTDraft if exists
    Returns a list of dicts:
    {
        "indicator": str,
        "description": str,
        "remarks": str,
        "war_id": int or None
    }
    """
    reports = []

    # 1. Get the unit
    from apps.gso_accounts.models import Unit
    try:
        unit = Unit.objects.get(name__iexact=unit_name)
    except Unit.DoesNotExist:
        return []

    # 2. Get all active SuccessIndicators for this unit
    indicators = SuccessIndicator.objects.filter(unit=unit, is_active=True)

    # 3. Filter WARs for this unit and month
    wars = WorkAccomplishmentReport.objects.filter(
        unit=unit,
        date_started__year=year,
        date_started__month=month_num,
    ).prefetch_related("assigned_personnel")

    # 4. Optionally filter by personnel
    if personnel_names and "all" not in [p.lower() for p in personnel_names]:
        wars = wars.filter(
            assigned_personnel__first_name__in=[p.split()[0] for p in personnel_names]
        )

    # 5. Build report rows
    for indicator in indicators:
        # Find a WAR that matches this indicator (simple keyword match)
        matched_war = None
        for war in wars:
            if indicator.description.lower() in (war.description or "").lower():
                matched_war = war
                break

        # Prefill description from WAR AI description if exists
        description = matched_war.description if matched_war else ""

        # Prefill remarks from IPMTDraft if exists
        ipmt_draft = IPMTDraft.objects.filter(
            indicator=indicator,
            unit=unit,
            month=f"{year}-{month_num:02d}"
        ).first()
        remarks = ipmt_draft.remarks if ipmt_draft else ""

        reports.append({
            "indicator": indicator.code,
            "description": description,
            "remarks": remarks,
            "war_id": matched_war.id if matched_war else None,
        })

    return reports
# -------------------------------
# Generate IPMT Excel
# -------------------------------
def generate_ipmt_excel(month_filter: str, unit_name: str = None, personnel_names: list = None):
    """
    Generate an Excel file for IPMT reports.
    - One sheet per personnel
    - Columns: Indicator, Accomplishment, Remarks
    """
    try:
        year, month_num = map(int, month_filter.split("-"))  # expects "YYYY-MM"
    except ValueError:
        raise ValueError("Month filter must be in 'YYYY-MM' format.")

    if not personnel_names or "all" in [p.lower() for p in personnel_names]:
        # Get all unique personnel with WARs this month
        personnel_names = set()
        wars = WorkAccomplishmentReport.objects.filter(
            date_started__year=year,
            date_started__month=month_num,
        )
        if unit_name and unit_name.lower() != "all":
            wars = wars.filter(unit__name__iexact=unit_name)
        for war in wars:
            for p in war.assigned_personnel.all():
                personnel_names.add(p.get_full_name() or p.username)
        personnel_names = list(personnel_names)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        for person in personnel_names:
            reports = collect_ipmt_reports(year, month_num, unit_name, [person])
            df = pd.DataFrame(reports)

            if df.empty:
                df = pd.DataFrame([{"indicator": "N/A", "description": "No reports", "remarks": ""}])

            # Match your sample format: Indicator → Accomplishment → Remarks
            df = df.rename(columns={
                "indicator": "Success Indicator",
                "description": "Accomplishment",
                "remarks": "Remarks"
            })

            sheet_title = (person[:30] if len(person) > 30 else person) or "Unassigned"
            df.to_excel(writer, index=False, sheet_name=sheet_title)

            worksheet = writer.sheets[sheet_title]
            worksheet.write(0, 4, f"Month: {calendar.month_name[month_num]} {year}")
            worksheet.write(1, 4, f"Personnel: {person}")
            if unit_name:
                worksheet.write(2, 4, f"Unit: {unit_name}")

    buffer.seek(0)

    from openpyxl import load_workbook
    wb = load_workbook(buffer)

    return wb
