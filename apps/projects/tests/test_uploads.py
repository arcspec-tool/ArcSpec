import io
import json
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse
from docx import Document
from PIL import Image

from apps.accounts.factories import UserFactory
from apps.projects.factories import ItemFactory, ProjectFactory, ProjectMembershipFactory, SectionFactory
from apps.projects.models import Attachment, Item


def image_bytes(fmt):
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='red').save(buffer, format=fmt)
    return buffer.getvalue()


def docx_bytes():
    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph('Report')
    document.save(buffer)
    return buffer.getvalue()


def zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('notes.txt', 'Notes')
    return buffer.getvalue()


class UploadContentTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(project=self.project, section=self.section, item_id='REQ-001', created_by=self.user)
        self.client.force_login(self.user)

    def attachment_url(self):
        return reverse('api_attachment_list', kwargs={'slug': self.project.slug, 'item_key': self.item.public_key})

    def test_every_page_upload_refuses_content_that_does_not_match_the_extension_and_saves_nothing(self):
        jpeg_named_png = image_bytes('JPEG')
        image_refusal = ['The content of the file is image/jpeg, which does not match .png.']
        cases = (
            ('attachment', lambda: self.client.post(self.attachment_url(), {
                'file': SimpleUploadedFile('report.pdf', b'<html><body>Report</body></html>'),
            }), {'file': ['The content of the file is text/html, which does not match .pdf.']}),
            ('image of an item', lambda: self.client.post(
                reverse('api_item_image', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key}),
                {'image': SimpleUploadedFile('chart.png', jpeg_named_png)},
            ), {'error': image_refusal[0]}),
            ('image of a new item', lambda: self.client.post(
                reverse('api_item_list', kwargs={'slug': self.project.slug}),
                {'section': self.section.pk, 'text': 'New item', 'image': SimpleUploadedFile('chart.png', jpeg_named_png)},
            ), {'image': image_refusal}),
            ('image in an item edit', lambda: self.client.patch(
                reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key}),
                data=encode_multipart(BOUNDARY, {'image': SimpleUploadedFile('chart.png', jpeg_named_png)}),
                content_type=MULTIPART_CONTENT,
            ), {'image': image_refusal}),
        )
        for case, send, body in cases:
            with self.subTest(case=case):
                response = send()
                self.assertEqual((response.status_code, response.json()), (400, body))
        self.item.refresh_from_db()
        self.assertEqual((Attachment.objects.count(), Item.objects.count(), bool(self.item.image)), (0, 1, False))

    def test_an_attachment_whose_content_matches_its_extension_is_stored(self):
        for name, content in (
            ('report.docx', docx_bytes()),
            ('chart.png', image_bytes('PNG')),
            ('photo.jpg', image_bytes('JPEG')),
            ('bundle.zip', zip_bytes()),
            ('script.txt', b'#!/usr/bin/env python3\nprint("checked")\n'),
            ('data.json', json.dumps({'name': 'alpha'}).encode()),
        ):
            with self.subTest(name=name):
                response = self.client.post(self.attachment_url(), {'file': SimpleUploadedFile(name, content)})
                self.assertEqual(response.status_code, 201)
        self.assertEqual(
            sorted(Attachment.objects.values_list('filename', flat=True)),
            ['bundle.zip', 'chart.png', 'data.json', 'photo.jpg', 'report.docx', 'script.txt'],
        )
