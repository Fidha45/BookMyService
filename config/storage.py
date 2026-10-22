"""Persistent public image storage backed by Vercel Blob."""

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class VercelBlobStorage(Storage):
    """Store public provider and service images in Vercel Blob."""

    access = "public"

    @staticmethod
    def is_blob_url(name):
        parsed = urlsplit(str(name))
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.endswith(".public.blob.vercel-storage.com")
        )

    @staticmethod
    def _blob_api():
        try:
            from vercel.blob import sync as blob
        except ImportError as exc:
            raise ImproperlyConfigured(
                "Install the vercel-blob dependency to use persistent Vercel uploads."
            ) from exc
        return blob

    @staticmethod
    def _missing_object(exc):
        return getattr(exc, "status_code", None) == 404 or getattr(exc, "code", None) in {
            "blob_not_found",
            "not_found",
        }

    def _save(self, name, content):
        content.seek(0)
        result = self._blob_api().put_blob(
            name,
            content,
            access=self.access,
            content_length=content.size,
            content_type=getattr(content, "content_type", None),
            add_random_suffix=True,
        )
        return result.url

    def upload_existing(self, name, content):
        """Copy a legacy media file to its stable Blob pathname, safely repeatable."""
        content.seek(0)
        result = self._blob_api().put_blob(
            name,
            content,
            access=self.access,
            content_length=content.size,
            content_type=getattr(content, "content_type", None),
            allow_overwrite=True,
        )
        return result.url

    def _open(self, name, mode="rb"):
        if mode not in ("rb", "r"):
            raise ValueError("Vercel Blob images can only be opened for reading.")
        if not self.is_blob_url(name):
            raise FileNotFoundError(
                "This media path has not been copied to Vercel Blob yet."
            )
        result = self._blob_api().get_blob(name, access=self.access)
        return ContentFile(result.body, name=PurePosixPath(urlsplit(name).path).name)

    def _require_blob_url(self, name):
        if not self.is_blob_url(name):
            raise FileNotFoundError(
                "This media path has not been copied to Vercel Blob yet."
            )
        return name

    def delete(self, name):
        self._blob_api().delete_blob(self._require_blob_url(name))

    def exists(self, name):
        if not self.is_blob_url(name):
            return False
        try:
            self._blob_api().head_blob(name)
        except Exception as exc:
            if self._missing_object(exc):
                return False
            raise
        return True

    def size(self, name):
        metadata = self._blob_api().head_blob(self._require_blob_url(name))
        return metadata.size

    def url(self, name):
        return self._require_blob_url(name)
