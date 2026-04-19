from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage

try:
    # django-storages >= 1.14
    from storages.backends.s3 import S3Storage as _S3StorageBase
except ImportError:  # pragma: no cover - compatibility fallback
    try:
        # django-storages < 1.14
        from storages.backends.s3boto3 import S3Boto3Storage as _S3StorageBase
    except ImportError:  # pragma: no cover - local/dev without django-storages installed
        _S3StorageBase = None


class StorjS3Storage(_S3StorageBase or FileSystemStorage):
    def __init__(self, **kwargs):
        from django.conf import settings
        if _S3StorageBase is None:
            raise ImproperlyConfigured(
                "django-storages is required for Storj storage. "
                "Install dependencies from requirements.txt."
            )

        kwargs.setdefault("endpoint_url", settings.STORJ_S3_ENDPOINT_URL)
        kwargs.setdefault("access_key", settings.STORJ_S3_ACCESS_KEY_ID)
        kwargs.setdefault("secret_key", settings.STORJ_S3_SECRET_ACCESS_KEY)
        kwargs.setdefault("bucket_name", settings.STORJ_S3_BUCKET_NAME)
        kwargs.setdefault("addressing_style", "path")
        kwargs.setdefault("querystring_expire", 3600)
        kwargs.setdefault("custom_domain", None)
        super().__init__(**kwargs)

    def path(self, name):
        raise NotImplementedError(
            "StorjS3Storage does not support local filesystem paths. "
            "Use default_storage.open(name) to read the file content."
        )

    def _save(self, name, content):
        # Storj's S3 gateway requires Content-Length, which the parent
        # _save's upload_fileobj doesn't always provide. Use put_object
        # instead, which sets Content-Length automatically.
        from storages.utils import clean_name

        name = self._normalize_name(clean_name(name))
        params = self._get_write_parameters(name, content)

        content.seek(0)
        body = content.read()

        put_kwargs = {
            "Bucket": self.bucket_name,
            "Key": name,
            "Body": body,
            **params,
        }
        # Normalize any lower-case/None content-length from upstream params.
        if "content_length" in put_kwargs and "ContentLength" not in put_kwargs:
            put_kwargs["ContentLength"] = put_kwargs.pop("content_length")

        if put_kwargs.get("ContentLength") is None:
            file_size = getattr(content, "size", None)
            put_kwargs["ContentLength"] = int(file_size) if file_size is not None else len(body)
        else:
            put_kwargs["ContentLength"] = int(put_kwargs["ContentLength"])

        self.connection.meta.client.put_object(**put_kwargs)
        return name


def get_storage_url(path: str) -> str:
    """Return a URL for a stored file.

    For S3 backends, ``default_storage.url()`` already returns an absolute
    pre-signed URL — calling ``build_absolute_uri`` on it would corrupt it by
    prepending the Django host.  For local filesystem storage the URL is
    relative and can be resolved via the request if needed.
    """
    from django.core.files.storage import default_storage

    url = default_storage.url(path)
    if url.startswith(("http://", "https://")):
        return url
    return url
