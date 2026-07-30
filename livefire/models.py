import secrets
from django.conf import settings
from django.db import models


class Scenario(models.Model):
    TAX_CHOICES = [("included", "Included in prices"), ("added", "Added at checkout")]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="livefire_scenarios")
    name = models.CharField(max_length=100)
    is_archived = models.BooleanField(default=False)
    traffic = models.PositiveIntegerField(default=10000)
    capture_rate = models.DecimalField(max_digits=6, decimal_places=4, default="0.10")
    operating_days = models.PositiveSmallIntegerField(default=20)
    hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=9)
    max_transactions_per_hour = models.PositiveIntegerField(default=150)
    sales_tax_rate = models.DecimalField(max_digits=6, decimal_places=4, default="0.087")
    sales_tax_treatment = models.CharField(max_length=10, choices=TAX_CHOICES, default="included")
    waste_rate = models.DecimalField(max_digits=6, decimal_places=4, default="0.05")
    card_rate = models.DecimalField(max_digits=6, decimal_places=4, default="0.029")
    card_fixed_fee = models.DecimalField(max_digits=6, decimal_places=2, default="0.30")
    fixed_costs = models.DecimalField(max_digits=12, decimal_places=2, default=22600)
    operating_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_archived", "name"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_livefire_scenario_name")]

    def __str__(self):
        return self.name


class DayAssumption(models.Model):
    DAYS = [("thu", "Thursday"), ("fri", "Friday"), ("sat", "Saturday"), ("sun", "Sunday")]
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="days")
    day = models.CharField(max_length=3, choices=DAYS)
    traffic = models.PositiveIntegerField(default=10000)
    capture_rate = models.DecimalField(max_digits=6, decimal_places=4, default="0.10")
    hours = models.DecimalField(max_digits=5, decimal_places=2, default=9)
    occurrences = models.PositiveSmallIntegerField(default=5)
    max_transactions_per_hour = models.PositiveIntegerField(default=150)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scenario", "day"], name="unique_livefire_scenario_day")]


class MenuItem(models.Model):
    CATEGORIES = [("entree", "Entrée"), ("addon", "Add-on")]
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="menu_items")
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=10, choices=CATEGORIES)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    food_cost = models.DecimalField(max_digits=8, decimal_places=2)
    packaging_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    purchase_rate = models.DecimalField(max_digits=6, decimal_places=4)
    vendor = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)

    @property
    def unit_contribution(self):
        return self.price - self.food_cost - self.packaging_cost

    @property
    def margin(self):
        return self.unit_contribution / self.price if self.price else 0


class StaffingLine(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="staffing")
    day = models.CharField(max_length=3, choices=DayAssumption.DAYS)
    position = models.CharField(max_length=100)
    employee_count = models.PositiveSmallIntegerField(default=1)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    wage = models.DecimalField(max_digits=8, decimal_places=2)
    payroll_burden = models.DecimalField(max_digits=6, decimal_places=4, default=0)

    @property
    def daily_cost(self):
        return self.employee_count * self.hours * self.wage * (1 + self.payroll_burden)


class Expense(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="expenses")
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)


class QuoteRequest(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item_name = models.CharField(max_length=150)
    vendor_name = models.CharField(max_length=150)
    vendor_email = models.EmailField(blank=True)
    requested_unit = models.CharField(max_length=50, default="each")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe, editable=False)
    expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VendorQuote(models.Model):
    request = models.ForeignKey(QuoteRequest, on_delete=models.CASCADE, related_name="quotes")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    package_size = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    available = models.BooleanField(default=True)
    expiration_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    preferred = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    @property
    def unit_cost(self):
        return (self.price + self.delivery_fee / self.minimum_order) / self.package_size if self.package_size and self.minimum_order else None


class Snapshot(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="snapshots")
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe, editable=False)
    title = models.CharField(max_length=150)
    data = models.JSONField()
    visible_sections = models.JSONField(default=list)
    published_at = models.DateTimeField(auto_now_add=True)
