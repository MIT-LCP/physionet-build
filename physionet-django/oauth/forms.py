from django import forms
from django.conf import settings

from oauth.models import Partner


class PartnerCreateForm(forms.Form):
    organization_name = forms.CharField(max_length=200)
    contact_name = forms.CharField(max_length=200, required=False)
    contact_email = forms.EmailField(required=False)
    agreement_signed_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    redirect_uris = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One URI per line.",
    )
    post_logout_redirect_uris = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        help_text="One URI per line. Optional.",
    )
    allowed_scopes = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=[],
        required=False,
    )
    requires_pkce = forms.BooleanField(
        required=False,
        initial=True,
        label="Require PKCE",
        help_text=(
            "Require PKCE (code_challenge) on /authorize. Disable only when "
            "the partner cannot send a code_challenge (e.g. an upstream "
            "federator acting as the OAuth client)."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowed_scopes"].choices = [
            (k, f"{k} - {v}") for k, v in settings.OAUTH2_PROVIDER["SCOPES"].items()
        ]
        if not self.is_bound:
            self.initial["allowed_scopes"] = ["openid", "profile", "email"]

    def clean_redirect_uris(self):
        raw = self.cleaned_data["redirect_uris"]
        uris = [line.strip() for line in raw.splitlines() if line.strip()]
        if not uris:
            raise forms.ValidationError("At least one redirect URI is required.")
        for uri in uris:
            if not (uri.startswith("http://") or uri.startswith("https://")):
                raise forms.ValidationError(f"{uri!r} must be http:// or https://")
        return " ".join(uris)

    def clean_post_logout_redirect_uris(self):
        raw = self.cleaned_data["post_logout_redirect_uris"]
        uris = [line.strip() for line in raw.splitlines() if line.strip()]
        for uri in uris:
            if not (uri.startswith("http://") or uri.startswith("https://")):
                raise forms.ValidationError(f"{uri!r} must be http:// or https://")
        return " ".join(uris)


class PartnerEditForm(forms.ModelForm):
    class Meta:
        model = Partner
        fields = (
            "organization_name", "contact_name", "contact_email",
            "agreement_signed_date", "requires_pkce",
        )
        widgets = {
            "agreement_signed_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "requires_pkce": (
                "Require PKCE (code_challenge) on /authorize. Disable only when "
                "the partner cannot send a code_challenge (e.g. an upstream "
                "federator acting as the OAuth client)."
            ),
        }


class PartnerScopesForm(forms.ModelForm):
    allowed_scopes = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        choices=[],
        required=False,
    )

    class Meta:
        model = Partner
        fields = ("allowed_scopes",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowed_scopes"].choices = [
            (k, f"{k} - {v}") for k, v in settings.OAUTH2_PROVIDER["SCOPES"].items()
        ]


class PartnerRedirectURIsForm(forms.Form):
    redirect_uris = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    post_logout_redirect_uris = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def clean_redirect_uris(self):
        raw = self.cleaned_data["redirect_uris"]
        uris = [line.strip() for line in raw.splitlines() if line.strip()]
        if not uris:
            raise forms.ValidationError("At least one redirect URI is required.")
        for uri in uris:
            if not (uri.startswith("http://") or uri.startswith("https://")):
                raise forms.ValidationError(f"{uri!r} must be http:// or https://")
        return " ".join(uris)

    def clean_post_logout_redirect_uris(self):
        raw = self.cleaned_data["post_logout_redirect_uris"]
        uris = [line.strip() for line in raw.splitlines() if line.strip()]
        for uri in uris:
            if not (uri.startswith("http://") or uri.startswith("https://")):
                raise forms.ValidationError(f"{uri!r} must be http:// or https://")
        return " ".join(uris)


class PartnerSuspendForm(forms.Form):
    status_reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    revoke_active_tokens = forms.BooleanField(required=False, initial=False)
