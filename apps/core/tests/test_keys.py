import time
import uuid

from django.test import TestCase, override_settings
from django.urls import Resolver404, get_resolver, resolve, reverse
from django.urls.converters import IntConverter, UUIDConverter
from django.urls.resolvers import URLResolver

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.tests.test_auth_methods import set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.core.keys import uuid7
from apps.projects.factories import ProjectFactory, ProjectMembershipFactory

KEYED_ROUTES = {
    'admin_deactivate_user',
    'admin_edit_role',
    'admin_resend_invitation',
    'admin_tag_preset_delete',
    'admin_template_toggle_visibility',
    'api_attachment_delete',
    'api_attachment_list',
    'api_collaborator_update',
    'api_comment_delete',
    'api_comment_list',
    'api_item_detail',
    'api_item_image',
    'api_item_inline_edit',
    'api_item_tags',
    'api_link_delete',
    'api_link_list',
    'api_project_attribute_detail',
    'api_saved_view_delete',
    'api_version_restore',
    'attachment_download',
    'item_image',
    'mcp_disconnect',
    'notification_mark_read',
    'section_delete',
    'section_update',
    'set_password',
    'template_delete',
    'template_duplicate',
    'template_edit',
}

METHODS = ('get', 'post', 'put', 'patch', 'delete')


def routes():
    found = []

    def walk(patterns, prefix):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
            else:
                found.append((pattern.name, prefix + str(pattern.pattern), pattern.pattern.converters))

    walk(get_resolver().url_patterns, '')
    return found


class Uuid7Test(TestCase):

    def test_keys_are_version_7_rfc_variant_uuids(self):
        key = uuid7()
        self.assertIsInstance(key, uuid.UUID)
        self.assertEqual(key.version, 7)
        self.assertEqual(key.variant, uuid.RFC_4122)

    def test_keys_order_by_time_and_do_not_repeat(self):
        first = uuid7()
        time.sleep(0.002)
        second = uuid7()
        self.assertLess(first, second)
        self.assertEqual(len({uuid7() for _ in range(1000)}), 1000)


class PublicKeyColumnTest(TestCase):

    def test_rows_get_distinct_keys_without_being_asked(self):
        users = [UserFactory() for _ in range(3)]
        keys = {u.public_key for u in users}
        self.assertEqual(len(keys), 3)
        for user in users:
            self.assertEqual(user.public_key.version, 7)


class RouteKeyTest(TestCase):

    def test_no_route_takes_an_integer(self):
        offenders = [route for name, route, converters in routes() if any(isinstance(c, IntConverter) for c in converters.values())]
        self.assertEqual(offenders, [])

    def test_the_keyed_routes_are_exactly_the_known_set(self):
        keyed = {name for name, route, converters in routes() if any(isinstance(c, UUIDConverter) for c in converters.values())}
        self.assertEqual(keyed, KEYED_ROUTES)
        for name, route, converters in routes():
            for parameter, converter in converters.items():
                if isinstance(converter, UUIDConverter):
                    self.assertIn(parameter, ('public_key', 'item_key'), route)


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class UnknownKeyTest(TestCase):

    def setUp(self):
        set_methods(True, True)
        self.admin = AdminUserFactory()
        self.project = ProjectFactory(created_by=self.admin)
        ProjectMembershipFactory(project=self.project, user=self.admin, role='admin')
        self.client.force_login(self.admin)

    def url_for(self, name, converters, key):
        kwargs = {}
        for parameter, converter in converters.items():
            if isinstance(converter, UUIDConverter):
                kwargs[parameter] = key
            elif parameter == 'slug':
                kwargs[parameter] = self.project.slug
            elif parameter == 'token':
                kwargs[parameter] = 'abcdef-0123456789abcdef0123456789abcdef'
        return reverse(name, kwargs=kwargs)

    def keyed_routes(self):
        return [(name, converters) for name, route, converters in routes() if name in KEYED_ROUTES]

    def test_every_keyed_route_is_404_for_a_key_that_matches_nothing(self):
        for name, converters in self.keyed_routes():
            if name == 'set_password':
                continue
            with self.subTest(route=name):
                url = self.url_for(name, converters, uuid7())
                statuses = {method: getattr(self.client, method)(url).status_code for method in METHODS}
                self.assertTrue(set(statuses.values()) <= {404, 405}, statuses)
                self.assertIn(404, statuses.values(), statuses)

    def test_the_set_password_route_shows_the_invalid_page_for_a_key_that_matches_nothing(self):
        self.client.logout()
        url = reverse('set_password', kwargs={'public_key': uuid7(), 'token': 'abcdef-0123456789abcdef0123456789abcdef'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/set_password_invalid.html')

    def test_every_keyed_route_refuses_an_integer_in_place_of_the_key(self):
        for name, converters in self.keyed_routes():
            with self.subTest(route=name):
                url = self.url_for(name, converters, uuid7())
                integer_url = url.replace(str(next(iter(k for k in url.split('/') if len(k) == 36))), '12345')
                with self.assertRaises(Resolver404):
                    resolve(integer_url)
                self.assertEqual(self.client.get(integer_url).status_code, 404)
                self.assertEqual(self.client.post(integer_url).status_code, 404)
