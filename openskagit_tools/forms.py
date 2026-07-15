from django import forms

from .models import McpAccessRequest


class McpAccessRequestForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput, label="Leave blank")
    agreed_to_terms = forms.BooleanField(
        required=True,
        label="I will use the data responsibly and verify consequential decisions with official sources.",
    )

    class Meta:
        model = McpAccessRequest
        fields = ["name", "email", "organization", "agent_client", "intended_use", "expected_volume", "agreed_to_terms"]
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Your name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
            "organization": forms.TextInput(attrs={"autocomplete": "organization", "placeholder": "Organization (optional)"}),
            "agent_client": forms.TextInput(attrs={"placeholder": "Claude, ChatGPT, custom agent..."}),
            "intended_use": forms.Textarea(attrs={"rows": 5, "placeholder": "What would you like your agent to do with OpenSkagit?"}),
        }

    def clean_website(self) -> str:
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Unable to submit this request.")
        return value
