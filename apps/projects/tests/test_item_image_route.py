import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.accounts.factories import UserFactory
from apps.projects.factories import ItemFactory, ProjectFactory, ProjectMembershipFactory, SectionFactory


def png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='red').save(buffer, format='PNG')
    return buffer.getvalue()


PNG = png_bytes()


class ItemImageRouteTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        self.item.image = SimpleUploadedFile('chart.png', PNG, content_type='image/png')
        self.item.save()
        self.url = reverse('item_image', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        self.client.force_login(self.user)

    def test_a_member_gets_the_image_bytes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(b''.join(response.streaming_content), PNG)
        self.assertEqual(response['Cache-Control'], 'private, no-cache')
        self.assertIn('Last-Modified', response)

    def test_an_unchanged_image_answers_304(self):
        first = self.client.get(self.url)
        response = self.client.get(self.url, HTTP_IF_MODIFIED_SINCE=first['Last-Modified'])
        self.assertEqual(response.status_code, 304)

    def test_a_non_member_gets_404(self):
        self.client.force_login(UserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonymous_is_sent_to_sign_in(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/?next='))

    def test_an_item_without_an_image_is_404(self):
        bare = ItemFactory(project=self.project, section=self.section, created_by=self.user)
        url = reverse('item_image', kwargs={'slug': self.project.slug, 'public_key': bare.public_key})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_media_path_itself_is_not_served(self):
        self.assertEqual(self.client.get(self.item.image.url).status_code, 404)

    def test_the_api_and_the_page_point_at_the_route(self):
        detail = self.client.get(reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key}))
        self.assertEqual(detail.json()['image'], self.url)
        listing = self.client.get(reverse('api_item_list', kwargs={'slug': self.project.slug})).json()
        rows = listing['results'] if isinstance(listing, dict) else listing
        self.assertEqual(rows[0]['image'], self.url)
        page = self.client.get(reverse('project_detail', kwargs={'slug': self.project.slug}))
        self.assertContains(page, f'src="{self.url}"')
        self.assertNotContains(page, self.item.image.url)

    def test_the_upload_response_points_at_the_route(self):
        url = reverse('api_item_image', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.post(url, {'image': SimpleUploadedFile('new.png', PNG, content_type='image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['image'], self.url)
