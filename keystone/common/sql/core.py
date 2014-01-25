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

"""SQL backends for the various services.

Before using this module, call initialize(). This has to be done before
CONF() because it sets up configuration options.

"""
import contextlib
import functools

import six
import sqlalchemy as sql
from sqlalchemy.ext import declarative
from sqlalchemy.orm.attributes import flag_modified, InstrumentedAttribute
from sqlalchemy import types as sql_types

from keystone.common import utils
from keystone import exception
from keystone.openstack.common.db import exception as db_exception
from keystone.openstack.common.db.sqlalchemy import models
from keystone.openstack.common.db.sqlalchemy import session
from keystone.openstack.common import jsonutils


ModelBase = declarative.declarative_base()


# For exporting to other modules
Column = sql.Column
Index = sql.Index
String = sql.String
ForeignKey = sql.ForeignKey
DateTime = sql.DateTime
IntegrityError = sql.exc.IntegrityError
OperationalError = sql.exc.OperationalError
NotFound = sql.orm.exc.NoResultFound
Boolean = sql.Boolean
Text = sql.Text
UniqueConstraint = sql.UniqueConstraint
relationship = sql.orm.relationship
joinedload = sql.orm.joinedload
# Suppress flake8's unused import warning for flag_modified:
flag_modified = flag_modified


def initialize():
    """Initialize the module."""

    session.set_defaults(
        sql_connection="sqlite:///keystone.db",
        sqlite_db="keystone.db")


def initialize_decorator(init):
    """Ensure that the length of string field do not exceed the limit.

    This decorator check the initialize arguments, to make sure the
    length of string field do not exceed the length limit, or raise a
    'StringLengthExceeded' exception.

    Use decorator instead of inheritance, because the metaclass will
    check the __tablename__, primary key columns, etc. at the class
    definition.

    """
    def initialize(self, *args, **kwargs):
        cls = type(self)
        for k, v in kwargs.items():
            if hasattr(cls, k):
                attr = getattr(cls, k)
                if isinstance(attr, InstrumentedAttribute):
                    column = attr.property.columns[0]
                    if isinstance(column.type, String):
                        if not isinstance(v, unicode):
                            v = str(v)
                        if column.type.length and \
                                column.type.length < len(v):
                            raise exception.StringLengthExceeded(
                                string=v, type=k, length=column.type.length)

        init(self, *args, **kwargs)
    return initialize

ModelBase.__init__ = initialize_decorator(ModelBase.__init__)


# Special Fields
class JsonBlob(sql_types.TypeDecorator):

    impl = sql.Text

    def process_bind_param(self, value, dialect):
        return jsonutils.dumps(value)

    def process_result_value(self, value, dialect):
        return jsonutils.loads(value)


class DictBase(models.ModelBase):
    attributes = []

    @classmethod
    def from_dict(cls, d):
        new_d = d.copy()

        new_d['extra'] = dict((k, new_d.pop(k)) for k in six.iterkeys(d)
                              if k not in cls.attributes and k != 'extra')

        return cls(**new_d)

    def to_dict(self, include_extra_dict=False):
        """Returns the model's attributes as a dictionary.

        If include_extra_dict is True, 'extra' attributes are literally
        included in the resulting dictionary twice, for backwards-compatibility
        with a broken implementation.

        """
        d = self.extra.copy()
        for attr in self.__class__.attributes:
            d[attr] = getattr(self, attr)

        if include_extra_dict:
            d['extra'] = self.extra.copy()

        return d

    def __getitem__(self, key):
        if key in self.extra:
            return self.extra[key]
        return getattr(self, key)


# Backends
class Base(object):
    get_session = session.get_session

    @contextlib.contextmanager
    def transaction(self, expire_on_commit=False):
        """Return a SQLAlchemy session in a scoped transaction."""
        session = self.get_session(expire_on_commit=expire_on_commit)
        with session.begin():
            yield session

    def _filter(self, model, query, hints):
        """Applies filtering to a query.

        :param model: the table model in question
        :param query: query to apply filters to
        :param hints: contains the list of filters yet to be satisfied.
                      Any filters satisfied here will be removed so that
                      the caller will know if any filters remain.

        :returns query: query, updated with any filters satisfied

        """
        def inexact_filter(model, query, filter, hints):
            """Applies an inexact filter to a query.

            :param model: the table model in question
            :param query: query to apply filters to
            :param filter: the dict that describes this filter
            :param hints: contains the list of filters yet to be satisfied.
                          Any filters satisfied here will be removed so that
                          the caller will know if any filters remain.

            :returns query: query updated to add any inexact filters we could
                            satisfy

            """
            column_attr = getattr(model, filter['name'])

            # TODO(henry-nash): Sqlalchemy 0.7 defaults to case insensitivity
            # so once we find a way of changing that (maybe on a call-by-call
            # basis), we can add support for the case sensitive versions of
            # the filters below.  For now, these case sensitive versions will
            # be handled at the controller level.

            if filter['case_sensitive']:
                return query

            if filter['comparator'] == 'contains':
                query_term = column_attr.ilike('%%%s%%' % filter['value'])
            elif filter['comparator'] == 'startswith':
                query_term = column_attr.ilike('%s%%' % filter['value'])
            elif filter['comparator'] == 'endswith':
                query_term = column_attr.ilike('%%%s' % filter['value'])
            else:
                # It's a filter we don't understand, so let the caller
                # work out if they need to do something with it.
                return query

            hints.remove(filter)
            return query.filter(query_term)

        def exact_filter(model, filter, cumlative_filter_dict, hints):
            """Applies an exact filter to a query.

            :param model: the table model in question
            :param filter: the dict that describes this filter
            :param cumlative_filter_dict: a dict that describes the set of
                                          exact filters built up so far
            :param hints: contains the list of filters yet to be satisfied.
                          Any filters satisfied here will be removed so that
                          the caller will know if any filters remain.

            :returns cumlative_filter_dict: updated cumulative dict

            """
            key = filter['name']
            if isinstance(getattr(model, key).property.columns[0].type,
                          sql.types.Boolean):
                filter_dict[key] = utils.attr_as_boolean(filter['value'])
            else:
                filter_dict[key] = filter['value']
            hints.remove(filter)
            return filter_dict

        filter_dict = {}

        for filter in hints.filters():
            # TODO(henry-nash): Check if name is valid column, if not skip
            if filter['comparator'] == 'equals':
                filter_dict = exact_filter(model, filter, filter_dict, hints)
            else:
                query = inexact_filter(model, query, filter, hints)

        # Apply any exact filters we built up
        if filter_dict:
            query = query.filter_by(**filter_dict)

        return query

    def filter(self, model, query, hints):
        """Applies filtering to a query.

        :param model: table model
        :param query: query to apply filters to
        :param hints: contains the list of filters yet to be satisfied.
                      Any filters satisfied here will be removed so that
                      the caller will know if any filters remain.

        :returns updated query

        """
        if hints is not None:
            query = self._filter(model, query, hints)

        return query


def handle_conflicts(conflict_type='object'):
    """Converts select sqlalchemy exceptions into HTTP 409 Conflict."""
    def decorator(method):
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            except db_exception.DBDuplicateEntry as e:
                raise exception.Conflict(type=conflict_type, details=str(e))
            except db_exception.DBError as e:
                # TODO(blk-u): inspecting inner_exception breaks encapsulation;
                # oslo.db should provide exception we need.
                if isinstance(e.inner_exception, IntegrityError):
                    raise exception.Conflict(type=conflict_type,
                                             details=str(e))
                raise

        return wrapper
    return decorator
