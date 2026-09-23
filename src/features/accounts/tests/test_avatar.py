from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse


class AvatarTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.directory.name)
        override.enable(); self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user(username='photo-user')
        self.other = get_user_model().objects.create_user(username='other')
        self.client.force_login(self.user)
        self.url = reverse('accounts:account')

    def photo(self):
        buf = BytesIO(); Image.new('RGB', (700, 600), 'blue').save(buf, 'PNG')
        return SimpleUploadedFile('photo.png', buf.getvalue(), content_type='image/png')

    def test_upload_private_serving_replacement_and_removal(self):
        response = self.client.post(self.url, {'action':'photo', 'photo': self.photo(), 'id':self.other.pk})
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db(); self.other.refresh_from_db()
        self.assertFalse(self.other.avatar)
        first = self.user.avatar.path
        with Image.open(first) as image:
            self.assertEqual(image.format, 'JPEG'); self.assertLessEqual(max(image.size),512)
        response = self.client.get(reverse('accounts:avatar'))
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control'])
        response.close()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'action':'photo','photo':self.photo()})
        self.assertFalse(Path(first).exists())
        self.user.refresh_from_db(); second=self.user.avatar.path
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, {'action':'remove-photo'})
        self.assertFalse(Path(second).exists())
        self.assertEqual(self.client.get(reverse('accounts:avatar')).status_code,404)

    def test_invalid_and_oversized_preserve_current_photo(self):
        self.client.post(self.url, {'action':'photo','photo':self.photo()})
        self.user.refresh_from_db(); original=self.user.avatar.name
        for file in [SimpleUploadedFile('fake.png',b'<script>bad</script>',content_type='image/png'), SimpleUploadedFile('huge.png',b'x'*(5*1024*1024+1),content_type='image/png')]:
            response=self.client.post(self.url,{'action':'photo','photo':file})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['avatar_form'].errors)
            self.user.refresh_from_db();self.assertEqual(self.user.avatar.name,original)

    def test_authentication_and_csrf(self):
        other=Client(); other.force_login(self.other)
        self.client.post(self.url, {'action':'photo','photo':self.photo()})
        self.assertEqual(other.get(reverse('accounts:avatar')).status_code,404)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.user)
        self.assertEqual(strict.post(self.url,{'action':'remove-photo'}).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('accounts:avatar')).status_code,302)
        self.assertEqual(self.client.post(self.url,{'action':'photo','photo':self.photo()}).status_code,302)
