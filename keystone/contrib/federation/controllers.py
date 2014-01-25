# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

"""Extensions supporting Federation."""

from keystone.common import controller
from keystone.common import dependency
from keystone.common import wsgi
from keystone import config
from keystone.contrib.federation import utils
from keystone import exception


CONF = config.CONF


@dependency.requires('federation_api')
class IdentityProvider(controller.V3Controller):
    """Identity Provider representation.

    Two new class parameters:
    - _mutable_parameters - set of parameters that can be changed by users.
                            Usually used by cls.check_immutable_params()
    - _public_parameters - set of parameters that exposed to the user.
                           Usually used by cls.filter_params()

    """
    collection_name = 'identity_providers'
    member_name = 'identity_provider'

    _mutable_parameters = frozenset(['description', 'enabled'])
    _public_parameters = frozenset(['id', 'enabled', 'description', 'links'])

    @classmethod
    def check_immutable_params(cls, ref, keys=None):
        """Raise exception when disallowed parameter is stored in the keys

        Check whether the ref dictionary representing a request has only
        mutable parameters included. If not, raise an exception. This method
        checks only root-level keys from a ref dictionary.

        :param ref: a dictionary representing deserialized request to be
                    stored
        :param keys: a set with mutable parameters. If None, use default class
                     attribute - _mutable_parameters
        :raises exception.ImmutableAttributeError

        """
        if keys is None:
            keys = cls._mutable_parameters

        ref_keys = set(ref.keys())
        blocked_keys = ref_keys.difference(keys)

        if not blocked_keys:
            #No immutable parameters changed
            return

        exception_args = {'target': cls.__name__,
                          'attribute': blocked_keys.pop()}
        raise exception.ImmutableAttributeError(**exception_args)

    @classmethod
    def filter_params(cls, ref, keys=None):
        """Remove unspecified parameters from the dictionary.

        This function removes unspecified parameters from the dictionary. See
        check_immutable_parameters for corresponding function that raises
        exceptions. This method checks only root-level keys from a ref
        dictionary.

        :param ref: a dictionary representing deserialized response to be
                    serialized
        :param keys: a set of attribute names, that are allowed in the request.
                     If None, use the class attribute _public_parameters

        """
        if keys is None:
            keys = cls._public_parameters
        ref_keys = set(ref.keys())
        blocked_keys = ref_keys - keys
        for blocked_param in blocked_keys:
            del ref[blocked_param]
        return ref

    @classmethod
    def base_url(cls, path=None):
        """Construct a path and pass it to V3Controller.base_url method."""

        path = '/OS-FEDERATION/' + cls.collection_name
        return controller.V3Controller.base_url(path=path)

    @classmethod
    def _add_related_links(cls, ref):
        """Add URLs for entities related with Identity Provider.

        Add URLs pointing to:
        - protocols tied to the Identity Provider

        """
        ref.setdefault('links', {})
        base_path = ref['links'].get('self')
        if base_path is None:
            base_path = '/'.join([IdentityProvider.base_url(), ref['id']])
        for name in ['protocols']:
            ref['links'][name] = '/'.join([base_path, name])

    @classmethod
    def _add_self_referential_link(cls, ref):
        id = ref.get('id')
        self_path = '/'.join([cls.base_url(), id])
        ref.setdefault('links', {})
        ref['links']['self'] = self_path

    @classmethod
    def wrap_member(cls, context, ref):
        cls._add_self_referential_link(ref)
        cls._add_related_links(ref)
        return {cls.member_name: ref}

    #TODO(marek-denis): Implement, when mapping engine is ready
    def _delete_tokens_issued_by_idp(self, idp_id):
        """Delete tokens created upon authentication from an IdP

        After the IdP is deregistered, users authenticating via such IdP should
        no longer be allowed to use federated services. Thus, delete all the
        tokens issued upon authentication from IdP with idp_id id

        :param idp_id: id of Identity Provider for which related tokens should
                       be removed.

        """
        raise exception.NotImplemented()

    @controller.protected()
    def create_identity_provider(self, context, idp_id, identity_provider):
        mutable_params = set(['description', 'enabled'])
        public_params = set(['id', 'description', 'enabled'])
        identity_provider = self._normalize_dict(identity_provider)
        identity_provider.setdefault('description', '')
        identity_provider.setdefault('enabled', False)
        IdentityProvider.check_immutable_params(identity_provider,
                                                keys=mutable_params)
        idp_ref = self.federation_api.create_idp(idp_id, identity_provider)
        idp_ref = IdentityProvider.filter_params(idp_ref, keys=public_params)
        response = IdentityProvider.wrap_member(context, idp_ref)
        return wsgi.render_response(body=response, status=('201', 'Created'))

    @controller.protected()
    def list_identity_providers(self, context):
        ref = self.federation_api.list_idps()
        ref = [self.filter_params(x) for x in ref]
        return IdentityProvider.wrap_collection(context, ref)

    @controller.protected()
    def get_identity_provider(self, context, idp_id):
        ref = self.federation_api.get_idp(idp_id)
        ref = self.filter_params(ref)
        return IdentityProvider.wrap_member(context, ref)

    @controller.protected()
    def delete_identity_provider(self, context, idp_id):
        self.federation_api.delete_idp(idp_id)

    @controller.protected()
    def update_identity_provider(self, context, idp_id, identity_provider):
        identity_provider = self._normalize_dict(identity_provider)
        IdentityProvider.check_immutable_params(identity_provider)
        idp_ref = self.federation_api.update_idp(idp_id, identity_provider)
        return IdentityProvider.wrap_member(context, idp_ref)


