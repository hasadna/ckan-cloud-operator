#### standard provider code ####

# import the correct PROVIDER_SUBMODULE and PROVIDER_ID constants for your provider
from .constants import PROVIDER_ID
from ..constants import PROVIDER_SUBMODULE

# define common provider functions based on the constants
from ckan_cloud_operator.providers import manager as providers_manager
def _get_resource_name(suffix=None, short=False): return providers_manager.get_resource_name(PROVIDER_SUBMODULE, PROVIDER_ID, suffix=suffix, short=short)
def _get_resource_labels(for_deployment=False): return providers_manager.get_resource_labels(PROVIDER_SUBMODULE, PROVIDER_ID, for_deployment=for_deployment)
def _get_resource_annotations(suffix=None): return providers_manager.get_resource_annotations(PROVIDER_SUBMODULE, PROVIDER_ID, suffix=suffix)
def _set_provider(): providers_manager.set_provider(PROVIDER_SUBMODULE, PROVIDER_ID)
def _config_set(key=None, value=None, values=None, namespace=None, is_secret=False, suffix=None): providers_manager.config_set(PROVIDER_SUBMODULE, PROVIDER_ID, key=key, value=value, values=values, namespace=namespace, is_secret=is_secret, suffix=suffix)
def _config_get(key=None, default=None, required=False, namespace=None, is_secret=False, suffix=None): return providers_manager.config_get(PROVIDER_SUBMODULE, PROVIDER_ID, key=key, default=default, required=required, namespace=namespace, is_secret=is_secret, suffix=suffix)
def _config_interactive_set(default_values, namespace=None, is_secret=False, suffix=None, from_file=False): providers_manager.config_interactive_set(PROVIDER_SUBMODULE, PROVIDER_ID, default_values, namespace, is_secret, suffix, from_file)

################################
# custom provider code starts here
#

from ckan_cloud_operator import logs


def update(instance_id, instance, dry_run=False):
    logs.debug('Updating none-based instance deployment', instance_id=instance_id)
    app_type = instance['spec'].get('app-type')
    _get_app_type_manager(app_type).deploy(instance_id, instance)


def pre_update_hook(instance_id, instance, override_spec, skip_route=False, dry_run=False):
    _pre_update_hook_override_spec(override_spec, instance)
    res = {}
    app_type = instance['spec'].get('app-type')
    logs.info(app_type=app_type)
    logs.info(f'Running {app_type} app pre_update_hook')
    _get_app_type_manager(app_type).pre_update_hook(instance_id, instance, res)
    return res


def _pre_update_hook_override_spec(override_spec, instance):
    # applies override spec, but doesn't persist
    if override_spec:
        for k, v in override_spec.items():
            logs.info(f'Applying override spec {k}={v}')
            if k != 'values':
                instance['spec'][k] = v
            else:
                instance['spec'].setdefault('values', {}).update(v)


def _get_app_type_manager(app_type):
    if app_type == 'nfs-client-provisioner':
        from . import type_nfs_client_provisioner as app_type_manager
    else:
        raise NotImplementedError(f'Unknown app type: {app_type}')
    return app_type_manager
