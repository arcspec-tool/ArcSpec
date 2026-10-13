from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.notifications.factories import AuditLogFactory, NotificationFactory
from apps.projects.factories import (
    OwnedProjectFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)
from apps.notifications.models import Notification

DASHBOARD_URL = 'dashboard:dashboard'
ACTIVITY_FEED_URL = 'dashboard:dashboard_activity_feed'
NOTIFICATIONS_URL = 'dashboard:dashboard_notifications'
AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


class DashboardViewAuthTest(TestCase):

    def test_redirects_anonymous(self):
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.status_code, 302)

    def test_accessible_for_authenticated_user(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.status_code, 200)


class DashboardStatCardsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_active_projects_count(self):
        OwnedProjectFactory(created_by=self.user, status='active')
        OwnedProjectFactory(created_by=self.user, status='active')
        OwnedProjectFactory(created_by=self.user, status='draft')
        ProjectFactory(status='active')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['active_projects_count'], 2)

    def test_approved_items_count(self):
        project = OwnedProjectFactory(created_by=self.user)
        section = SectionFactory(project=project)
        ItemFactory(project=project, section=section, item_id='REQ-001', status='approved')
        ItemFactory(project=project, section=section, item_id='REQ-002', status='approved')
        ItemFactory(project=project, section=section, item_id='REQ-003', status='draft')
        other = ProjectFactory()
        other_section = SectionFactory(project=other)
        ItemFactory(project=other, section=other_section, item_id='REQ-004', status='approved')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['approved_items_count'], 2)

    def test_in_review_items_count(self):
        project = OwnedProjectFactory(created_by=self.user)
        section = SectionFactory(project=project)
        ItemFactory(project=project, section=section, item_id='REQ-001', status='in-review')
        ItemFactory(project=project, section=section, item_id='REQ-002', status='draft')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['in_review_items_count'], 1)

    def test_collaborators_count(self):
        project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=project, user=self.user, role='admin')
        other_user = UserFactory()
        ProjectMembershipFactory(project=project, user=other_user, role='editor')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['collaborators_count'], 1)

    def test_member_projects_counted(self):
        other_project = ProjectFactory(status='active')
        ProjectMembershipFactory(project=other_project, user=self.user, role='editor')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['active_projects_count'], 1)

    def test_system_admin_sees_all_projects(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        ProjectFactory(status='active')
        ProjectFactory(status='active')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(response.context['active_projects_count'], 2)


class DashboardRecentProjectsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_recent_projects_present(self):
        OwnedProjectFactory(created_by=self.user, name='Project A')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertIn('recent_projects', response.context)
        self.assertEqual(len(response.context['recent_projects']), 1)

    def test_recent_projects_excludes_other_users(self):
        OwnedProjectFactory(created_by=self.user, name='Mine')
        ProjectFactory(name='Not Mine')
        response = self.client.get(reverse(DASHBOARD_URL))
        names = [p.name for p in response.context['recent_projects']]
        self.assertIn('Mine', names)
        self.assertNotIn('Not Mine', names)

    def test_recent_projects_limited_to_6(self):
        for i in range(8):
            OwnedProjectFactory(created_by=self.user, name=f'Project {i}')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(len(response.context['recent_projects']), 6)

    def test_recent_projects_ordered_by_updated_at(self):
        p1 = OwnedProjectFactory(created_by=self.user, name='Old')
        p2 = OwnedProjectFactory(created_by=self.user, name='New')
        response = self.client.get(reverse(DASHBOARD_URL))
        projects = list(response.context['recent_projects'])
        self.assertEqual(projects[0], p2)


class DashboardActivityFeedTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_activity_feed_present(self):
        project = OwnedProjectFactory(created_by=self.user)
        AuditLogFactory(project=project, user=self.user, action='created')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertIn('activity_feed', response.context)
        self.assertEqual(len(response.context['activity_feed']), 1)

    def test_activity_excludes_other_projects(self):
        my_project = OwnedProjectFactory(created_by=self.user)
        other_project = ProjectFactory()
        AuditLogFactory(project=my_project, user=self.user)
        AuditLogFactory(project=other_project, user=UserFactory())
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(len(response.context['activity_feed']), 1)

    def test_activity_limited_to_6(self):
        project = OwnedProjectFactory(created_by=self.user)
        for _ in range(15):
            AuditLogFactory(project=project, user=self.user)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(len(response.context['activity_feed']), 6)


class DashboardNotificationsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_notifications_present(self):
        NotificationFactory(user=self.user, is_read=False)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertIn('notifications', response.context)
        self.assertEqual(len(response.context['notifications']), 1)

    def test_notifications_excludes_other_users(self):
        NotificationFactory(user=self.user)
        NotificationFactory(user=UserFactory())
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(len(response.context['notifications']), 1)

    def test_unread_first(self):
        read = NotificationFactory(user=self.user, is_read=True, message='read')
        unread = NotificationFactory(user=self.user, is_read=False, message='unread')
        response = self.client.get(reverse(DASHBOARD_URL))
        notifs = list(response.context['notifications'])
        unread_idx = next(i for i, n in enumerate(notifs) if n == unread)
        read_idx = next(i for i, n in enumerate(notifs) if n == read)
        self.assertLess(unread_idx, read_idx)

    def test_notifications_limited_to_6(self):
        for _ in range(15):
            NotificationFactory(user=self.user)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertEqual(len(response.context['notifications']), 6)

    def test_notification_is_a_link_to_its_target(self):
        NotificationFactory(user=self.user, is_read=False, link='/projects/some-project/')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertContains(response, 'class="dash-row-body notification-link"')
        self.assertContains(response, 'href="/projects/some-project/"')


class DashboardPanelsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_new_project_opens_the_create_modal(self):
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertContains(response, 'data-modal-open="project_create"')

    def test_viewer_is_not_offered_new_project(self):
        viewer = UserFactory(system_role='viewer')
        self.client.force_login(viewer)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertNotContains(response, 'data-modal-open="project_create"')

    def test_dashboard_sets_the_csrf_cookie_for_its_requests(self):
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertIn('csrftoken', response.cookies)

    def test_project_row_counts_items_in_words(self):
        project = OwnedProjectFactory(created_by=self.user, name='Counted')
        section = SectionFactory(project=project)
        ItemFactory(project=project, section=section, item_id='REQ-001')
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertContains(response, '1 item &middot;')

    def test_unread_count_and_mark_all_shown_only_with_unread(self):
        NotificationFactory(user=self.user, is_read=True)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertNotContains(response, 'id="markAllRead"')
        self.assertNotContains(response, 'id="notificationBadge"')
        NotificationFactory(user=self.user, is_read=False)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertContains(response, 'id="markAllRead"')
        self.assertContains(response, 'id="notificationBadge"')


class DashboardLoadMoreActivityTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = OwnedProjectFactory(created_by=self.user)

    def make_rows(self, count, start=0):
        return [
            AuditLogFactory(project=self.project, user=self.user, action='created', target_id=f'REQ-{i:03}')
            for i in range(start, start + count)
        ]

    def load(self, **params):
        return self.client.get(reverse(ACTIVITY_FEED_URL), params, **AJAX)

    def test_button_shown_only_when_more_than_six_exist(self):
        self.make_rows(6)
        self.assertNotContains(self.client.get(reverse(DASHBOARD_URL)), 'id="loadMoreActivity"')
        self.make_rows(1, start=6)
        response = self.client.get(reverse(DASHBOARD_URL))
        self.assertContains(response, 'id="loadMoreActivity"')
        self.assertContains(response, 'data-offset="6"')

    def test_load_more_continues_after_the_first_page(self):
        self.make_rows(15)
        page = self.client.get(reverse(DASHBOARD_URL)).context
        first = [a.target_id for a in page['activity_feed']]
        response = self.load(offset=6, until=page['activity_until'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertFalse(data['has_more'])
        self.assertEqual(data['html'].count('class="dash-row dash-activity"'), 9)
        loaded = [f'REQ-{i:03}' for i in range(15) if f'<span class="dash-target">REQ-{i:03}</span>' in data['html']]
        self.assertEqual(sorted(first + loaded), [f'REQ-{i:03}' for i in range(15)])

    def test_load_more_has_more_flag(self):
        self.make_rows(25)
        self.assertTrue(self.load(offset=5).json()['has_more'])
        self.assertFalse(self.load(offset=15).json()['has_more'])

    def test_rows_created_after_the_page_are_not_loaded(self):
        self.make_rows(8)
        until = self.client.get(reverse(DASHBOARD_URL)).context['activity_until']
        self.make_rows(3, start=8)
        data = self.load(offset=6, until=until).json()
        self.assertEqual(data['html'].count('class="dash-row dash-activity"'), 2)
        self.assertIn('<span class="dash-target">REQ-000</span>', data['html'])
        self.assertNotIn('<span class="dash-target">REQ-010</span>', data['html'])

    def test_excludes_other_projects(self):
        AuditLogFactory(project=ProjectFactory(), user=UserFactory(), target_id='OTHER-1')
        self.make_rows(1)
        html = self.load(offset=0).json()['html']
        self.assertNotIn('OTHER-1', html)
        self.assertEqual(html.count('class="dash-row dash-activity"'), 1)

    def test_invalid_parameters_return_400(self):
        for params in ({'offset': 'abc'}, {'offset': -1}, {'offset': 5, 'until': 'nope'}, {'offset': 5, 'until': '2026-10-10T10:00:00'}):
            self.assertEqual(self.load(**params).status_code, 400, params)

    def test_anonymous_sent_to_sign_in(self):
        self.client.logout()
        response = self.load(offset=5)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response['X-Redirect-To'].startswith('/?next='))


class DashboardLoadMoreNotificationsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def make(self, count, is_read, prefix):
        return [NotificationFactory(user=self.user, is_read=is_read, message=f'{prefix}-{i:02}') for i in range(count)]

    def first_page(self):
        context = self.client.get(reverse(DASHBOARD_URL)).context
        return [n.public_key for n in context['notifications']], context.get('notifications_cursor')

    def load(self, cursor):
        response = self.client.get(reverse(NOTIFICATIONS_URL), cursor, **AJAX)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def keys_in(self, html):
        return [n.public_key for n in Notification.objects.filter(user=self.user) if f'data-notification-id="{n.public_key}"' in html]

    def test_button_shown_only_when_more_than_six_exist(self):
        self.make(6, False, 'u')
        self.assertNotContains(self.client.get(reverse(DASHBOARD_URL)), 'id="loadMoreNotifications"')
        self.make(1, True, 'r')
        self.assertContains(self.client.get(reverse(DASHBOARD_URL)), 'id="loadMoreNotifications"')

    def test_load_more_continues_unread_first(self):
        unread = self.make(3, False, 'u')
        read = self.make(9, True, 'r')
        shown, cursor = self.first_page()
        data = self.load(cursor)
        self.assertFalse(data['has_more'])
        self.assertEqual(data['html'].count('class="dash-row dash-notification'), 6)
        expected = [n.public_key for n in reversed(unread)] + [n.public_key for n in reversed(read)]
        loaded = [k for k in expected if f'data-notification-id="{k}"' in data['html']]
        self.assertEqual(shown + loaded, expected)

    def test_has_more_and_cursor_for_a_long_list(self):
        self.make(30, True, 'r')
        _, cursor = self.first_page()
        data = self.load(cursor)
        self.assertTrue(data['has_more'])
        self.assertEqual(data['html'].count('class="dash-row dash-notification'), 10)
        self.assertEqual(data['cursor']['read'], 1)
        second = self.load(data['cursor'])
        self.assertEqual(second['html'].count('class="dash-row dash-notification'), 10)
        self.assertEqual(set(self.keys_in(data['html'])) & set(self.keys_in(second['html'])), set())

    def test_marking_a_shown_notification_read_skips_no_unread_one(self):
        self.make(8, False, 'u')
        shown, cursor = self.first_page()
        self.client.post(reverse('notification_mark_read', kwargs={'public_key': shown[0]}))
        loaded = self.keys_in(self.load(cursor)['html'])
        all_keys = set(Notification.objects.filter(user=self.user).values_list('public_key', flat=True))
        self.assertEqual(set(shown) | set(loaded), all_keys)

    def test_mark_all_read_skips_nothing(self):
        self.make(4, False, 'u')
        self.make(6, True, 'r')
        shown, cursor = self.first_page()
        self.client.post(reverse('notification_mark_all_read'))
        loaded = self.keys_in(self.load(cursor)['html'])
        all_keys = set(Notification.objects.filter(user=self.user).values_list('public_key', flat=True))
        self.assertEqual(set(shown) | set(loaded), all_keys)

    def test_excludes_other_users(self):
        NotificationFactory(user=UserFactory(), message='someone else')
        self.make(7, False, 'u')
        _, cursor = self.first_page()
        self.assertNotIn('someone else', self.load(cursor)['html'])

    def test_invalid_cursor_returns_400(self):
        good = {'read': '0', 'before': '2026-10-10T10:00:00+00:00', 'key': '0192a6b0-0000-7000-8000-000000000000'}
        for change in ({'read': '2'}, {'before': 'nope'}, {'before': '2026-10-10T10:00:00'}, {'key': '12'}, {'key': None}):
            params = {k: v for k, v in {**good, **change}.items() if v is not None}
            response = self.client.get(reverse(NOTIFICATIONS_URL), params, **AJAX)
            self.assertEqual(response.status_code, 400, change)

    def test_anonymous_sent_to_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse(NOTIFICATIONS_URL), {'read': '0'}, **AJAX)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response['X-Redirect-To'].startswith('/?next='))
