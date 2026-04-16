import io
import logging

from django.apps import AppConfig

log = logging.getLogger(__name__)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


def _cache_attachment_content(sender, instance, **kwargs):
    """Cache file content in memory before it's committed to S3/R2.

    post_save would require re-downloading the file from R2 (slow, can cause
    gunicorn worker timeout). Instead, we read the file here while it's still
    a local upload object, and stash it on the instance.
    """
    name = getattr(instance.attached_file, 'name', None)
    if not name:
        return
    if not any(name.lower().endswith(ext) for ext in IMAGE_EXTS):
        return

    try:
        f = instance.attached_file
        # TemporaryUploadedFile / InMemoryUploadedFile — still local at this point.
        if hasattr(f, 'file') and hasattr(f.file, 'read'):
            f.file.seek(0)
            instance._cached_image_content = f.file.read()
            f.file.seek(0)
        elif hasattr(f, 'read'):
            pos = f.tell() if hasattr(f, 'tell') else 0
            f.seek(0)
            instance._cached_image_content = f.read()
            f.seek(0)
    except Exception:
        log.warning("Could not cache attachment content for thumbnail", exc_info=True)


def _generate_attachment_thumbnail(sender, instance, created, **kwargs):
    """Generate a 300x200 crop thumbnail and upload it to S3/R2.

    Taiga computes the thumbnail_card_url as ``<original>.300x200_q85_crop.jpg``
    but does not upload that file when DEFAULT_FILE_STORAGE is S3.
    This signal fills the gap.
    """
    if not created:
        return

    name = getattr(instance.attached_file, 'name', None)
    if not name:
        return

    if not any(name.lower().endswith(ext) for ext in IMAGE_EXTS):
        return

    try:
        from PIL import Image, ImageOps
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        # Use cached content from pre_save to avoid a round-trip to R2.
        content = getattr(instance, '_cached_image_content', None)
        if content is None:
            # Fallback: read from storage (slower, risks timeout on large files).
            log.warning("No cached content for %s — falling back to R2 read", name)
            with instance.attached_file.open('rb') as fh:
                content = fh.read()

        img = Image.open(io.BytesIO(content))
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # Pillow < 10

        # Crop-to-fit at 300x200, quality 85 — matches Taiga's naming convention.
        thumb = ImageOps.fit(img, (300, 200), resample)
        buf = io.BytesIO()
        thumb.save(buf, format='JPEG', quality=85)

        thumb_name = f"{name}.300x200_q85_crop.jpg"
        default_storage.save(thumb_name, ContentFile(buf.getvalue()))
        log.info("Thumbnail uploaded: %s", thumb_name)

    except Exception:
        log.warning(
            "Thumbnail generation failed for %s", name, exc_info=True
        )


class TaigaRailwayConfig(AppConfig):
    name = 'taiga_railway'
    verbose_name = 'Taiga Railway Overrides'

    def ready(self):
        from django.db.models.signals import pre_save, post_save
        try:
            from taiga.projects.attachments.models import Attachment
            pre_save.connect(
                _cache_attachment_content,
                sender=Attachment,
                dispatch_uid='railway_attachment_cache_content',
            )
            post_save.connect(
                _generate_attachment_thumbnail,
                sender=Attachment,
                dispatch_uid='railway_attachment_thumbnail',
            )
            log.info("Attachment thumbnail signals connected.")
        except ImportError as exc:
            log.warning("Could not connect thumbnail signal: %s", exc)
