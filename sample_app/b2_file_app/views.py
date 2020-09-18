from typing import Optional

from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import ModelWithFiles  # type: ignore


def index(request: HttpRequest) -> HttpResponse:
    class FileForm(ModelForm):  # noqa: DJ07
        class Meta:
            model = ModelWithFiles
            fields = "__all__"

    modelInstance: Optional[ModelWithFiles] = ModelWithFiles.objects.first()

    if request.method == "POST":
        form = FileForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            modelInstance = form.instance
            modelInstance.refresh_from_db()
            form = FileForm(instance=modelInstance)
    else:
        form = FileForm(instance=modelInstance)

    return render(request, "index.html", {"form": form})
