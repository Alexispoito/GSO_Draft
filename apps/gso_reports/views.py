# apps/gso_reports/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse

from apps.gso_requests.models import ServiceRequest
from apps.gso_accounts.models import User, Unit
from .models import WorkAccomplishmentReport, SuccessIndicator, IPMT
from .utils import normalize_report, generate_ipmt_excel, collect_ipmt_reports
from apps.ai_service.utils import generate_war_description


# -------------------------------
# Role Checks
# -------------------------------
def is_gso_or_director(user):
    return user.is_authenticated and user.role in ["gso", "director"]


# -------------------------------
# Accomplishment Report View
# -------------------------------
@login_required
@user_passes_test(is_gso_or_director)
def accomplishment_report(request):
    # Fetch completed requests
    completed_requests = ServiceRequest.objects.filter(status="Completed").order_by("-created_at")
    # Fetch all WARs
    all_wars = WorkAccomplishmentReport.objects.select_related("request", "unit").prefetch_related("assigned_personnel").all().order_by("-date_started")

    reports = []

    # Track which requests already have a WAR
    war_request_ids = set(war.request_id for war in all_wars if war.request_id)

    # Process completed requests that **don't yet have a WAR**
    for r in completed_requests:
        if r.id in war_request_ids:
            continue
        norm = normalize_report(r)
        norm["id"] = r.id

        if not norm.get("description") or norm["description"].strip() == "":
            try:
                desc = generate_war_description(
                    activity_name=getattr(r, "activity_name", getattr(r, "title", "Task")),
                    unit=getattr(r.unit, "name", None),
                    personnel_names=[p.get_full_name() for p in r.assigned_personnel.all()] if hasattr(r, "assigned_personnel") else None
                )
                r.description = desc or "No description generated."
                r.save(update_fields=["description"])
                norm["description"] = r.description
            except Exception as e:
                norm["description"] = f"Error generating description: {e}"

        reports.append(norm)

    # Process all WARs
    for war in all_wars:
        norm = normalize_report(war)
        norm["id"] = war.id

        if not norm.get("description") or norm["description"].strip() == "":
            try:
                desc = generate_war_description(
                    activity_name=getattr(war, "activity_name", getattr(war, "title", "Task")),
                    unit=getattr(war.unit, "name", None),
                    personnel_names=[p.get_full_name() for p in war.assigned_personnel.all()] if hasattr(war, "assigned_personnel") else None
                )
                war.description = desc or "No description generated."
                war.save(update_fields=["description"])
                norm["description"] = war.description
            except Exception as e:
                norm["description"] = f"Error generating description: {e}"

        reports.append(norm)

    # Apply search and unit filters
    search_query = request.GET.get("q")
    if search_query:
        reports = [r for r in reports if search_query.lower() in str(r).lower()]

    unit_filter = request.GET.get("unit")
    if unit_filter:
        reports = [r for r in reports if r["unit"].lower() == unit_filter.lower()]

    reports.sort(key=lambda r: r["date"], reverse=True)

    # Load all active personnel for IPMT modal
    personnel_qs = User.objects.filter(role="personnel", account_status="active") \
        .select_related('unit').order_by('unit__name', 'first_name')

    personnel_list = [
        {
            "full_name": u.get_full_name() or u.username,
            "username": u.username,
            "unit": u.unit.name.lower() if u.unit else "unassigned"
        }
        for u in personnel_qs
    ]

    return render(
        request,
        "gso_office/accomplishment_report/accomplishment_report.html",
        {
            "reports": reports,
            "personnel_list": personnel_list,
        },
    )


# -------------------------------
# Generate IPMT Excel
# -------------------------------
@login_required
@user_passes_test(is_gso_or_director)
def generate_ipmt(request):
    month_filter = request.GET.get("month")
    unit_filter = request.GET.get("unit", "all")
    personnel_names = request.GET.getlist("personnel")

    if not month_filter:
        return HttpResponse("Month is required in 'YYYY-MM' format.", status=400)

    try:
        wb = generate_ipmt_excel(month_filter, unit_name=unit_filter, personnel_names=personnel_names)
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    filename = f"IPMT_{unit_filter}_{month_filter}.xlsx"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


