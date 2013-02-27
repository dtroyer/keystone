# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC
# Copyright 2013 IBM
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

import json
import tempfile
import uuid

import nose.exc

from keystone import config
from keystone.policy.backends import rules

import test_v3


CONF = config.CONF


class IdentityTestProtectedCase(test_v3.RestfulTestCase):
    """Test policy protection of a sample of v3 identity apis"""

    def setUp(self):
        super(IdentityTestProtectedCase, self).setUp()
        # Start by creating a couple of domains
        self.domainA = self.new_domain_ref()
        domainA_ref = self.identity_api.create_domain(self.domainA['id'],
                                                      self.domainA)

        self.domainB = self.new_domain_ref()
        domainB_ref = self.identity_api.create_domain(self.domainB['id'],
                                                      self.domainB)

        # Now create some users, one in domainA and two of them in domainB
        self.user1 = self.new_user_ref(
            domain_id=self.domainA['id'])
        self.user1['password'] = uuid.uuid4().hex
        user_ref = self.identity_api.create_user(self.user1['id'], self.user1)

        self.user2 = self.new_user_ref(
            domain_id=self.domainB['id'])
        self.user2['password'] = uuid.uuid4().hex
        user_ref = self.identity_api.create_user(self.user2['id'], self.user2)

        self.user3 = self.new_user_ref(
            domain_id=self.domainB['id'])
        self.user3['password'] = uuid.uuid4().hex
        user_ref = self.identity_api.create_user(self.user3['id'], self.user3)

        self.project = self.new_project_ref(
            domain_id=self.domainA['id'])
        project_ref = self.identity_api.create_project(self.project['id'],
                                                       self.project)

        self.role = self.new_role_ref()
        self.identity_api.create_role(self.role['id'], self.role)
        self.identity_api.add_role_to_user_and_project(self.user1['id'],
                                                       self.project['id'],
                                                       self.role['id'])
        self.identity_api.create_grant(self.role['id'],
                                       user_id=self.user1['id'],
                                       domain_id=self.domainA['id'])

        # Initialize the policy engine and allow us to write to a temp
        # file in each test to create the policies
        self.orig_policy_file = CONF.policy_file
        rules.reset()
        _unused, self.tmpfilename = tempfile.mkstemp()
        self.opt(policy_file=self.tmpfilename)

        # A default auth request we can use - un-scoped user token
        self.auth = {}
        self.auth['identity'] = {'methods': []}
        self.auth['identity']['methods'].append('password')
        self.auth['identity']['password'] = {'user': {}}
        self.auth['identity']['password']['user']['id'] = (
            self.user1['id'])
        self.auth['identity']['password']['user']['password'] = (
            self.user1['password'])
        self.auth = {'auth': self.auth}

    def tearDown(self):
        super(IdentityTestProtectedCase, self).tearDown()
        rules.reset()
        self.opt(policy_file=self.orig_policy_file)

    def _get_id_list_from_ref_list(self, ref_list):
        result_list = []
        for x in ref_list:
            result_list.append(x['id'])
        return result_list

    def test_list_users_unprotected(self):
        """GET /users (unprotected)"""

        # Make sure we get all the users back if no protection
        # or filtering
        with open(self.tmpfilename, "w") as policyfile:
            policyfile.write("""{"identity:list_users": []}""")
        r = self.get('/users', auth=self.auth)
        id_list = self._get_id_list_from_ref_list(r.body.get('users'))
        self.assertIn(self.user1['id'], id_list)
        self.assertIn(self.user2['id'], id_list)
        self.assertIn(self.user3['id'], id_list)

    def test_list_users_filtered_by_domain(self):
        """GET /users?domain_id=mydomain """

        # Using no protection, make sure filtering works
        with open(self.tmpfilename, "w") as policyfile:
            policyfile.write("""{"identity:list_users": []}""")
        url_by_name = '/users?domain_id=%s' % self.domainB['id']
        r = self.get(url_by_name, auth=self.auth)
        # We should  get back two users, those in DomainB
        id_list = self._get_id_list_from_ref_list(r.body.get('users'))
        self.assertIn(self.user2['id'], id_list)
        self.assertIn(self.user3['id'], id_list)

    def test_list_users_protected_by_domain(self):
        """GET /users?domain_id=mydomain (protected)"""

        # Update policy to protect by domain, and then use a domain
        # scoped token
        new_policy = """{"identity:list_users": ["domain_id:%(domain_id)s"]}"""
        with open(self.tmpfilename, "w") as policyfile:
            policyfile.write(new_policy)
        self.auth['auth']['scope'] = {'domain': {'id': self.domainA['id']}}
        url_by_name = '/users?domain_id=%s' % self.user1['domain_id']
        r = self.get(url_by_name, auth=self.auth)
        # We should only get back one user, the one in DomainA
        id_list = self._get_id_list_from_ref_list(r.body.get('users'))
        self.assertIn(self.user1['id'], id_list)

    def test_get_user_protected_match_id(self):
        """GET /users/{id} (match payload)"""
        # Tests the flattening of the payload
        policy = {"identity:get_user": [["user_id:%(user_id)s"]]}
        with open(self.tmpfilename, "w") as policyfile:
            policyfile.write(json.dumps(policy))
        url_by_name = '/users/%s' % self.user1['id']
        r = self.get(url_by_name, auth=self.auth)
        body = r.body
        self.assertEquals(self.user1['id'], body['user']['id'])
