# Custom URL configuration for Railway deployment
# Adds media file serving since there's no shared volume with nginx

from taiga.urls import *  # noqa
from django.urls import re_path
from django.views.static import serve
from django.conf import settings

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
