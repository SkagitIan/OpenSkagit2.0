from django import forms
from .models import DayAssumption, Expense, MenuItem, QuoteRequest, Scenario, Snapshot, StaffingLine, VendorQuote


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "lf-input")


class ScenarioForm(StyledModelForm):
    class Meta:
        model = Scenario
        exclude = ("owner", "is_archived")

class DayForm(StyledModelForm):
    class Meta: model = DayAssumption; exclude = ("scenario",)

class MenuItemForm(StyledModelForm):
    class Meta: model = MenuItem; exclude = ("scenario",)

class StaffingForm(StyledModelForm):
    class Meta: model = StaffingLine; exclude = ("scenario",)

class ExpenseForm(StyledModelForm):
    class Meta: model = Expense; exclude = ("scenario",)

class QuoteRequestForm(StyledModelForm):
    class Meta: model = QuoteRequest; exclude = ("owner", "token", "created_at")

class VendorQuoteForm(StyledModelForm):
    class Meta: model = VendorQuote; exclude = ("request", "preferred", "submitted_at")

class SnapshotForm(forms.Form):
    title = forms.CharField(max_length=150)
    visible_sections = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=[(x, x.title()) for x in ("forecast", "menu", "staffing", "expenses", "capacity", "profit")], initial=["forecast", "menu", "staffing", "expenses", "capacity", "profit"])
