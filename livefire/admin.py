from django.contrib import admin
from .models import DayAssumption, Expense, MenuItem, QuoteRequest, Scenario, Snapshot, StaffingLine, VendorQuote

for model in (Scenario, DayAssumption, MenuItem, StaffingLine, Expense, QuoteRequest, VendorQuote, Snapshot):
    admin.site.register(model)
