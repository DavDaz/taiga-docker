# Custom URL configuration for Railway deployment
from taiga.urls import *  # noqa
from django.conf import settings
from django.urls import path, include

# Grappelli related-lookup URLs (required for admin foreign key widgets)
urlpatterns = [path('grappelli/', include('grappelli.urls'))] + urlpatterns

# Only serve media locally if NOT using external storage (R2)
if not getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None):
    from django.urls import re_path
    from django.views.static import serve
    import mimetypes

    def secure_media_serve(request, path):
        """Serves media files with correct Content-Type detection."""
        response = serve(request, path, document_root=settings.MEDIA_ROOT)
        content_type, encoding = mimetypes.guess_type(path)
        if content_type:
            response['Content-Type'] = content_type
        return response

    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', secure_media_serve),
    ]
