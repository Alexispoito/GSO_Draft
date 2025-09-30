from django.contrib import admin
from .models import WorkAccomplishmentReport, SuccessIndicator, IPMTDraft, ActivityName


@admin.register(ActivityName)
class ActivityNameAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name", "keywords")
    list_filter = ("is_active",)


@admin.register(SuccessIndicator)
class SuccessIndicatorAdmin(admin.ModelAdmin):
    list_display = ("code", "unit", "description", "is_active")
    list_filter = ("unit", "is_active")
    search_fields = ("code", "description")


@admin.register(IPMTDraft)
class IPMTDraftAdmin(admin.ModelAdmin):
    list_display = ("personnel", "unit", "month", "indicator", "status")
    list_filter = ("unit", "month", "status")
    search_fields = ("personnel__username", "indicator__code")


@admin.register(WorkAccomplishmentReport)
class WorkAccomplishmentReportAdmin(admin.ModelAdmin):
    list_display = ("project_name", "unit", "date_started", "status", "total_cost")
    list_filter = ("unit", "status", "date_started")
    search_fields = ("project_name", "description")