# -------------------------------
# Get WAR Description (AJAX)
# -------------------------------
@login_required
@user_passes_test(is_gso_or_director)
def get_war_description(request, war_id):
    try:
        war = WorkAccomplishmentReport.objects.get(id=war_id)
        return JsonResponse({'description': war.description or ""})
    except WorkAccomplishmentReport.DoesNotExist:
        return JsonResponse({'error': 'WAR not found'}, status=404)


# -------------------------------
# Preview IPMT (Web)
# -------------------------------
@login_required
@user_passes_test(is_gso_or_director)
def preview_ipmt(request):
    month_filter = request.GET.get("month")
    unit_filter = request.GET.get("unit", "all")
    personnel_names = request.GET.getlist("personnel[]") or []

    if not month_filter:
        return HttpResponse("Month is required in 'YYYY-MM' format.", status=400)

    try:
        year, month_num = map(int, month_filter.split("-"))
    except ValueError:
        return HttpResponse("Invalid month format. Use YYYY-MM.", status=400)

    # Get selected unit object
    unit = None
    if unit_filter.lower() != "all":
        unit = Unit.objects.filter(name__iexact=unit_filter).first()

    # Fetch all indicators for this unit (or all units)
    indicators = SuccessIndicator.objects.filter(unit=unit) if unit else SuccessIndicator.objects.all()

    reports = []
    for indicator in indicators:
        # For each indicator, fetch WARs for selected personnel & month
        wars = WorkAccomplishmentReport.objects.filter(
            unit=unit,
            activity_name=indicator.activity_name,
            date_started__year=year,
            date_started__month=month_num,
        )
        if personnel_names:
            wars = wars.filter(assigned_personnel__first_name__in=[p.split()[0] for p in personnel_names])

        description = " / ".join([w.description for w in wars if w.description]) or ""
        remarks = ""  # can generate default remarks if needed

        reports.append({
            "indicator": indicator.code,
            "description": description,
            "remarks": remarks,
            "war_ids": [w.id for w in wars],
        })

    context = {
        "reports": reports,
        "month_filter": month_filter,
        "unit_filter": unit_filter,
        "personnel_names": personnel_names,
    }

    return render(request, "gso_office/ipmt/ipmt_preview.html", context)
# -------------------------------
# Save IPMT (after editing in preview)
# -------------------------------
@login_required
@user_passes_test(is_gso_or_director)
def save_ipmt(request):
    import json
    from apps.gso_accounts.models import User, Unit
    from .models import IPMT, SuccessIndicator, WorkAccomplishmentReport
    from .utils import generate_ipmt_summary

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    month = data.get("month")
    unit_name = data.get("unit")
    personnel_names = data.get("personnel", [])
    rows = data.get("rows", [])

    if not month or not unit_name or not personnel_names or not rows:
        return JsonResponse({"error": "Missing required data"}, status=400)

    unit = Unit.objects.filter(name__iexact=unit_name).first()
    if not unit:
        return JsonResponse({"error": f"Unit '{unit_name}' not found"}, status=404)

    for person_name in personnel_names:
        user = (
            User.objects.filter(first_name__iexact=person_name.split()[0]).first()
            or User.objects.filter(username__iexact=person_name).first()
        )
        if not user:
            continue

        for row in rows:
            indicator = SuccessIndicator.objects.filter(unit=unit, code=row["indicator"]).first()
            if not indicator:
                continue

            # Use correct activity_name mapping
            war_ids = row.get("war_ids", [])
            wars = WorkAccomplishmentReport.objects.filter(
                id__in=war_ids,
                assigned_personnel=user,
                activity_name=indicator.activity_name
            )

            accomplishment = row.get("description") or row.get("accomplishment") or ""
            if not accomplishment and wars.exists():
                war_descriptions = [w.description for w in wars if w.description]
                if war_descriptions:
                    accomplishment = generate_ipmt_summary(indicator.code, war_descriptions)

            remarks = row.get("remarks") or accomplishment

            ipmt_obj, created = IPMT.objects.update_or_create(
                personnel=user,
                unit=unit,
                month=month,
                indicator=indicator,
                defaults={
                    "accomplishment": accomplishment,
                    "remarks": remarks,
                }
            )

            ipmt_obj.reports.set(wars)

    return JsonResponse({"status": "success"})