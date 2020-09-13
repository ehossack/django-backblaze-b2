from django.urls import path

from tests.test_project.files import views

urlpatterns = [
    path("", views.index, name="index"),
]
