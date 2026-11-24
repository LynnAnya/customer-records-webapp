from django.urls import path
from django.views.generic import RedirectView

from customers import views, views_admin, views_import

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
    path("customers/import/", views_import.customer_import, name="customer_import"),
    path(
        "customers/import/check/",
        views_import.customer_import_check,
        name="customer_import_check",
    ),
    path(
        "customers/import/confirm/",
        views_import.customer_import_confirm,
        name="customer_import_confirm",
    ),
    path(
        "customers/import/done/",
        views_import.customer_import_done,
        name="customer_import_done",
    ),
    path(
        "customers/import/template.xlsx",
        views_import.customer_import_template,
        name="customer_import_template",
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
