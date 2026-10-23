import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.notifications.factories import AuditLogFactory
from apps.notifications.models import AuditLog, Notification
from apps.projects.factories import (
    AttachmentFactory,
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    ProjectVersionFactory,
    SavedViewFactory,
    SectionFactory,
    TagFactory,
    PresetTagFactory,
    TraceabilityLinkFactory,
)
from apps.projects.models import (
    Attachment,
    Comment,
    Item,
    ItemTag,
    ProjectMembership,
    ProjectVersion,
    SavedView,
    Tag,
    TraceabilityLink,
)


class ItemAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', text='Test item', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_create_item(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': 'New item',
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Item.objects.filter(project=self.project, text='New item').exists())

    def test_insert_before_and_after_place_the_new_item_next_to_the_anchor(self):
        second = ItemFactory(project=self.project, section=self.section, item_id='REQ-002', text='Second', created_by=self.user)
        Item.objects.filter(pk=self.item.pk).update(order=1)
        Item.objects.filter(pk=second.pk).update(order=2)
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        for anchor_field, anchor, text in (('insert_before', second, 'Above second'), ('insert_after', self.item, 'Below first')):
            response = self.client.post(url, data=json.dumps({
                'section': self.section.pk, 'text': text, 'status': 'draft', 'priority': 'medium',
                anchor_field: str(anchor.public_key),
            }), content_type='application/json')
            self.assertEqual(response.status_code, 201)
        texts = list(Item.objects.filter(section=self.section).order_by('order').values_list('text', flat=True))
        self.assertEqual(texts, ['Test item', 'Below first', 'Above second', 'Second'])

    def test_insert_anchor_in_another_section_is_refused(self):
        other_section = SectionFactory(project=self.project, number='2', title='Other')
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': other_section.pk, 'text': 'Misplaced', 'status': 'draft', 'priority': 'medium',
            'insert_before': str(self.item.public_key),
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Item.objects.filter(text='Misplaced').exists())

    def test_create_item_rejects_cross_project_section(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project, number='1', title='Foreign')
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': other_section.pk,
            'text': 'Cross-project attempt',
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Item.objects.filter(text='Cross-project attempt').exists())

    def test_create_item_auto_generates_id(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': 'Auto ID item',
            'status': 'draft',
            'priority': 'high',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(text='Auto ID item')
        self.assertTrue(item.item_id.startswith(self.project.template.item_id_prefix))

    def test_get_item_detail(self):
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['item_id'], 'REQ-001')

    def test_a_patch_with_a_section_of_another_project_is_refused(self):
        foreign = SectionFactory(project=ProjectFactory(), number='1', title='Foreign')
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({'section': foreign.pk}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.json()), ['section'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.section, self.section)

    def test_an_inactive_or_non_member_assignee_is_refused_on_every_write_path(self):
        inactive = UserFactory(is_active=False)
        ProjectMembershipFactory(project=self.project, user=inactive, role='editor')
        stranger = UserFactory()
        create_url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        patch_url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        inline_url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        paths = (
            ('create', 'post', create_url, 'assignee', lambda pk: {'section': self.section.pk, 'text': 'Assigned', 'status': 'draft', 'priority': 'medium', 'assignee': pk}),
            ('patch', 'patch', patch_url, 'assignee', lambda pk: {'assignee': pk}),
            ('inline', 'patch', inline_url, 'error', lambda pk: {'field': 'assignee', 'value': str(pk)}),
        )
        for path, method, url, key, payload in paths:
            for case, user in (('inactive', inactive), ('non-member', stranger)):
                with self.subTest(path=path, case=case):
                    response = getattr(self.client, method)(url, data=json.dumps(payload(user.pk)), content_type='application/json')
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(list(response.json()), [key])
        self.item.refresh_from_db()
        self.assertIsNone(self.item.assignee)
        self.assertEqual(Item.objects.filter(project=self.project).count(), 1)

    def test_a_patch_with_item_id_and_order_leaves_both_unchanged(self):
        Item.objects.filter(pk=self.item.pk).update(order=3)
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'item_id': 'REQ-999', 'order': 42, 'text': '<p>Renumbered</p>',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual((self.item.item_id, self.item.order, self.item.text), ('REQ-001', 3, '<p>Renumbered</p>'))

    def test_inline_edit_status(self):
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'field': 'status', 'value': 'approved',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'approved')

    def test_inline_edit_text(self):
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'field': 'text', 'value': '<p>Updated text</p>',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.text, '<p>Updated text</p>')

    def test_delete_item(self):
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Item.objects.filter(pk=self.item.pk).exists())

    def test_delete_item_audit_row_names_the_deleting_user(self):
        item = ItemFactory(project=self.project, section=self.section, created_by=UserFactory())
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        self.assertEqual(self.client.delete(url).status_code, 204)
        row = AuditLog.objects.get(project=self.project, action='deleted', target_type='Item', target_id=item.item_id)
        self.assertEqual(row.user, self.user)

    def test_bulk_set_status(self):
        item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', text='Item 2', created_by=self.user
        )
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item.pk, item2.pk],
            'action': 'set_status',
            'value': 'approved',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(self.item.status, 'approved')
        self.assertEqual(item2.status, 'approved')

    def test_viewer_cannot_create_item(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': 'Should fail',
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_create_item_with_html(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': '<p><strong>Bold</strong> text</p>',
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(text='<p><strong>Bold</strong> text</p>')
        self.assertIn('<strong>', item.text)

    def test_create_item_strips_script(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': '<p>Safe</p><script>alert("xss")</script>',
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        item = Item.objects.filter(project=self.project).order_by('-pk').first()
        self.assertNotIn('<script', item.text)
        self.assertIn('<p>Safe</p>', item.text)

    def test_create_item_preserves_table(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        html = '<table><thead><tr><th>Col</th></tr></thead><tbody><tr><td>Val</td></tr></tbody></table>'
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': html,
            'status': 'draft',
            'priority': 'medium',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        item = Item.objects.filter(project=self.project).order_by('-pk').first()
        self.assertIn('<table>', item.text)
        self.assertIn('<th>Col</th>', item.text)

    def test_update_item_sanitizes_text(self):
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'text': '<p>Clean</p><script>bad</script>',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertNotIn('<script', self.item.text)
        self.assertIn('<p>Clean</p>', self.item.text)

    def test_inline_edit_text_sanitizes(self):
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'field': 'text', 'value': '<p>Good</p><img src=x onerror=alert(1)>',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertNotIn('<img', self.item.text)
        self.assertIn('<p>Good</p>', self.item.text)

    def test_inline_edit_rejects_invalid_status(self):
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'field': 'status', 'value': 'hacked',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'draft')

    def test_inline_edit_rejects_invalid_priority(self):
        url = reverse('api_item_inline_edit', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'field': 'priority', 'value': 'super-urgent',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.item.refresh_from_db()
        self.assertEqual(self.item.priority, 'medium')

    def test_bulk_operation_rejects_invalid_status(self):
        item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', text='Item 2', created_by=self.user
        )
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item.pk, item2.pk],
            'action': 'set_status',
            'value': 'invalid-status',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('value', response.json())
        self.item.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(self.item.status, 'draft')
        self.assertEqual(item2.status, 'draft')

    def test_bulk_operation_rejects_invalid_priority(self):
        item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', text='Item 2', created_by=self.user
        )
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item.pk, item2.pk],
            'action': 'set_priority',
            'value': 'critical',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('value', response.json())
        self.item.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(self.item.priority, 'medium')
        self.assertEqual(item2.priority, 'medium')


class CommentAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_create_comment(self):
        url = reverse('api_comment_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'text': 'Nice work!',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Comment.objects.filter(item=self.item, text='Nice work!').exists())

    def test_a_reply_to_a_comment_on_another_item_is_refused_and_notifies_nobody(self):
        other_item = ItemFactory(project=self.project, section=self.section, item_id='REQ-002', created_by=self.user)
        author = UserFactory()
        ProjectMembershipFactory(project=self.project, user=author, role='editor')
        parent = CommentFactory(item=other_item, author=author, text='Elsewhere')
        Notification.objects.all().delete()
        url = reverse('api_comment_list', kwargs={'slug': self.project.slug, 'item_key': self.item.public_key})
        response = self.client.post(url, data=json.dumps({'text': 'Reply', 'parent': parent.pk}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.json()), ['parent'])
        self.assertEqual(Comment.objects.filter(parent=parent).count(), 0)
        self.assertEqual(Notification.objects.filter(user=author).count(), 0)

    def test_delete_own_comment(self):
        comment = CommentFactory(item=self.item, author=self.user)
        url = reverse('api_comment_delete', kwargs={
            'slug': self.project.slug, 'public_key': comment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)


class TagAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.client.force_login(self.user)

    def test_create_tag(self):
        url = reverse('api_tag_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'name': 'NewTag', 'color': '#ff0000',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Tag.objects.filter(name='NewTag', project=self.project).exists())


class SavedViewAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.client.force_login(self.user)

    def test_create_saved_view(self):
        url = reverse('api_saved_view_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'name': 'My View',
            'filters': {'status': 'draft'},
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(SavedView.objects.filter(name='My View').exists())

    def test_delete_saved_view(self):
        sv = SavedViewFactory(project=self.project, user=self.user, name='Temp')
        url = reverse('api_saved_view_delete', kwargs={
            'slug': self.project.slug, 'public_key': sv.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)

    def test_cannot_delete_default_view(self):
        sv = SavedViewFactory(project=self.project, user=self.user, name='All Items', is_default=True)
        url = reverse('api_saved_view_delete', kwargs={
            'slug': self.project.slug, 'public_key': sv.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)


class CollaboratorAPITests(TestCase):

    def setUp(self):
        self.admin_user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.admin_user, role='admin')
        self.client.force_login(self.admin_user)

    def test_invite_collaborator(self):
        new_user = UserFactory()
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': new_user.email, 'role': 'editor',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(ProjectMembership.objects.filter(
            project=self.project, user=new_user, role='editor'
        ).exists())

    def test_invite_duplicate_fails(self):
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': self.admin_user.email, 'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_invite_nonexistent_user_fails(self):
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': 'nobody@example.com', 'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_invite_rejects_an_unknown_role(self):
        new_user = UserFactory()
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': new_user.email, 'role': 'owner',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=new_user).exists())

    def test_editor_cannot_invite(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        url = reverse('api_collaborator_invite', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'email': UserFactory().email, 'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_change_role(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='editor')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.role, 'viewer')

    def test_remove_collaborator(self):
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='viewer')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(pk=m.pk).exists())

    def _membership_added_by_someone_else(self):
        inviter = UserFactory()
        ProjectMembershipFactory(project=self.project, user=inviter, role='admin')
        member = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=member, role='editor', added_by=inviter)
        AuditLog.objects.all().delete()
        Notification.objects.all().delete()
        return m, member, inviter

    def test_role_change_is_attributed_to_the_admin_who_made_it(self):
        m, member, inviter = self._membership_added_by_someone_else()
        url = reverse('api_collaborator_update', kwargs={'slug': self.project.slug, 'public_key': m.public_key})
        response = self.client.patch(url, data=json.dumps({'role': 'viewer'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        log = AuditLog.objects.get(project=self.project, action='collaborator_role_changed')
        self.assertEqual(log.user, self.admin_user)
        notification = Notification.objects.get(user=member)
        self.assertEqual(notification.actor, self.admin_user)
        self.assertNotEqual(log.user, inviter)

    def test_removal_is_attributed_to_the_admin_who_made_it(self):
        m, member, inviter = self._membership_added_by_someone_else()
        url = reverse('api_collaborator_update', kwargs={'slug': self.project.slug, 'public_key': m.public_key})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        log = AuditLog.objects.get(project=self.project, action='collaborator_removed')
        self.assertEqual(log.user, self.admin_user)
        notification = Notification.objects.get(user=member)
        self.assertEqual(notification.actor, self.admin_user)
        self.assertNotEqual(log.user, inviter)

    def test_cannot_demote_last_admin(self):
        my_membership = ProjectMembership.objects.get(
            project=self.project, user=self.admin_user
        )
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': my_membership.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('last project admin', response.json()['error'])
        my_membership.refresh_from_db()
        self.assertEqual(my_membership.role, 'admin')

    def test_cannot_delete_last_admin(self):
        my_membership = ProjectMembership.objects.get(
            project=self.project, user=self.admin_user
        )
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': my_membership.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('last project admin', response.json()['error'])
        self.assertTrue(ProjectMembership.objects.filter(pk=my_membership.pk).exists())

    def test_can_demote_admin_when_another_admin_exists(self):
        second_admin = UserFactory()
        ProjectMembershipFactory(project=self.project, user=second_admin, role='admin')
        my_membership = ProjectMembership.objects.get(
            project=self.project, user=self.admin_user
        )
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': my_membership.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'editor',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        my_membership.refresh_from_db()
        self.assertEqual(my_membership.role, 'editor')

    def test_can_delete_admin_when_another_admin_exists(self):
        second_admin = UserFactory()
        ProjectMembershipFactory(project=self.project, user=second_admin, role='admin')
        my_membership = ProjectMembership.objects.get(
            project=self.project, user=self.admin_user
        )
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': my_membership.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProjectMembership.objects.filter(pk=my_membership.pk).exists())

    def test_can_demote_non_admin_freely(self):
        editor = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'role': 'viewer',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.role, 'viewer')

    def test_can_delete_non_admin_freely(self):
        editor = UserFactory()
        m = ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        url = reverse('api_collaborator_update', kwargs={
            'slug': self.project.slug, 'public_key': m.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)


class PermissionTests(TestCase):

    def setUp(self):
        self.project = ProjectFactory()
        self.section = SectionFactory(project=self.project)

    def test_nonmember_cannot_access_items(self):
        user = UserFactory()
        self.client.force_login(user)
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_system_admin_can_access_any_project(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class AttachmentAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_upload_attachment(self):
        url = reverse('api_attachment_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        test_file = SimpleUploadedFile('report.pdf', b'%PDF-1.4\n%%EOF\n', content_type='application/pdf')
        response = self.client.post(url, {'file': test_file})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Attachment.objects.filter(item=self.item, filename='report.pdf').exists())

    def test_delete_attachment(self):
        attachment = AttachmentFactory(item=self.item, uploaded_by=self.user)
        url = reverse('api_attachment_delete', kwargs={
            'slug': self.project.slug, 'public_key': attachment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())

    def test_delete_attachment_removes_the_file_from_storage(self):
        from django.core.files.storage import default_storage

        attachment = AttachmentFactory(item=self.item, uploaded_by=self.user)
        stored_name = attachment.file.name
        self.assertTrue(default_storage.exists(stored_name))
        url = reverse('api_attachment_delete', kwargs={
            'slug': self.project.slug, 'public_key': attachment.public_key
        })
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(default_storage.exists(stored_name))

    def test_viewer_cannot_upload_attachment(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('api_attachment_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        test_file = SimpleUploadedFile('report.pdf', b'pdf-content', content_type='application/pdf')
        response = self.client.post(url, {'file': test_file})
        self.assertEqual(response.status_code, 403)

    def test_svg_attachment_rejected(self):
        url = reverse('api_attachment_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        svg_file = SimpleUploadedFile('diagram.svg', svg_content, content_type='image/svg+xml')
        response = self.client.post(url, {'file': svg_file})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Attachment.objects.filter(item=self.item, filename='diagram.svg').exists())


class TraceabilityLinkAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item1 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user
        )
        self.item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_incoming_link_names_the_source_item_and_its_project(self):
        TraceabilityLinkFactory(source_item=self.item1, target_item=self.item2, link_type='traces-to', created_by=self.user)
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item2.public_key})
        link = self.client.get(url).json()['incoming_links'][0]
        self.assertEqual((link['source_item_id'], link['source_project_name']), ('REQ-001', self.project.name))

    def test_create_link(self):
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': self.item2.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(TraceabilityLink.objects.filter(
            source_item=self.item1, target_item=self.item2
        ).exists())

    def test_a_link_to_itself_or_into_an_archived_project_is_refused(self):
        archived = ProjectFactory(status='archived')
        ProjectMembershipFactory(project=archived, user=self.user, role='editor')
        archived_item = ItemFactory(project=archived, section=SectionFactory(project=archived), item_id='TC-001', created_by=self.user)
        url = reverse('api_link_list', kwargs={'slug': self.project.slug, 'item_key': self.item1.public_key})
        for case, target in (('itself', self.item1), ('archived project', archived_item)):
            with self.subTest(case=case):
                response = self.client.post(url, data=json.dumps({
                    'source_item': self.item1.pk, 'target_item': target.pk, 'link_type': 'related-to',
                }), content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), ['target_item'])
        self.assertEqual(TraceabilityLink.objects.count(), 0)

    def test_delete_link(self):
        link = TraceabilityLinkFactory(
            source_item=self.item1, target_item=self.item2, created_by=self.user
        )
        url = reverse('api_link_delete', kwargs={
            'slug': self.project.slug, 'public_key': link.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TraceabilityLink.objects.filter(pk=link.pk).exists())

    def test_viewer_cannot_create_link(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': self.item2.pk,
            'link_type': 'related-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_cross_project_link_with_access(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        ProjectMembershipFactory(project=other_project, user=self.user, role='editor')
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='TC-001', created_by=self.user
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': other_item.pk,
            'link_type': 'verified-by',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_cross_project_link_without_target_access_denied(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='TC-001', created_by=UserFactory()
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': other_item.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('target_item', response.json())
        self.assertFalse(TraceabilityLink.objects.filter(
            source_item=self.item1, target_item=other_item
        ).exists())

    def test_cross_project_link_no_leak_of_project_name(self):
        other_project = ProjectFactory(name='Secret Project Alpha')
        other_section = SectionFactory(project=other_project)
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='SEC-001', created_by=UserFactory()
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': other_item.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Secret Project Alpha', response.content.decode())

    def test_cross_project_link_viewer_on_target_allowed(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        ProjectMembershipFactory(project=other_project, user=self.user, role='viewer')
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='TC-001', created_by=UserFactory()
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': other_item.pk,
            'link_type': 'related-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_source_item_must_belong_to_url_project(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        ProjectMembershipFactory(project=other_project, user=self.user, role='editor')
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='TC-001', created_by=self.user
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': other_item.pk,
            'target_item': self.item2.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('source_item', response.json())

    def test_system_admin_can_link_to_any_project(self):
        admin = AdminUserFactory()
        ProjectMembershipFactory(project=self.project, user=admin, role='admin')
        self.client.force_login(admin)
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        other_item = ItemFactory(
            project=other_project, section=other_section,
            item_id='TC-001', created_by=UserFactory()
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': other_item.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_cannot_enumerate_items_via_link_creation(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        items = []
        for i in range(3):
            items.append(ItemFactory(
                project=other_project, section=other_section,
                item_id=f'SEC-{i+1:03d}', created_by=UserFactory()
            ))
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        for item in items:
            response = self.client.post(url, data=json.dumps({
                'source_item': self.item1.pk,
                'target_item': item.pk,
                'link_type': 'traces-to',
            }), content_type='application/json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(TraceabilityLink.objects.count(), 0)

    def test_nonexistent_target_item_returns_400(self):
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': 99999,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_duplicate_link_rejected(self):
        TraceabilityLinkFactory(
            source_item=self.item1, target_item=self.item2,
            link_type='traces-to', created_by=self.user
        )
        url = reverse('api_link_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item1.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'source_item': self.item1.pk,
            'target_item': self.item2.pk,
            'link_type': 'traces-to',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)


class AuditLogFilterAPITests(TestCase):

    def test_collaboration_filter_returns_added_removed_and_role_changed_rows(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMembershipFactory(project=project, user=user, role='viewer')
        AuditLog.objects.all().delete()
        for action in ('collaborator_added', 'collaborator_removed', 'collaborator_role_changed', 'created'):
            AuditLogFactory(project=project, user=user, action=action)
        self.client.force_login(user)
        response = self.client.get(reverse('api_audit_log', kwargs={'slug': project.slug}), {'action': 'collaboration'})
        self.assertEqual(
            sorted(entry['action'] for entry in response.json()['results']),
            ['collaborator_added', 'collaborator_removed', 'collaborator_role_changed'],
        )

    def test_a_page_parameter_that_is_not_a_whole_number_answers_400(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMembershipFactory(project=project, user=user, role='viewer')
        self.client.force_login(user)
        url = reverse('api_audit_log', kwargs={'slug': project.slug})
        for parameter, value in (('offset', 'x'), ('limit', 'x'), ('offset', '-1')):
            with self.subTest(parameter=parameter, value=value):
                response = self.client.get(url, {parameter: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [parameter])


class ItemReorderAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item1 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user, order=0
        )
        self.item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', created_by=self.user, order=1
        )
        self.client.force_login(self.user)

    def test_reorder_items(self):
        url = reverse('api_item_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'items': [
                {'id': self.item1.pk, 'order': 1},
                {'id': self.item2.pk, 'order': 0},
            ]
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        self.assertEqual(self.item1.order, 1)
        self.assertEqual(self.item2.order, 0)

    def test_reorder_changes_section(self):
        section2 = SectionFactory(project=self.project, number='2', title='Details')
        url = reverse('api_item_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'items': [
                {'id': self.item1.pk, 'order': 0, 'section': section2.pk},
            ]
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.section_id, section2.pk)

    def test_viewer_cannot_reorder(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('api_item_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'items': [{'id': self.item1.pk, 'order': 5}]
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_reorder_rejects_cross_project_section(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project, number='1', title='Foreign')
        url = reverse('api_item_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'items': [
                {'id': self.item1.pk, 'order': 0, 'section': other_section.pk},
            ]
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.section_id, self.section.pk)


class ItemFilterAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.draft_item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', status='draft', priority='high',
            text='Draft high item', created_by=self.user
        )
        self.approved_item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', status='approved', priority='low',
            text='Approved low item', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_filter_by_status(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url + '?status=draft')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data if isinstance(data, list) else data.get('results', data)
        self.assertTrue(all(i['status'] == 'draft' for i in items))
        self.assertEqual(len(items), 1)

    def test_filter_by_priority(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url + '?priority=high')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data if isinstance(data, list) else data.get('results', data)
        self.assertTrue(all(i['priority'] == 'high' for i in items))
        self.assertEqual(len(items), 1)

    def test_filter_by_tag(self):
        tag = TagFactory(project=self.project, name='Important')
        ItemTag.objects.create(item=self.draft_item, tag=tag)
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url + '?tag=Important')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data if isinstance(data, list) else data.get('results', data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_id'], 'REQ-001')

    def test_filter_by_search(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url + '?search=Approved')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data if isinstance(data, list) else data.get('results', data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_id'], 'REQ-002')

    def test_filter_by_section(self):
        section2 = SectionFactory(project=self.project, number='2', title='Details')
        ItemFactory(
            project=self.project, section=section2,
            item_id='REQ-003', created_by=self.user
        )
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url + '?section=' + str(section2.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        items = data if isinstance(data, list) else data.get('results', data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['item_id'], 'REQ-003')


class BulkOperationExtendedTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item1 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user
        )
        self.item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', created_by=self.user
        )
        self.client.force_login(self.user)

    def test_bulk_set_priority(self):
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item1.pk, self.item2.pk],
            'action': 'set_priority',
            'value': 'high',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        self.assertEqual(self.item1.priority, 'high')
        self.assertEqual(self.item2.priority, 'high')

    def test_bulk_add_tag_attaches_the_chosen_preset_without_copying_it(self):
        preset = PresetTagFactory(name='Urgent')
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item1.pk],
            'action': 'add_tag',
            'value': str(preset.pk),
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(ItemTag.objects.filter(item=self.item1).values_list('tag', flat=True)), [preset.pk])
        self.assertEqual(Tag.objects.filter(name='Urgent').count(), 1)

    def test_bulk_delete(self):
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item1.pk, self.item2.pk],
            'action': 'delete',
            'value': '',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(pk=self.item1.pk).exists())
        self.assertFalse(Item.objects.filter(pk=self.item2.pk).exists())

    def test_bulk_delete_writes_one_audit_row_per_item_and_one_version(self):
        creator = UserFactory()
        ProjectMembershipFactory(project=self.project, user=creator, role='editor')
        Item.objects.filter(pk=self.item1.pk).update(created_by=creator)
        AuditLog.objects.filter(project=self.project).delete()
        Notification.objects.all().delete()
        versions = ProjectVersion.objects.filter(project=self.project).count()
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item1.pk, self.item2.pk],
            'action': 'delete',
            'value': '',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        rows = AuditLog.objects.filter(project=self.project)
        self.assertEqual(sorted(rows.values_list('target_id', flat=True)), sorted([self.item1.item_id, self.item2.item_id]))
        self.assertEqual({row.user for row in rows}, {self.user})
        self.assertEqual({row.action for row in rows}, {'deleted'})
        self.assertEqual(ProjectVersion.objects.filter(project=self.project).count(), versions + 1)
        self.assertEqual(Notification.objects.count(), 0)

    def test_viewer_cannot_bulk_operate(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('api_item_bulk', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'item_ids': [self.item1.pk],
            'action': 'set_status',
            'value': 'approved',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)


class VersionHistoryAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')
        self.client.force_login(self.user)

    def test_the_version_list_runs_a_constant_number_of_queries_without_loading_snapshots(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        url = reverse('api_version_list', kwargs={'slug': self.project.slug})
        for n in range(2):
            ProjectVersionFactory(project=self.project, changed_by=self.user, version_number=f'0.{n}', snapshot={'sections': [], 'items': [{'id': n}]})
        with CaptureQueriesContext(connection) as few:
            self.assertEqual(self.client.get(url).json()['count'], 2)
        for n in range(2, 7):
            ProjectVersionFactory(project=self.project, changed_by=self.user, version_number=f'0.{n}', snapshot={'sections': [], 'items': [{'id': n}]})
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.client.get(url).json()['count'], 7)
        self.assertEqual(len(many), len(few))
        self.assertEqual([query['sql'] for query in many if '"snapshot"' in query['sql']], [])

    def test_restore_version(self):
        version = ProjectVersionFactory(project=self.project, changed_by=self.user)
        url = reverse('api_version_restore', kwargs={
            'slug': self.project.slug, 'public_key': version.public_key
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')

    def test_editor_cannot_restore_version(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        version = ProjectVersionFactory(project=self.project, changed_by=self.user)
        url = reverse('api_version_restore', kwargs={
            'slug': self.project.slug, 'public_key': version.public_key
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


class ViewerPermissionTests(TestCase):

    def setUp(self):
        self.editor = UserFactory()
        self.viewer = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.editor, role='editor')
        ProjectMembershipFactory(project=self.project, user=self.viewer, role='viewer')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.editor
        )

    def test_viewer_cannot_inline_edit(self):
        self.client.force_login(self.viewer)
        url = reverse('api_item_inline_edit', kwargs={
            'slug': self.project.slug, 'public_key': self.item.public_key
        })
        response = self.client.patch(url, data=json.dumps({
            'field': 'status', 'value': 'approved',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_delete_item(self):
        self.client.force_login(self.viewer)
        url = reverse('api_item_detail', kwargs={
            'slug': self.project.slug, 'public_key': self.item.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_viewer_can_comment(self):
        self.client.force_login(self.viewer)
        url = reverse('api_comment_list', kwargs={
            'slug': self.project.slug, 'item_key': self.item.public_key
        })
        response = self.client.post(url, data=json.dumps({
            'text': 'Viewer comment',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_viewer_cannot_create_tag(self):
        self.client.force_login(self.viewer)
        url = reverse('api_tag_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'name': 'ViewerTag', 'color': '#000000',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_delete_attachment(self):
        self.client.force_login(self.viewer)
        attachment = AttachmentFactory(item=self.item, uploaded_by=self.editor)
        url = reverse('api_attachment_delete', kwargs={
            'slug': self.project.slug, 'public_key': attachment.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_delete_link(self):
        self.client.force_login(self.viewer)
        item2 = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', created_by=self.editor
        )
        link = TraceabilityLinkFactory(
            source_item=self.item, target_item=item2, created_by=self.editor
        )
        url = reverse('api_link_delete', kwargs={
            'slug': self.project.slug, 'public_key': link.public_key
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)


class ItemImageAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', text='Test item', created_by=self.user
        )
        self.client.force_login(self.user)
        self.url = reverse('api_item_image', kwargs={
            'slug': self.project.slug, 'public_key': self.item.public_key
        })

    def test_upload_image(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (2, 2), color='red').save(buf, format='PNG')
        image = SimpleUploadedFile('chart.png', buf.getvalue(), content_type='image/png')
        response = self.client.post(self.url, {'image': image, 'image_caption': 'Test chart'})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.image)
        self.assertEqual(self.item.image_caption, 'Test chart')

    def test_upload_rejects_invalid_extension(self):
        bad_file = SimpleUploadedFile('script.exe', b'\x00' * 100, content_type='application/octet-stream')
        response = self.client.post(self.url, {'image': bad_file})
        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_oversized(self):
        big = SimpleUploadedFile('huge.png', b'\x89PNG' + b'\x00' * (6 * 1024 * 1024), content_type='image/png')
        response = self.client.post(self.url, {'image': big})
        self.assertEqual(response.status_code, 400)

    def test_delete_image(self):
        self.item.image = SimpleUploadedFile('chart.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 100, content_type='image/png')
        self.item.image_caption = 'Old caption'
        self.item.save()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)
        self.assertEqual(self.item.image_caption, '')

    def test_viewer_cannot_upload(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        image = SimpleUploadedFile('chart.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 100, content_type='image/png')
        response = self.client.post(self.url, {'image': image})
        self.assertEqual(response.status_code, 403)

    def test_svg_upload_rejected(self):
        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        svg_file = SimpleUploadedFile('malicious.svg', svg_content, content_type='image/svg+xml')
        response = self.client.post(self.url, {'image': svg_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('not allowed', response.json()['error'])
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)


class ItemImageBypassTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', text='Test item', created_by=self.user
        )
        self.client.force_login(self.user)
        self.patch_url = reverse('api_item_detail', kwargs={
            'slug': self.project.slug, 'public_key': self.item.public_key,
        })
        self.create_url = reverse('api_item_list', kwargs={
            'slug': self.project.slug,
        })

    def _make_bmp(self):
        import struct
        w, h = 2, 2
        row_size = (w * 3 + 3) & ~3
        pixel_data_size = row_size * h
        file_size = 54 + pixel_data_size
        bmp = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
        bmp += struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0,
                           pixel_data_size, 2835, 2835, 0, 0)
        row = (b'\xff\x00\x00' * w) + (b'\x00' * (row_size - w * 3))
        bmp += row * h
        return bmp

    def test_patch_rejects_disallowed_extension(self):
        bmp = SimpleUploadedFile('test.bmp', self._make_bmp(), content_type='image/bmp')
        response = self.client.patch(
            self.patch_url,
            data=encode_multipart(BOUNDARY, {'image': bmp}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)

    def test_patch_rejects_oversized_image(self):
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * (6 * 1024 * 1024)
        big = SimpleUploadedFile('big.png', data, content_type='image/png')
        response = self.client.patch(
            self.patch_url,
            data=encode_multipart(BOUNDARY, {'image': big}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)

    def test_create_rejects_disallowed_extension(self):
        bmp = SimpleUploadedFile('test.bmp', self._make_bmp(), content_type='image/bmp')
        response = self.client.post(
            self.create_url,
            {'section': self.section.pk, 'text': 'New item', 'image': bmp},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_oversized_image(self):
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * (6 * 1024 * 1024)
        big = SimpleUploadedFile('big.png', data, content_type='image/png')
        response = self.client.post(
            self.create_url,
            {'section': self.section.pk, 'text': 'New item', 'image': big},
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_allows_valid_png(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (2, 2), color='red').save(buf, format='PNG')
        buf.seek(0)
        png = SimpleUploadedFile('ok.png', buf.read(), content_type='image/png')
        response = self.client.patch(
            self.patch_url,
            data=encode_multipart(BOUNDARY, {'image': png}),
            content_type=MULTIPART_CONTENT,
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.image)


class ItemAttributeValueAPITests(TestCase):

    def setUp(self):
        from apps.projects.factories import ProjectAttributeFactory
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.attr_dropdown = ProjectAttributeFactory(
            project=self.project, name='Risk Level',
            field_type='dropdown', options=['Low', 'Medium', 'High']
        )
        self.attr_text = ProjectAttributeFactory(
            project=self.project, name='Notes', field_type='text'
        )
        self.attr_bool = ProjectAttributeFactory(
            project=self.project, name='Automated', field_type='boolean'
        )
        self.client.force_login(self.user)

    def test_create_item_with_attribute_values(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk,
            'text': 'Item with attrs',
            'status': 'draft',
            'priority': 'medium',
            'attribute_values': [
                {'attribute': self.attr_dropdown.pk, 'value': 'High'},
                {'attribute': self.attr_text.pk, 'value': 'Some note'},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        from apps.projects.models import ItemAttributeValue
        item = Item.objects.get(text='Item with attrs')
        self.assertEqual(item.attribute_values.count(), 2)
        self.assertEqual(
            item.attribute_values.get(attribute=self.attr_dropdown).value, 'High'
        )

    def test_update_item_attribute_values(self):
        item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', text='Existing', created_by=self.user
        )
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'attribute_values': [
                {'attribute': self.attr_bool.pk, 'value': 'true'},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        from apps.projects.models import ItemAttributeValue
        self.assertEqual(
            ItemAttributeValue.objects.get(item=item, attribute=self.attr_bool).value, 'true'
        )

    def test_item_detail_includes_attribute_values(self):
        from apps.projects.factories import ItemAttributeValueFactory
        item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-002', text='Detail item', created_by=self.user
        )
        ItemAttributeValueFactory(item=item, attribute=self.attr_dropdown, value='Medium')
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        response = self.client.get(url)
        data = response.json()
        self.assertEqual(len(data['attribute_values']), 1)
        self.assertEqual(data['attribute_values'][0]['attribute_name'], 'Risk Level')
        self.assertEqual(data['attribute_values'][0]['value'], 'Medium')

    def test_item_list_includes_attribute_values(self):
        from apps.projects.factories import ItemAttributeValueFactory
        item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-003', text='List item', created_by=self.user
        )
        ItemAttributeValueFactory(item=item, attribute=self.attr_text, value='A note')
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.get(url)
        data = response.json()
        results = data.get('results', data)
        item_data = [d for d in results if d['id'] == item.pk][0]
        self.assertEqual(len(item_data['attribute_values']), 1)
        self.assertEqual(item_data['attribute_values'][0]['value'], 'A note')

    def test_an_attribute_value_that_fails_its_rule_is_refused(self):
        from apps.projects.factories import ItemAttributeValueFactory, ProjectAttributeFactory
        from apps.projects.models import ItemAttributeValue
        attr_number = ProjectAttributeFactory(project=self.project, name='Effort', field_type='number')
        attr_builtin = ProjectAttributeFactory(project=self.project, name='Fixed', field_type='text', is_builtin=True)
        other_attr = ProjectAttributeFactory(project=ProjectFactory(), name='Other')
        item = ItemFactory(project=self.project, section=self.section, item_id='REQ-001', text='Checked', created_by=self.user)
        ItemAttributeValueFactory(item=item, attribute=self.attr_text, value='Kept')
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        cases = (
            ('wrong type', attr_number.pk, 'soon', 'Effort'),
            ('outside the options', self.attr_dropdown.pk, 'Extreme', 'Risk Level'),
            ('unknown attribute', other_attr.pk, 'Elsewhere', 'attribute_values'),
            ('malformed id', 'garbage', 'Nowhere', 'attribute_values'),
            ('built-in attribute', attr_builtin.pk, 'Fixed', 'Fixed'),
        )
        for case, attribute, value, key in cases:
            with self.subTest(case=case):
                response = self.client.patch(url, data=json.dumps({
                    'attribute_values': [{'attribute': self.attr_text.pk, 'value': 'Changed'}, {'attribute': attribute, 'value': value}],
                }), content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [key])
        self.assertEqual(list(ItemAttributeValue.objects.filter(item=item).values_list('attribute_id', 'value')), [(self.attr_text.pk, 'Kept')])

    def test_the_version_written_by_an_item_create_holds_its_attribute_values(self):
        url = reverse('api_item_list', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'section': self.section.pk, 'text': 'Versioned', 'status': 'draft', 'priority': 'medium',
            'attribute_values': [
                {'attribute': self.attr_dropdown.pk, 'value': 'Low'},
                {'attribute': self.attr_text.pk, 'value': 'A note'},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        item = Item.objects.get(text='Versioned')
        version = ProjectVersion.objects.filter(project=self.project).order_by('-changed_at').first()
        self.assertEqual(version.change_summary, f'Created item {item.item_id}')
        snapshot_item = next(entry for entry in version.snapshot['items'] if entry['id'] == item.pk)
        self.assertEqual(
            sorted((av['attribute_id'], av['value']) for av in snapshot_item['attribute_values']),
            sorted([(self.attr_dropdown.pk, 'Low'), (self.attr_text.pk, 'A note')]),
        )

    def test_update_replaces_attribute_values(self):
        from apps.projects.factories import ItemAttributeValueFactory
        item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-004', text='Replace test', created_by=self.user
        )
        ItemAttributeValueFactory(item=item, attribute=self.attr_text, value='Old')
        url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': item.public_key})
        response = self.client.patch(url, data=json.dumps({
            'attribute_values': [
                {'attribute': self.attr_text.pk, 'value': 'New'},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        from apps.projects.models import ItemAttributeValue
        self.assertEqual(ItemAttributeValue.objects.filter(item=item).count(), 1)
        self.assertEqual(
            ItemAttributeValue.objects.get(item=item).value, 'New'
        )

class MemberPreferencesAPITests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory(created_by=self.user)
        self.membership = ProjectMembershipFactory(
            project=self.project, user=self.user, role='admin'
        )
        self.url = reverse('api_member_preferences', kwargs={'slug': self.project.slug})
        self.client.force_login(self.user)

    def test_get_empty_preferences(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['preferences'], {})

    def test_system_admin_without_membership_gets_empty_preferences(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['preferences'], {})
        response = self.client.patch(self.url, json.dumps({
            'preferences': {'visible_columns': {'1': True}}
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'preferences': {'visible_columns': {'1': True}}, 'stored': False})
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=admin).exists())

    def test_non_member_user_gets_404(self):
        self.client.force_login(UserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 404)
        response = self.client.patch(self.url, json.dumps({'preferences': {}}), content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_patch_preferences(self):
        response = self.client.patch(self.url, json.dumps({
            'preferences': {'visible_columns': {'1': True, '2': False}}
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.preferences['visible_columns'], {'1': True, '2': False})

    def test_patch_merges_preferences(self):
        self.membership.preferences = {'theme': 'dark'}
        self.membership.save()
        response = self.client.patch(self.url, json.dumps({
            'preferences': {'visible_columns': {'3': True}}
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.preferences['theme'], 'dark')
        self.assertEqual(self.membership.preferences['visible_columns'], {'3': True})

    def test_patch_rejects_non_dict(self):
        response = self.client.patch(self.url, json.dumps({
            'preferences': 'not a dict'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