@dependency.requires('federation_api')
class FederationProtocol(IdentityProvider):
    """A federation protocol representation.

    See IdentityProvider docstring for explanation on _mutable_parameters
    and _public_parameters class attributes.

    """
    collection_name = 'protocols'
    member_name = 'protocol'

    _public_parameters = frozenset(['id', 'mapping_id', 'links'])
    _mutable_parameters = set(['mapping_id'])

    @classmethod
    def _add_self_referential_link(cls, ref):
        """Add 'links' entry to the response dictionary.

        Calls IdentityProvider.base_url() class method, as it constructs
        proper URL along with the 'identity providers' part included.

        :param ref: response dictionary

        """
        ref.setdefault('links', {})
        base_path = ref['links'].get('identity_provider')
        if base_path is None:
            base_path = [IdentityProvider.base_url(), ref['idp_id']]
            base_path = '/'.join(base_path)
        self_path = [base_path, 'protocols', ref['id']]
        self_path = '/'.join(self_path)
        ref['links']['self'] = self_path

    @classmethod
    def _add_related_links(cls, ref):
        """Add new entries to the 'links' subdictionary in the response.

        Adds 'identity_provider' key with URL pointing to related identity
        provider as a value.

        :param ref: response dictionary

        """
        ref.setdefault('links', {})
        base_path = '/'.join([IdentityProvider.base_url(), ref['idp_id']])
        ref['links']['identity_provider'] = base_path

    @classmethod
    def wrap_member(cls, context, ref):
        cls._add_related_links(ref)
        cls._add_self_referential_link(ref)
        ref = cls.filter_params(ref)
        return {cls.member_name: ref}

    @controller.protected()
    def create_protocol(self, context, idp_id, protocol_id, protocol):
        ref = self._normalize_dict(protocol)
        keys = self._mutable_parameters.copy()
        FederationProtocol.check_immutable_params(ref, keys=keys)
        ref = self.federation_api.create_protocol(idp_id, protocol_id, ref)
        response = FederationProtocol.wrap_member(context, ref)
        return wsgi.render_response(body=response, status=('201', 'Created'))

    @controller.protected()
    def update_protocol(self, context, idp_id, protocol_id, protocol):
        ref = self._normalize_dict(protocol)
        FederationProtocol.check_immutable_params(ref)
        ref = self.federation_api.update_protocol(idp_id, protocol_id,
                                                  protocol)
        return FederationProtocol.wrap_member(context, ref)

    @controller.protected()
    def get_protocol(self, context, idp_id, protocol_id):
        ref = self.federation_api.get_protocol(idp_id, protocol_id)
        return FederationProtocol.wrap_member(context, ref)

    @controller.protected()
    def list_protocols(self, context, idp_id):
        protocols_ref = self.federation_api.list_protocols(idp_id)
        protocols = list(protocols_ref)
        return FederationProtocol.wrap_collection(context, protocols)

    @controller.protected()
    def delete_protocol(self, context, idp_id, protocol_id):
        self.federation_api.delete_protocol(idp_id, protocol_id)


@dependency.requires('federation_api')
class MappingController(controller.V3Controller):
    collection_name = 'mappings'
    member_name = 'mapping'

    @classmethod
    def base_url(cls, path=None):
        path = '/OS-FEDERATION/' + cls.collection_name
        return controller.V3Controller.base_url(path)

    @controller.protected()
    def create_mapping(self, context, mapping_id, mapping):
        ref = self._normalize_dict(mapping)
        utils.validate_mapping_structure(ref)
        mapping_ref = self.federation_api.create_mapping(mapping_id, ref)
        response = MappingController.wrap_member(context, mapping_ref)
        return wsgi.render_response(body=response, status=('201', 'Created'))

    @controller.protected()
    def list_mappings(self, context):
        ref = self.federation_api.list_mappings()
        return MappingController.wrap_collection(context, ref)

    @controller.protected()
    def get_mapping(self, context, mapping_id):
        ref = self.federation_api.get_mapping(mapping_id)
        return MappingController.wrap_member(context, ref)

    @controller.protected()
    def delete_mapping(self, context, mapping_id):
        self.federation_api.delete_mapping(mapping_id)

    @controller.protected()
    def update_mapping(self, context, mapping_id, mapping):
        mapping = self._normalize_dict(mapping)
        utils.validate_mapping_structure(mapping)
        mapping_ref = self.federation_api.update_mapping(mapping_id, mapping)
        return MappingController.wrap_member(context, mapping_ref)
