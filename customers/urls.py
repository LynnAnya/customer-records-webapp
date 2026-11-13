from django.urls import path

from customers import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/thanks/", views.register_thanks, name="register_thanks"),
]
