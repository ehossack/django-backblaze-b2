from typing import Optional, cast

from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import ModelWithFiles  # type: ignore


def index(request: HttpRequest) -> HttpResponse:
    class FileForm(ModelForm):  # noqa: DJ07
        class Meta:
            model = ModelWithFiles
            fields = "__all__"

    model_instance: Optional[ModelWithFiles] = ModelWithFiles.objects.first()

    if request.method == "POST":
        form = FileForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            model_instance = cast(ModelWithFiles, form.instance)
            model_instance.refresh_from_db()
            form = FileForm(instance=model_instance)
    else:
        form = FileForm(instance=model_instance)

    return render(request, "index.html", {"form": form})
