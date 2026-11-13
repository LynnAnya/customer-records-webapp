from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

urlpatterns = [
    path(
        "login/",
        LoginView.as_view(
            template_name="accounts/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    # LogoutView only accepts POST.
    path("logout/", LogoutView.as_view(), name="logout"),
]
