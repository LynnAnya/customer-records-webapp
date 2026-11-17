from django.urls import path
from django.views.generic import RedirectView

from customers import views, views_admin

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="customer_list"), name="home"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/table/", views.customer_table, name="customer_table"),
    path(
        "customers/share-text/", views.customer_share_text, name="customer_share_text"
    ),
    path("customers/pdf/", views.customer_pdf, name="customer_pdf"),
    # Admin only
    path("customers/new/", views_admin.customer_create, name="customer_create"),
    path(
        "customers/hide/", views_admin.customer_set_hidden, name="customer_set_hidden"
    ),
    path(
        "customers/delete/",
        views_admin.customer_bulk_delete,
        name="customer_bulk_delete",
    ),
    path("customers/<int:pk>/edit/", views_admin.customer_edit, name="customer_edit"),
    path(
        "customers/<int:pk>/delete/",
        views_admin.customer_delete,
        name="customer_delete",
    ),
    # Public
    path("register/", views.register, name="register"),
    path("register/thanks/", views.register_thanks, name="register_thanks"),
]
