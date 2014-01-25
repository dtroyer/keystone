# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import datetime
import uuid

from keystone import config
from keystone import exception
from keystone import identity
from keystone.openstack.common import timeutils
from keystone import tests
from keystone.tests import default_fixtures
from keystone.tests import test_backend

CONF = config.CONF


class KvsIdentity(tests.TestCase, test_backend.IdentityTests):
    def setUp(self):
        super(KvsIdentity, self).setUp()
        identity.CONF.identity.driver = (
            'keystone.identity.backends.kvs.Identity')
        self.load_backends()
        self.load_fixtures(default_fixtures)

    def test_list_projects_for_user_with_grants(self):
        self.skipTest('kvs backend is now deprecated')

    def test_create_duplicate_group_name_in_different_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_create_duplicate_user_name_in_different_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_create_duplicate_project_name_in_different_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_user_between_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_user_between_domains_with_clashing_names_fails(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_group_between_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_group_between_domains_with_clashing_names_fails(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_project_between_domains(self):
        self.skipTest('Blocked by bug 1119770')

    def test_move_project_between_domains_with_clashing_names_fails(self):
        self.skipTest('Blocked by bug 1119770')

    def test_delete_user_grant_no_user(self):
        # See bug 1239476, kvs checks if user exists and sql does not.
        self.assertRaises(
            exception.UserNotFound,
            super(KvsIdentity, self).test_delete_user_grant_no_user)

    def test_delete_group_grant_no_group(self):
        # See bug 1239476, kvs checks if group exists and sql does not.
        self.assertRaises(
            exception.GroupNotFound,
            super(KvsIdentity, self).test_delete_group_grant_no_group)


class KvsToken(tests.TestCase, test_backend.TokenTests):
    def setUp(self):
        super(KvsToken, self).setUp()
        identity.CONF.identity.driver = (
            'keystone.identity.backends.kvs.Identity')
        self.load_backends()

    def test_flush_expired_token(self):
        self.assertRaises(exception.NotImplemented,
                          self.token_api.flush_expired_tokens)

    def _update_user_token_index_direct(self, user_key, token_id, new_data):
        token_list = self.token_api.driver._get_user_token_list_with_expiry(
            user_key)
        # Update the user-index so that the expires time is _actually_ expired
        # since we do not do an explicit get on the token, we only reference
        # the data in the user index (to save extra round-trips to the kvs
        # backend).
        for i, data in enumerate(token_list):
            if data[0] == token_id:
                token_list[i] = new_data
                break
        self.token_api.driver._store.set(user_key, token_list)

    def test_cleanup_user_index_on_create(self):
        user_id = unicode(uuid.uuid4().hex)
        valid_token_id, data = self.create_token_sample_data(user_id=user_id)
        expired_token_id, expired_data = self.create_token_sample_data(
            user_id=user_id)

        expire_delta = datetime.timedelta(seconds=86400)

        # NOTE(morganfainberg): Directly access the data cache since we need to
        # get expired tokens as well as valid tokens. token_api.list_tokens()
        # will not return any expired tokens in the list.
        user_key = self.token_api.driver._prefix_user_id(user_id)
        user_token_list = self.token_api.driver._store.get(user_key)
        valid_token_ref = self.token_api.get_token(valid_token_id)
        expired_token_ref = self.token_api.get_token(expired_token_id)
        expected_user_token_list = [
            (valid_token_id, timeutils.isotime(valid_token_ref['expires'],
                                               subsecond=True)),
            (expired_token_id, timeutils.isotime(expired_token_ref['expires'],
                                                 subsecond=True))]
        self.assertEqual(user_token_list, expected_user_token_list)
        new_expired_data = (expired_token_id,
                            timeutils.isotime(
                                (timeutils.utcnow() - expire_delta),
                                subsecond=True))
        self._update_user_token_index_direct(user_key, expired_token_id,
                                             new_expired_data)
        valid_token_id_2, valid_data_2 = self.create_token_sample_data(
            user_id=user_id)
        valid_token_ref_2 = self.token_api.get_token(valid_token_id_2)
        expected_user_token_list = [
            (valid_token_id, timeutils.isotime(valid_token_ref['expires'],
                                               subsecond=True)),
            (valid_token_id_2, timeutils.isotime(valid_token_ref_2['expires'],
                                                 subsecond=True))]
        user_token_list = self.token_api.driver._store.get(user_key)
        self.assertEqual(user_token_list, expected_user_token_list)

        # Test that revoked tokens are removed from the list on create.
        self.token_api.delete_token(valid_token_id_2)
        new_token_id, data = self.create_token_sample_data(user_id=user_id)
        new_token_ref = self.token_api.get_token(new_token_id)
        expected_user_token_list = [
            (valid_token_id, timeutils.isotime(valid_token_ref['expires'],
                                               subsecond=True)),
            (new_token_id, timeutils.isotime(new_token_ref['expires'],
                                             subsecond=True))]
        user_token_list = self.token_api.driver._store.get(user_key)
        self.assertEqual(user_token_list, expected_user_token_list)


class KvsTrust(tests.TestCase, test_backend.TrustTests):
    def setUp(self):
        super(KvsTrust, self).setUp()
        identity.CONF.identity.driver = (
            'keystone.identity.backends.kvs.Identity')
        identity.CONF.trust.driver = (
            'keystone.trust.backends.kvs.Trust')
        identity.CONF.catalog.driver = (
            'keystone.catalog.backends.kvs.Catalog')
        self.load_backends()
        self.load_fixtures(default_fixtures)


class KvsCatalog(tests.TestCase, test_backend.CatalogTests):
    def setUp(self):
        super(KvsCatalog, self).setUp()
        identity.CONF.identity.driver = (
            'keystone.identity.backends.kvs.Identity')
        identity.CONF.trust.driver = (
            'keystone.trust.backends.kvs.Trust')
        identity.CONF.catalog.driver = (
            'keystone.catalog.backends.kvs.Catalog')
        self.load_backends()
        self._load_fake_catalog()

    def _load_fake_catalog(self):
        self.catalog_foobar = self.catalog_api.driver._create_catalog(
            'foo', 'bar',
            {'RegionFoo': {'service_bar': {'foo': 'bar'}}})

    def test_get_catalog_404(self):
        # FIXME(dolph): this test should be moved up to test_backend
        # FIXME(dolph): exceptions should be UserNotFound and ProjectNotFound
        self.assertRaises(exception.NotFound,
                          self.catalog_api.get_catalog,
                          uuid.uuid4().hex,
                          'bar')

        self.assertRaises(exception.NotFound,
                          self.catalog_api.get_catalog,
                          'foo',
                          uuid.uuid4().hex)

    def test_get_catalog(self):
        catalog_ref = self.catalog_api.get_catalog('foo', 'bar')
        self.assertDictEqual(catalog_ref, self.catalog_foobar)


class KvsTokenCacheInvalidation(tests.TestCase,
                                test_backend.TokenCacheInvalidation):
    def setUp(self):
        super(KvsTokenCacheInvalidation, self).setUp()
        CONF.identity.driver = 'keystone.identity.backends.kvs.Identity'
        CONF.token.driver = 'keystone.token.backends.kvs.Token'
        self.load_backends()
        self._create_test_data()
