import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import (
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TagFactory,
)


class ProjectDetailViewTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        self.membership = ProjectMembershipFactory(
            project=self.project, user=self.user, role='admin'
        )
        self.section = SectionFactory(project=self.project, number='1', title='Introduction')
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', text='Test requirement', created_by=self.user
        )
        self.url = reverse('project_detail', kwargs={'slug': self.project.slug})

    def test_detail_view_accessible_to_member(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_carries_the_modal_targets_and_no_modal_markup(self):
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('id="modalTarget"'), 1)
        self.assertEqual(html.count('id="confirmTarget"'), 1)
        self.assertNotIn('modal fade', html)
        self.assertNotIn('data-bs-toggle="modal"', html)
        for name in ('add_item', 'save_view', 'export', 'add_link', 'manage_sections', 'collaborators'):
            self.assertIn(f'data-modal-open="{name}" data-project="{self.project.slug}"', html, name)
        self.assertIn(f'data-section-key="{self.section.public_key}"', html)

    def test_editor_page_carries_the_item_menu_with_a_trigger_per_item(self):
        from apps.projects.factories import PresetTagFactory
        from apps.projects.models import Item
        ItemFactory(project=self.project, section=self.section, item_id='REQ-002', text='Second', created_by=self.user)
        project_tag = TagFactory(project=self.project, name='Project Tag')
        preset = PresetTagFactory(name='Preset Tag')
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('id="itemMenu"'), 1)
        self.assertIn('data-menu-context="itemMenu" data-menu-context-target="tr.item-row[data-key]"', html)
        self.assertEqual(html.count('data-menu-open="itemMenu"'), 3)
        self.assertEqual(html.count('class="menu menu-sub"'), 3)
        for value, label in Item.STATUS_CHOICES:
            self.assertIn(f'role="menuitemradio" aria-checked="false" tabindex="-1" data-action="set-status" data-value="{value}"', html)
        for value, label in Item.PRIORITY_CHOICES:
            self.assertIn(f'role="menuitemradio" aria-checked="false" tabindex="-1" data-action="set-priority" data-value="{value}"', html)
        for tag in (project_tag, preset):
            self.assertEqual(html.count(f'data-action="set-tag" data-value="{tag.pk}" data-tag-name="{tag.name}"'), 2)
        self.assertEqual(html.count('id="detailTagsMenu"'), 1)
        self.assertIn('colspan="7"', html)
        self.assertNotIn('colspan="6"', html)

    def test_detail_page_sets_the_csrf_cookie_for_its_api_calls(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertIn('csrftoken', response.cookies)

    def test_viewer_page_carries_no_item_menu(self):
        self.membership.role = 'viewer'
        self.membership.save()
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('id="itemMenu"', html)
        self.assertNotIn('data-menu-open="itemMenu"', html)
        self.assertNotIn('data-menu-context', html)
        self.assertNotIn('id="detailTagsMenu"', html)
        self.assertIn('colspan="6"', html)
        self.assertNotIn('class="col-actions"', html)

    def test_detail_view_returns_404_for_nonmember(self):
        other = UserFactory()
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_detail_view_accessible_to_system_admin(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_detail_context_has_user_role(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.context['user_role'], 'admin')
        self.assertTrue(response.context['is_editor'])
        self.assertTrue(response.context['is_admin'])

    def test_viewer_role_context(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.context['user_role'], 'viewer')
        self.assertFalse(response.context['is_editor'])
        self.assertFalse(response.context['is_admin'])

    def test_detail_context_has_section_data(self):
        self.section.description = 'Intro description'
        self.section.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertIn('section_data', response.context)
        section_data = response.context['section_data']
        section_entry = section_data[str(self.section.pk)]
        self.assertEqual(section_entry['title'], 'Introduction')
        self.assertEqual(section_entry['description'], 'Intro description')
        self.assertEqual(section_entry['number'], '1')

    def test_section_title_script_injection_escaped(self):
        self.section.title = '</script><img src=x onerror=alert(1)><script>//'
        self.section.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '</script><img src=x onerror=alert(1)>')

    def test_page_names_the_project_and_links_back_to_the_list(self):
        self.project.name = 'Payment Gateway'
        self.project.status = 'in-review'
        self.project.save()
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn('<nav class="topbar-context" aria-label="Breadcrumb">', html)
        self.assertIn(f'<a href="{reverse("project_list")}" class="topbar-context-parent">Projects</a>', html)
        self.assertIn('<h1 class="topbar-context-title" title="Payment Gateway">Payment Gateway</h1>', html)
        self.assertIn('<span class="status-pill status-in-review">In Review</span>', html)
        self.assertEqual(html.count('<h1'), 1)

    def test_other_pages_carry_no_project_context(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('project_list')).content.decode()
        self.assertNotIn('topbar-context', html)

    def test_tree_counts_include_subsections_and_omit_empty_sections(self):
        parent = SectionFactory(project=self.project, number='2', title='Overall', order=1)
        child = SectionFactory(project=self.project, number='2.1', title='Perspective', parent=parent, order=2)
        SectionFactory(project=self.project, number='3', title='Empty', order=3)
        for n in range(2):
            ItemFactory(project=self.project, section=child, item_id=f'REQ-10{n}', created_by=self.user)
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn('title="2 items in this section and its subsections">2</span>', html)
        self.assertIn('title="2 items">2</span>', html)
        self.assertIn('title="1 item">1</span>', html)
        self.assertEqual(html.count('class="tree-count"'), 3)
        self.assertIsNone(re.search(r'<div class="tree-node[^>]*draggable', html))

    def test_section_data_carries_the_key_and_the_item_total(self):
        child = SectionFactory(project=self.project, number='1.1', title='Purpose', parent=self.section, order=1)
        ItemFactory(project=self.project, section=child, item_id='REQ-002', created_by=self.user)
        self.client.force_login(self.user)
        data = self.client.get(self.url).context['section_data']
        self.assertEqual(data[str(self.section.pk)]['key'], str(self.section.public_key))
        self.assertEqual(data[str(self.section.pk)]['total_items'], 2)
        self.assertEqual(data[str(child.pk)]['total_items'], 1)

    def test_query_count_does_not_grow_with_sections_items_or_tags(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from apps.projects.models import ItemTag
        tag = TagFactory(project=self.project, name='Security')
        ItemTag.objects.create(item=self.item, tag=tag)
        self.client.force_login(self.user)
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url)
        for n in range(2, 8):
            section = SectionFactory(project=self.project, number=str(n), title=f'Section {n}', order=n)
            item = ItemFactory(project=self.project, section=section, item_id=f'REQ-0{n}0', created_by=self.user)
            ItemTag.objects.create(item=item, tag=tag)
        with CaptureQueriesContext(connection) as large:
            self.client.get(self.url)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))

    def test_footer_lists_statuses_in_workflow_order_with_their_labels(self):
        self.item.status = 'approved'
        self.item.save()
        ItemFactory(project=self.project, section=self.section, item_id='REQ-002', status='in-review', created_by=self.user)
        ItemFactory(project=self.project, section=self.section, item_id='REQ-003', status='draft', created_by=self.user)
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        footer = html[html.index('id="statusSummary"'):html.index('id="itemCount"')]
        self.assertLess(footer.index('1 Draft'), footer.index('1 In Review'))
        self.assertLess(footer.index('1 In Review'), footer.index('1 Approved'))
        self.assertNotIn('In-Review', html)
        self.assertIn('status-progress-segment status-fill-in-review', html)

    def test_section_details_offer_adding_an_item_to_editors_only(self):
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="sectionAddItemBtn" data-modal-open="add_item" data-project="{}" data-section=""'.format(self.project.slug), html)
        self.membership.role = 'viewer'
        self.membership.save()
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('sectionAddItemBtn', html)

    def test_section_description_script_injection_escaped(self):
        self.section.description = '</script><div id="XSS">pwned</div><script>//'
        self.section.save()
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '</script><div id="XSS">pwned</div>')


class ProjectExportViewTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(
            project=self.project, section=self.section,
            item_id='REQ-001', created_by=self.user
        )
        self.url = reverse('project_export', kwargs={'slug': self.project.slug})

    def test_export_requires_login(self):
        response = self.client.post(self.url, {'format': 'pdf'})
        self.assertNotEqual(response.status_code, 200)

    def test_export_pdf(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'format': 'pdf'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_docx(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'format': 'docx'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('wordprocessingml', response['Content-Type'])

    def test_export_nonmember_gets_404(self):
        other = UserFactory()
        self.client.force_login(other)
        response = self.client.post(self.url, {'format': 'pdf'})
        self.assertEqual(response.status_code, 404)

    def test_export_pdf_rejects_invalid_paper_size(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'format': 'pdf',
            'paper_size': 'a4; } body { background: url(http://evil.com) } @page { size: a4',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_pdf_rejects_invalid_orientation(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'format': 'pdf',
            'orientation': 'portrait; } body { background: url(http://evil.com) } @page { size: a4',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_pdf_valid_paper_sizes_accepted(self):
        self.client.force_login(self.user)
        for size in ('a4', 'letter', 'legal', 'a3', 'A4', 'LETTER'):
            response = self.client.post(self.url, {
                'format': 'pdf', 'paper_size': size,
            })
            self.assertEqual(response.status_code, 200, f'Failed for paper_size={size}')


class ExportInputSanitizationUnitTests(TestCase):

    def test_restricted_url_fetcher_blocks_http(self):
        from apps.projects.export import _restricted_url_fetcher
        with self.assertRaises(ValueError):
            _restricted_url_fetcher().fetch('http://169.254.169.254/latest/meta-data/')

    def test_restricted_url_fetcher_blocks_file(self):
        from apps.projects.export import _restricted_url_fetcher
        with self.assertRaises(ValueError):
            _restricted_url_fetcher().fetch('file:///etc/passwd')

    def test_restricted_url_fetcher_allows_data_uri(self):
        from apps.projects.export import _restricted_url_fetcher
        response = _restricted_url_fetcher().fetch('data:text/plain;base64,SGVsbG8=')
        self.assertEqual(response.read(), b'Hello')
