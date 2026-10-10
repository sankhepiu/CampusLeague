import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

# The smallest files that really are what their extension says.
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
PDF = b'%PDF-1.4\n%%EOF\n'


def receipt(name='receipt.png', content=PNG, content_type='image/png'):
    return SimpleUploadedFile(name, content, content_type=content_type)


class TempMediaMixin:
    """Uploads made by a test go to a throwaway folder, removed afterwards."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='campusleague-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
