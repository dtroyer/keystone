# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import uuid

from keystone import config
from keystone import exception
from keystone import tests


CONF = config.CONF


class ConfigTestCase(tests.TestCase):
    def test_paste_config(self):
        self.assertEqual(config.find_paste_config(),
                         tests.dirs.etc('keystone-paste.ini'))
        self.opt_in_group('paste_deploy', config_file=uuid.uuid4().hex)
        self.assertRaises(exception.ConfigFileNotFound,
                          config.find_paste_config)
        self.opt_in_group('paste_deploy', config_file='')
        self.assertEqual(config.find_paste_config(),
                         tests.dirs.etc('keystone.conf.sample'))

    def test_config_default(self):
        self.assertEqual('keystone.auth.plugins.password.Password',
                         CONF.auth.password)
        self.assertEqual('keystone.auth.plugins.token.Token',
                         CONF.auth.token)


class DeprecatedTestCase(tests.TestCase):
    """Test using the original (deprecated) name for renamed options."""

    def setUp(self):
        super(DeprecatedTestCase, self).setUp()
        self.config([tests.dirs.etc('keystone.conf.sample'),
                     tests.dirs.tests('test_overrides.conf'),
                     tests.dirs.tests('deprecated.conf'), ])

    def test_sql(self):
        # Options in [sql] were moved to [database] in Icehouse for the change
        # to use oslo-incubator's db.sqlalchemy.sessions.

        self.assertEqual(CONF.database.connection, 'sqlite://deprecated')
        self.assertEqual(CONF.database.idle_timeout, 54321)


class DeprecatedOverrideTestCase(tests.TestCase):
    """Test using the deprecated AND new name for renamed options."""

    def setUp(self):
        super(DeprecatedOverrideTestCase, self).setUp()
        self.config([tests.dirs.etc('keystone.conf.sample'),
                     tests.dirs.tests('test_overrides.conf'),
                     tests.dirs.tests('deprecated_override.conf'), ])

    def test_sql(self):
        # Options in [sql] were moved to [database] in Icehouse for the change
        # to use oslo-incubator's db.sqlalchemy.sessions.

        self.assertEqual(CONF.database.connection, 'sqlite://new')
        self.assertEqual(CONF.database.idle_timeout, 65432)
