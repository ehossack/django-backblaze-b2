from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from tests.test_project.files.models import Files


def index(request: HttpRequest) -> HttpResponse:
    class FileForm(ModelForm):  # noqa: DJ07
        class Meta:
            model = Files
            fields = "__all__"

    return render(
        request, "index.html", {"form": FileForm(instance=Files.objects.first())}
    )
