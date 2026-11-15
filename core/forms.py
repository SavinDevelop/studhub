from allauth.account.forms import LoginForm as AllauthLoginForm
from allauth.account.forms import SignupForm as AllauthSignupForm


class LoginForm(AllauthLoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].label = "Електронна пошта"
        self.fields["login"].widget.attrs["placeholder"] = "student@example.com"
        self.fields["password"].widget.attrs["placeholder"] = "••••••••••"


class SignupForm(AllauthSignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Електронна пошта"
        self.fields["email"].widget.attrs["placeholder"] = "student@example.com"
        self.fields["password1"].widget.attrs["placeholder"] = "Мінімум 8 символів"
