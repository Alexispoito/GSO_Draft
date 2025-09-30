from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.gso_accounts.models import Unit, User
from apps.gso_requests.models import ServiceRequest

User = settings.AUTH_USER_MODEL


class ActivityName(models.Model):
    """
    Master list of standardized activity names.
    Used to auto-map ServiceRequest or WAR descriptions into activities.
    """
    name = models.CharField(max_length=255, unique=True)
    keywords = models.TextField(
        help_text="Comma-separated keywords to match against request description",
        blank=True
    )
    is_active = models.BooleanField(default=True)

    def keyword_list(self):
        return [kw.strip().lower() for kw in self.keywords.split(",") if kw.strip()]

    def __str__(self):
        return self.name


class SuccessIndicator(models.Model):
    """
    Success indicators per unit (IPMT basis).
    """
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    code = models.CharField(max_length=20)  # e.g., CF1, SF2
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.unit.name}"


class WorkAccomplishmentReport(models.Model):
    """
    Represents a Work Accomplishment Report (WAR), either migrated or live from ServiceRequest.
    """
    request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="war",
        null=True, blank=True
    )
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    assigned_personnel = models.ManyToManyField(
        User, related_name="war_personnel", blank=True
    )

    date_started = models.DateField()
    date_completed = models.DateField(null=True, blank=True)

    project_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=50,
        choices=[
            ("Pending", "Pending"),
            ("In Progress", "In Progress"),
            ("Completed", "Completed"),
        ],
        default="Completed",
    )

    material_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    control_number = models.CharField(max_length=100, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def generate_description(self):
        if self.description:
            return self.description
        if self.request:
            return f"WAR generated from request {self.request.id}: {self.request.description}"
        return f"WAR for project {self.project_name or 'N/A'}"

    def save(self, *args, **kwargs):
        self.total_cost = (self.material_cost or 0) + (self.labor_cost or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"WAR - {self.project_name or 'No Project'} ({self.unit.name})"


class IPMTDraft(models.Model):
    """
    Temporary or finalized IPMT report, tied to personnel and success indicators.
    """
    personnel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    month = models.CharField(max_length=20)  # e.g., "September 2025"
    indicator = models.ForeignKey(SuccessIndicator, on_delete=models.CASCADE)
    accomplishment = models.TextField(blank=True, null=True)  # AI/manual fill
    remarks = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=[("draft", "Draft"), ("final", "Finalized")],
        default="draft"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    reports = models.ManyToManyField(WorkAccomplishmentReport, blank=True)

    def __str__(self):
        return f"{self.personnel} - {self.month} - {self.indicator.code}"
