import json
from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from PIL import Image

from . import test_question_images as fixtures
from features.assessments.models import QuestionBankItem, QuestionImage
from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.users_manager.models import Organization, OrganizationMembership


class ImageLibraryTests(TestCase):
    setUp = fixtures.QuestionImageTests.setUp
    data = fixtures.QuestionImageTests.data

    def image(self, owner, description='Figura disponível'):
        return QuestionImage.objects.create(owner=owner, file=fixtures.image_upload(), description=description)

    def question(self, owner, image, **kwargs):
        item = QuestionBankItem.objects.create(owner=owner, subject='Geografia', topic='Mapas',
            statement='Observe a imagem', options=['A', 'B'], correct_answer='A', **kwargs)
        item.images.add(image)
        return item

    def blocks(self, image):
        return json.dumps([{'type': 'text', 'text': 'Antes'}, {'type': 'image', 'id': image.pk},
            {'type': 'text', 'text': 'Depois'}])

    def test_library_includes_own_private_and_accessible_public_images_only(self):
        own = self.image(self.user, 'Minha figura privada')
        self.question(self.user, own)
        organization = Organization.objects.create(name='Instituição', owner=self.other)
        OrganizationMembership.objects.create(organization=organization, user=self.user, is_teacher=True, added_by=self.other)
        public = self.image(self.other, 'Figura da instituição')
        self.question(self.other, public, organization=organization)
        private = self.image(self.other, 'Figura privada de outro autor')
        self.question(self.other, private)
        external = Organization.objects.create(name='Outra instituição', owner=self.other)
        restricted = self.image(self.other, 'Outra instituição sem liberação')
        self.question(self.other, restricted, organization=external)
        response = self.client.get(reverse('assessments:image-library'))
        self.assertEqual({row['id'] for row in response.json()['images']}, {own.pk, public.pk})
        self.assertNotContains(response, private.description)
        self.assertNotContains(response, restricted.description)
        self.assertEqual(self.client.get(reverse('assessments:question-image', args=[private.pk]), {'thumbnail': '1'}).status_code, 404)
        rows = self.client.get(reverse('assessments:image-library'), {'q': 'Minha figura'}).json()['images']
        self.assertEqual([row['id'] for row in rows], [own.pk])

    def test_selecting_existing_image_reuses_file_and_preserves_block_order(self):
        image = self.image(self.user)
        self.question(self.user, image)
        for form_class in (QuestionBankItemForm, QuestionForm):
            form = form_class(self.data(content_blocks=self.blocks(image)), owner=self.user)
            self.assertTrue(form.is_valid(), form.errors)
            item = form.save_for(self.user) if form_class == QuestionBankItemForm else form.save(self.assessment)
            self.assertEqual(item.images.get().pk, image.pk)
            self.assertEqual([block['type'] for block in item.content_blocks], ['text', 'image', 'text'])
            self.assertEqual(item.content_blocks[1]['description'], image.description)
        self.assertEqual(QuestionImage.objects.count(), 1)

    def test_public_access_is_checked_when_image_is_submitted(self):
        organization = Organization.objects.create(name='Publicadora', owner=self.other)
        image = self.image(self.other)
        item = self.question(self.other, image, organization=organization, external_visibility='everyone')
        form = QuestionBankItemForm(self.data(content_blocks=self.blocks(image)), owner=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        item.external_visibility = 'institution'
        item.save()
        denied = QuestionBankItemForm(self.data(content_blocks=self.blocks(image)), owner=self.user)
        self.assertFalse(denied.is_valid())
        self.assertIn('content_blocks', denied.errors)
        private = self.image(self.other, 'Privada')
        self.question(self.other, private)
        denied = QuestionBankItemForm(self.data(content_blocks=self.blocks(private)), owner=self.user)
        self.assertFalse(denied.is_valid())

    def test_thumbnails_are_small_and_library_paging_has_no_duplicates(self):
        image = self.image(self.user)
        item = self.question(self.user, image)
        self.question(self.user, image)
        self.assertEqual(len(self.client.get(reverse('assessments:image-library')).json()['images']), 1)
        response = self.client.get(reverse('assessments:question-image', args=[image.pk]), {'thumbnail': '1'})
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        with Image.open(BytesIO(response.content)) as thumbnail:
            self.assertLessEqual(max(thumbnail.size), 360)
        for i in range(25):
            item.images.add(self.image(self.user, f'Imagem {i}'))
        first = self.client.get(reverse('assessments:image-library')).json()
        self.assertEqual(len(first['images']), 24)
        second = self.client.get(reverse('assessments:image-library'), {'before': first['next']}).json()
        self.assertEqual(len(second['images']), 2)
        self.assertFalse({row['id'] for row in first['images']} & {row['id'] for row in second['images']})
        self.assertIsNone(second['next'])
        self.assertEqual(self.client.post(reverse('assessments:image-library')).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('assessments:image-library')).status_code, 302)

    def test_public_image_can_be_inserted_without_changing_its_original_owner(self):
        organization = Organization.objects.create(name='Publicadora', owner=self.other)
        image = self.image(self.other, 'Material público')
        self.question(self.other, image, organization=organization, external_visibility='everyone')
        form = QuestionBankItemForm(self.data(content_blocks=self.blocks(image)), owner=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        created = form.save_for(self.user)
        self.assertEqual(created.images.get().pk, image.pk)
        image.refresh_from_db()
        self.assertEqual(image.owner, self.other)
        self.assertEqual(QuestionImage.objects.count(), 1)
