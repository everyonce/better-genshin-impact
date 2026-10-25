"""File-only description of missing R47 authority; this candidate cannot activate it."""

SCHEMA = 'r47-navigation-v5-unbound-template-v1'
ACTUAL_FIELDS = ('buildManifest', 'testValidation', 'sourceSnapshotManifest', 'sourceProvenance',
    'deploymentClosure', 'deploymentSource', 'child', 'root', 'protectedGameCim',
    'collectionBinding', 'routeAuditorPackage', 'clientFiles')


def template():
    """Return unset actual identities; source review is not build/deployment evidence."""
    return dict(schema=SCHEMA, timingContract='v5', approvedForValidation=False,
                executionReady=False, **{name: None for name in ACTUAL_FIELDS})


def validate_template(value):
    """Reject guessed future fields, approval flags and relabeled R46 bindings."""
    expected=template()
    if type(value) is not dict or set(value)!=set(expected):
        raise RuntimeError('Exact unbound R47 template fields required.')
    if value != expected or type(value['approvedForValidation']) is not bool or type(value['executionReady']) is not bool:
        raise RuntimeError('R47 actual build/source/deployment fields must remain unset.')
    return True


def require_activation(value=None):
    """Never authorize collection or a successful route audit from this source packet."""
    if value is not None:
        validate_template(value)
    raise RuntimeError('R47 v5 activation is unavailable: reviewed actual build, tests, deployment and binding are required in a separate packet.')
