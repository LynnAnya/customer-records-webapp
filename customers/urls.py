from django.urls import path
from django.views.generic import RedirectView

from customers import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="customer_list"), name="home"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/table/", views.customer_table, name="customer_table"),
    path("register/", views.register, name="register"),
    path("register/thanks/", views.register_thanks, name="register_thanks"),
]
