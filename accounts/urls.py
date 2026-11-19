from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from accounts import views, views_staff

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
    path("account/", views.account, name="account"),
    path("account/password/", views.password_change, name="password_change"),
    path("account/theme/", views.set_theme, name="set_theme"),
    # Admin only
    path("staff/", views_staff.staff_list, name="staff_list"),
    path("staff/new/", views_staff.staff_create, name="staff_create"),
    path("staff/<int:pk>/edit/", views_staff.staff_edit, name="staff_edit"),
    path(
        "staff/<int:pk>/password/",
        views_staff.staff_reset_password,
        name="staff_reset_password",
    ),
    path(
        "staff/<int:pk>/active/", views_staff.staff_set_active, name="staff_set_active"
    ),
]
