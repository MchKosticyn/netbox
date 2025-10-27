import hashlib
import importlib
import importlib.util
import os
import platform
import sys
import warnings

# Shim rq module to use fakeredis_shim for in-memory testing
from utilities import fakeredis_shim
import types

# Create a fake rq package module
rq_module = types.ModuleType('rq')
rq_module.Worker = fakeredis_shim.Worker
rq_module.Retry = lambda *args, **kwargs: None  # Dummy Retry
sys.modules['rq'] = rq_module

# Create fake rq submodules
rq_worker_module = types.ModuleType('rq.worker')
rq_worker_module.Worker = fakeredis_shim.Worker
sys.modules['rq.worker'] = rq_worker_module

rq_exceptions_module = types.ModuleType('rq.exceptions')
rq_exceptions_module.InvalidJobOperation = fakeredis_shim.InvalidJobOperation
rq_exceptions_module.NoSuchJobError = fakeredis_shim.NoSuchJobError
sys.modules['rq.exceptions'] = rq_exceptions_module

rq_job_module = types.ModuleType('rq.job')
rq_job_module.Job = fakeredis_shim.Job
rq_job_module.JobStatus = fakeredis_shim.JobStatus
sys.modules['rq.job'] = rq_job_module

rq_registry_module = types.ModuleType('rq.registry')
rq_registry_module.FailedJobRegistry = fakeredis_shim.FailedJobRegistry
rq_registry_module.StartedJobRegistry = fakeredis_shim.StartedJobRegistry
rq_registry_module.FinishedJobRegistry = fakeredis_shim.FinishedJobRegistry
rq_registry_module.DeferredJobRegistry = fakeredis_shim.DeferredJobRegistry
rq_registry_module.ScheduledJobRegistry = fakeredis_shim.ScheduledJobRegistry
rq_registry_module.CanceledJobRegistry = fakeredis_shim.CanceledJobRegistry
sys.modules['rq.registry'] = rq_registry_module

rq_timeouts_module = types.ModuleType('rq.timeouts')
rq_timeouts_module.JobTimeoutException = fakeredis_shim.JobTimeoutException
sys.modules['rq.timeouts'] = rq_timeouts_module

rq_worker_registration_module = types.ModuleType('rq.worker_registration')
rq_worker_registration_module.clean_worker_registry = fakeredis_shim.clean_worker_registry
sys.modules['rq.worker_registration'] = rq_worker_registration_module

# Create fake django_rq package module
django_rq_module = types.ModuleType('django_rq')
django_rq_module.get_queue = fakeredis_shim.get_queue
django_rq_module.job = lambda *args, **kwargs: lambda func: func  # Dummy decorator
sys.modules['django_rq'] = django_rq_module

# Create fake django_rq.workers submodule
django_rq_workers_module = types.ModuleType('django_rq.workers')
django_rq_workers_module.get_worker = fakeredis_shim.get_worker
sys.modules['django_rq.workers'] = django_rq_workers_module

# Create fake django_rq.queues submodule
django_rq_queues_module = types.ModuleType('django_rq.queues')
django_rq_queues_module.get_connection = fakeredis_shim.get_connection
django_rq_queues_module.get_redis_connection = fakeredis_shim.get_redis_connection
django_rq_queues_module.get_queue_by_index = lambda index: fakeredis_shim.get_queue({0: 'default', 1: 'high', 2: 'low'}.get(index, 'default'))
sys.modules['django_rq.queues'] = django_rq_queues_module

# Create fake django_rq.settings submodule
django_rq_settings_module = types.ModuleType('django_rq.settings')
django_rq_settings_module.QUEUES_LIST = [
    {"name": "default", "connection_config": {}},
    {"name": "high", "connection_config": {}},
    {"name": "low", "connection_config": {}},
]
django_rq_settings_module.QUEUES_MAP = {"default": 0, "high": 1, "low": 2}
sys.modules['django_rq.settings'] = django_rq_settings_module

# Create fake django_rq.utils submodule
django_rq_utils_module = types.ModuleType('django_rq.utils')
def _get_statistics(*args, **kwargs):
    queues_data = []
    for i, queue_config in enumerate(django_rq_settings_module.QUEUES_LIST):
        queue_name = queue_config['name']
        queue = fakeredis_shim.get_queue(queue_name)
        
        # Get registries for additional statistics
        finished_registry = fakeredis_shim.FinishedJobRegistry(queue_name, connection=queue.connection)
        failed_registry = fakeredis_shim.FailedJobRegistry(queue_name, connection=queue.connection)
        started_registry = fakeredis_shim.StartedJobRegistry(queue_name, connection=queue.connection)
        deferred_registry = fakeredis_shim.DeferredJobRegistry(queue_name, connection=queue.connection)
        scheduled_registry = fakeredis_shim.ScheduledJobRegistry(queue_name, connection=queue.connection)
        canceled_registry = fakeredis_shim.CanceledJobRegistry(queue_name, connection=queue.connection)
        
        queues_data.append({
            'name': queue_name,
            'jobs': queue.count,
            'index': django_rq_settings_module.QUEUES_MAP.get(queue_name, i),
            'oldest_job_timestamp': '',  # Empty string for fakeredis
            'scheduler_pid': '',  # Empty string for fakeredis
            'workers': 0,  # No workers for fakeredis
            'finished_jobs': len(finished_registry),
            'failed_jobs': len(failed_registry),
            'started_jobs': len(started_registry),
            'deferred_jobs': len(deferred_registry),
            'scheduled_jobs': len(scheduled_registry),
            'canceled_jobs': len(canceled_registry),
        })
    return {
        "workers": 1,
        "queues": queues_data,
        "jobs": sum(q['jobs'] for q in queues_data),
    }
django_rq_utils_module.get_statistics = _get_statistics
django_rq_utils_module.get_jobs = lambda queue, job_ids, registry: [job for job_id in job_ids if (job := queue.fetch_job(job_id))]
django_rq_utils_module.stop_jobs = lambda queue, job_id: [0]
sys.modules['django_rq.utils'] = django_rq_utils_module

from django.contrib.messages import constants as messages
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import URLValidator
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

from core.exceptions import IncompatiblePluginError
from netbox.config import PARAMS as CONFIG_PARAMS
from netbox.constants import RQ_QUEUE_DEFAULT, RQ_QUEUE_HIGH, RQ_QUEUE_LOW
# Avoid importing netbox.plugins at settings import time to prevent early ORM usage
# from netbox.plugins import PluginConfig
from netbox.registry import registry
import storages.utils  # type: ignore
from utilities.release import load_release_data
# Ensure SQLite collations registered via signal for tests/dev (no early connection import)
import utilities.sqlite_collations  # noqa: F401
from utilities.string import trailing_slash

#
# Environment setup
#

RELEASE = load_release_data()
VERSION = RELEASE.full_version  # Retained for backward compatibility
# Set the base directory two levels up
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Validate Python version
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"NetBox requires Python 3.10 or later. (Currently installed: Python {platform.python_version()})"
    )

#
# Configuration import
#

# Import the configuration module
config_path = os.getenv('NETBOX_CONFIGURATION', 'netbox.configuration')
try:
    configuration = importlib.import_module(config_path)
except ModuleNotFoundError as e:
    if getattr(e, 'name') == config_path:
        raise ImproperlyConfigured(
            f"Specified configuration module ({config_path}) not found. Please define netbox/netbox/configuration.py "
            f"per the documentation, or specify an alternate module in the NETBOX_CONFIGURATION environment variable."
        )
    raise

# Check for missing/conflicting required configuration parameters
for parameter in ('ALLOWED_HOSTS', 'SECRET_KEY'):
    if not hasattr(configuration, parameter):
        raise ImproperlyConfigured(f"Required parameter {parameter} is missing from configuration.")
if not hasattr(configuration, 'DATABASE') and not hasattr(configuration, 'DATABASES'):
    raise ImproperlyConfigured("The database configuration must be defined using DATABASE or DATABASES.")
elif hasattr(configuration, 'DATABASE') and hasattr(configuration, 'DATABASES'):
    raise ImproperlyConfigured("DATABASE and DATABASES may not be set together. The use of DATABASES is encouraged.")

# Set static config parameters
ADMINS = getattr(configuration, 'ADMINS', [])
ALLOW_TOKEN_RETRIEVAL = getattr(configuration, 'ALLOW_TOKEN_RETRIEVAL', False)
ALLOWED_HOSTS = getattr(configuration, 'ALLOWED_HOSTS')  # Required
AUTH_PASSWORD_VALIDATORS = getattr(configuration, 'AUTH_PASSWORD_VALIDATORS', [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 12,
        },
    },
    {
        "NAME": "utilities.password_validation.AlphanumericPasswordValidator",
    },
])
BASE_PATH = trailing_slash(getattr(configuration, 'BASE_PATH', ''))
CHANGELOG_SKIP_EMPTY_CHANGES = getattr(configuration, 'CHANGELOG_SKIP_EMPTY_CHANGES', True)
CENSUS_REPORTING_ENABLED = getattr(configuration, 'CENSUS_REPORTING_ENABLED', True)
CORS_ORIGIN_ALLOW_ALL = getattr(configuration, 'CORS_ORIGIN_ALLOW_ALL', False)
CORS_ORIGIN_REGEX_WHITELIST = getattr(configuration, 'CORS_ORIGIN_REGEX_WHITELIST', [])
CORS_ORIGIN_WHITELIST = getattr(configuration, 'CORS_ORIGIN_WHITELIST', [])
CSRF_COOKIE_NAME = getattr(configuration, 'CSRF_COOKIE_NAME', 'csrftoken')
CSRF_COOKIE_PATH = f'/{BASE_PATH.rstrip("/")}'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = getattr(configuration, 'CSRF_COOKIE_SECURE', False)
CSRF_TRUSTED_ORIGINS = getattr(configuration, 'CSRF_TRUSTED_ORIGINS', [])
DATA_UPLOAD_MAX_MEMORY_SIZE = getattr(configuration, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 2621440)
DATABASE = getattr(configuration, 'DATABASE', None)  # Legacy DB definition
DATABASE_ROUTERS = getattr(configuration, 'DATABASE_ROUTERS', [])
DATABASES = getattr(configuration, 'DATABASES', {'default': DATABASE})
DEBUG = getattr(configuration, 'DEBUG', False)
DEFAULT_DASHBOARD = getattr(configuration, 'DEFAULT_DASHBOARD', None)
DEFAULT_PERMISSIONS = getattr(configuration, 'DEFAULT_PERMISSIONS', {
    # Permit users to manage their own bookmarks
    'extras.view_bookmark': ({'user': '$user'},),
    'extras.add_bookmark': ({'user': '$user'},),
    'extras.change_bookmark': ({'user': '$user'},),
    'extras.delete_bookmark': ({'user': '$user'},),
    # Permit users to manage their own notifications
    'extras.view_notification': ({'user': '$user'},),
    'extras.add_notification': ({'user': '$user'},),
    'extras.change_notification': ({'user': '$user'},),
    'extras.delete_notification': ({'user': '$user'},),
    # Permit users to manage their own subscriptions
    'extras.view_subscription': ({'user': '$user'},),
    'extras.add_subscription': ({'user': '$user'},),
    'extras.change_subscription': ({'user': '$user'},),
    'extras.delete_subscription': ({'user': '$user'},),
    # Permit users to manage their own API tokens
    'users.view_token': ({'user': '$user'},),
    'users.add_token': ({'user': '$user'},),
    'users.change_token': ({'user': '$user'},),
    'users.delete_token': ({'user': '$user'},),
})
DEVELOPER = getattr(configuration, 'DEVELOPER', False)
DOCS_ROOT = getattr(configuration, 'DOCS_ROOT', os.path.join(os.path.dirname(BASE_DIR), 'docs'))
EMAIL = getattr(configuration, 'EMAIL', {})
EVENTS_PIPELINE = getattr(configuration, 'EVENTS_PIPELINE', [
    'extras.events.process_event_queue',
])
EXEMPT_VIEW_PERMISSIONS = getattr(configuration, 'EXEMPT_VIEW_PERMISSIONS', [])
FIELD_CHOICES = getattr(configuration, 'FIELD_CHOICES', {})
FILE_UPLOAD_MAX_MEMORY_SIZE = getattr(configuration, 'FILE_UPLOAD_MAX_MEMORY_SIZE', 2621440)
GRAPHQL_MAX_ALIASES = getattr(configuration, 'GRAPHQL_MAX_ALIASES', 10)
HOSTNAME = getattr(configuration, 'HOSTNAME', platform.node())
HTTP_PROXIES = getattr(configuration, 'HTTP_PROXIES', {})
INTERNAL_IPS = getattr(configuration, 'INTERNAL_IPS', ('127.0.0.1', '::1'))
ISOLATED_DEPLOYMENT = getattr(configuration, 'ISOLATED_DEPLOYMENT', False)
JINJA2_FILTERS = getattr(configuration, 'JINJA2_FILTERS', {})
LANGUAGE_CODE = getattr(configuration, 'DEFAULT_LANGUAGE', 'en-us')
LANGUAGE_COOKIE_PATH = CSRF_COOKIE_PATH
LOGGING = getattr(configuration, 'LOGGING', {})
LOGIN_PERSISTENCE = getattr(configuration, 'LOGIN_PERSISTENCE', False)
LOGIN_REQUIRED = getattr(configuration, 'LOGIN_REQUIRED', True)
LOGIN_TIMEOUT = getattr(configuration, 'LOGIN_TIMEOUT', None)
LOGIN_FORM_HIDDEN = getattr(configuration, 'LOGIN_FORM_HIDDEN', False)
LOGOUT_REDIRECT_URL = getattr(configuration, 'LOGOUT_REDIRECT_URL', 'home')
MEDIA_ROOT = getattr(configuration, 'MEDIA_ROOT', os.path.join(BASE_DIR, 'media')).rstrip('/')
METRICS_ENABLED = getattr(configuration, 'METRICS_ENABLED', False)
PLUGINS = getattr(configuration, 'PLUGINS', [])
PLUGINS_CONFIG = getattr(configuration, 'PLUGINS_CONFIG', {})
PLUGINS_CATALOG_CONFIG = getattr(configuration, 'PLUGINS_CATALOG_CONFIG', {})
PROXY_ROUTERS = getattr(configuration, 'PROXY_ROUTERS', ['utilities.proxy.DefaultProxyRouter'])
QUEUE_MAPPINGS = getattr(configuration, 'QUEUE_MAPPINGS', {})
# Redis no longer used in this project
REDIS = {}
RELEASE_CHECK_URL = getattr(configuration, 'RELEASE_CHECK_URL', None)
REMOTE_AUTH_AUTO_CREATE_GROUPS = getattr(configuration, 'REMOTE_AUTH_AUTO_CREATE_GROUPS', False)
REMOTE_AUTH_AUTO_CREATE_USER = getattr(configuration, 'REMOTE_AUTH_AUTO_CREATE_USER', False)
REMOTE_AUTH_BACKEND = getattr(configuration, 'REMOTE_AUTH_BACKEND', 'netbox.authentication.RemoteUserBackend')
REMOTE_AUTH_DEFAULT_GROUPS = getattr(configuration, 'REMOTE_AUTH_DEFAULT_GROUPS', [])
REMOTE_AUTH_DEFAULT_PERMISSIONS = getattr(configuration, 'REMOTE_AUTH_DEFAULT_PERMISSIONS', {})
REMOTE_AUTH_ENABLED = getattr(configuration, 'REMOTE_AUTH_ENABLED', False)
REMOTE_AUTH_GROUP_HEADER = getattr(configuration, 'REMOTE_AUTH_GROUP_HEADER', 'HTTP_REMOTE_USER_GROUP')
REMOTE_AUTH_GROUP_SEPARATOR = getattr(configuration, 'REMOTE_AUTH_GROUP_SEPARATOR', '|')
REMOTE_AUTH_GROUP_SYNC_ENABLED = getattr(configuration, 'REMOTE_AUTH_GROUP_SYNC_ENABLED', False)
REMOTE_AUTH_HEADER = getattr(configuration, 'REMOTE_AUTH_HEADER', 'HTTP_REMOTE_USER')
REMOTE_AUTH_SUPERUSER_GROUPS = getattr(configuration, 'REMOTE_AUTH_SUPERUSER_GROUPS', [])
REMOTE_AUTH_SUPERUSERS = getattr(configuration, 'REMOTE_AUTH_SUPERUSERS', [])
REMOTE_AUTH_USER_EMAIL = getattr(configuration, 'REMOTE_AUTH_USER_EMAIL', 'HTTP_REMOTE_USER_EMAIL')
REMOTE_AUTH_USER_FIRST_NAME = getattr(configuration, 'REMOTE_AUTH_USER_FIRST_NAME', 'HTTP_REMOTE_USER_FIRST_NAME')
REMOTE_AUTH_USER_LAST_NAME = getattr(configuration, 'REMOTE_AUTH_USER_LAST_NAME', 'HTTP_REMOTE_USER_LAST_NAME')
REMOTE_AUTH_STAFF_GROUPS = getattr(configuration, 'REMOTE_AUTH_STAFF_GROUPS', [])
REMOTE_AUTH_STAFF_USERS = getattr(configuration, 'REMOTE_AUTH_STAFF_USERS', [])
# Required by extras/migrations/0109_script_models.py
REPORTS_ROOT = getattr(configuration, 'REPORTS_ROOT', os.path.join(BASE_DIR, 'reports')).rstrip('/')
RQ_DEFAULT_TIMEOUT = getattr(configuration, 'RQ_DEFAULT_TIMEOUT', 300)
RQ_RETRY_INTERVAL = getattr(configuration, 'RQ_RETRY_INTERVAL', 60)
RQ_RETRY_MAX = getattr(configuration, 'RQ_RETRY_MAX', 0)
SCRIPTS_ROOT = getattr(configuration, 'SCRIPTS_ROOT', os.path.join(BASE_DIR, 'scripts')).rstrip('/')
SEARCH_BACKEND = getattr(configuration, 'SEARCH_BACKEND', 'netbox.search.backends.CachedValueSearchBackend')
SECRET_KEY = getattr(configuration, 'SECRET_KEY')  # Required
SECURE_HSTS_INCLUDE_SUBDOMAINS = getattr(configuration, 'SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = getattr(configuration, 'SECURE_HSTS_PRELOAD', False)
SECURE_HSTS_SECONDS = getattr(configuration, 'SECURE_HSTS_SECONDS', 0)
SECURE_SSL_REDIRECT = getattr(configuration, 'SECURE_SSL_REDIRECT', False)
SENTRY_CONFIG = getattr(configuration, 'SENTRY_CONFIG', {})
# TODO: Remove in NetBox v4.5
SENTRY_DSN = getattr(configuration, 'SENTRY_DSN', None)
SENTRY_ENABLED = getattr(configuration, 'SENTRY_ENABLED', False)
# TODO: Remove in NetBox v4.5
SENTRY_SAMPLE_RATE = getattr(configuration, 'SENTRY_SAMPLE_RATE', 1.0)
# TODO: Remove in NetBox v4.5
SENTRY_SEND_DEFAULT_PII = getattr(configuration, 'SENTRY_SEND_DEFAULT_PII', False)
SENTRY_TAGS = getattr(configuration, 'SENTRY_TAGS', {})
# TODO: Remove in NetBox v4.5
SENTRY_TRACES_SAMPLE_RATE = getattr(configuration, 'SENTRY_TRACES_SAMPLE_RATE', 0)
SESSION_COOKIE_NAME = getattr(configuration, 'SESSION_COOKIE_NAME', 'sessionid')
SESSION_COOKIE_PATH = CSRF_COOKIE_PATH
SESSION_COOKIE_SECURE = getattr(configuration, 'SESSION_COOKIE_SECURE', False)
SESSION_FILE_PATH = getattr(configuration, 'SESSION_FILE_PATH', None)
STORAGE_BACKEND = getattr(configuration, 'STORAGE_BACKEND', None)
STORAGE_CONFIG = getattr(configuration, 'STORAGE_CONFIG', None)
STORAGES = getattr(configuration, 'STORAGES', {})
TIME_ZONE = getattr(configuration, 'TIME_ZONE', 'UTC')
TRANSLATION_ENABLED = getattr(configuration, 'TRANSLATION_ENABLED', True)
DISK_BASE_UNIT = getattr(configuration, 'DISK_BASE_UNIT', 1000)
if DISK_BASE_UNIT not in [1000, 1024]:
    raise ImproperlyConfigured(f"DISK_BASE_UNIT must be 1000 or 1024 (found {DISK_BASE_UNIT})")
RAM_BASE_UNIT = getattr(configuration, 'RAM_BASE_UNIT', 1000)
if RAM_BASE_UNIT not in [1000, 1024]:
    raise ImproperlyConfigured(f"RAM_BASE_UNIT must be 1000 or 1024 (found {RAM_BASE_UNIT})")

# Load any dynamic configuration parameters which have been hard-coded in the configuration file
for param in CONFIG_PARAMS:
    if hasattr(configuration, param.name):
        globals()[param.name] = getattr(configuration, param.name)

# Enforce minimum length for SECRET_KEY
if type(SECRET_KEY) is not str:
    raise ImproperlyConfigured(f"SECRET_KEY must be a string (found {type(SECRET_KEY).__name__})")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        f"SECRET_KEY must be at least 50 characters in length. To generate a suitable key, run the following command:\n"
        f"  python {BASE_DIR}/generate_secret_key.py"
    )

# Validate update repo URL and timeout
if RELEASE_CHECK_URL:
    try:
        URLValidator()(RELEASE_CHECK_URL)
    except ValidationError:
        raise ImproperlyConfigured(
            "RELEASE_CHECK_URL must be a valid URL. Example: https://api.github.com/repos/netbox-community/netbox"
        )

# Validate configured proxy routers
for path in PROXY_ROUTERS:
    if type(path) is str:
        try:
            import_string(path)
        except ImportError:
            raise ImproperlyConfigured(f"Invalid path in PROXY_ROUTERS: {path}")


#
# Database
#

# Force usage of in-memory SQLite for all environments (tests and runtime)
# This simplifies local testing and avoids DB-specific SQL syntax issues.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}


#
# Storage backend
#

if STORAGE_BACKEND is not None:
    if not STORAGES:
        raise ImproperlyConfigured(
            "STORAGE_BACKEND and STORAGES are both set, remove the deprecated STORAGE_BACKEND setting."
        )
    else:
        warnings.warn(
            "STORAGE_BACKEND is deprecated, use the new STORAGES setting instead."
        )

if STORAGE_CONFIG is not None:
    warnings.warn(
        "STORAGE_CONFIG is deprecated, use the new STORAGES setting instead."
    )

# Default STORAGES for Django
DEFAULT_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "scripts": {
        "BACKEND": "extras.storage.ScriptFileSystemStorage",
    },
}
STORAGES = DEFAULT_STORAGES | STORAGES

# TODO: This code is deprecated and needs to be removed in the future
if STORAGE_BACKEND is not None:
    STORAGES['default']['BACKEND'] = STORAGE_BACKEND

# Monkey-patch django-storages to fetch settings from STORAGE_CONFIG
if STORAGE_CONFIG is not None:
    def _setting(name, default=None):
        if name in STORAGE_CONFIG:
            return STORAGE_CONFIG[name]
        return globals().get(name, default)
    storages.utils.setting = _setting

# django-storage-swift
if STORAGE_BACKEND == 'swift.storage.SwiftStorage':
    try:
        import swift.utils  # noqa: F401
    except ModuleNotFoundError as e:
        if getattr(e, 'name') == 'swift':
            raise ImproperlyConfigured(
                f"STORAGE_BACKEND is set to {STORAGE_BACKEND} but django-storage-swift is not present. "
                "It can be installed by running 'pip install django-storage-swift'."
            )
        raise e

    # Load all SWIFT_* settings from the user configuration
    for param, value in STORAGE_CONFIG.items():
        if param.startswith('SWIFT_'):
            globals()[param] = value
# TODO: End of deprecated code

#
# In-memory configuration (no Redis)
#
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'netbox-cache',
    }
}


#
# Sessions
#

if LOGIN_TIMEOUT is not None:
    # Django default is 1209600 seconds (14 days)
    SESSION_COOKIE_AGE = LOGIN_TIMEOUT
SESSION_SAVE_EVERY_REQUEST = bool(LOGIN_PERSISTENCE)
if SESSION_FILE_PATH is not None:
    SESSION_ENGINE = 'django.contrib.sessions.backends.file'


#
# Email
#

EMAIL_HOST = EMAIL.get('SERVER')
EMAIL_HOST_USER = EMAIL.get('USERNAME')
EMAIL_HOST_PASSWORD = EMAIL.get('PASSWORD')
EMAIL_PORT = EMAIL.get('PORT', 25)
EMAIL_SSL_CERTFILE = EMAIL.get('SSL_CERTFILE')
EMAIL_SSL_KEYFILE = EMAIL.get('SSL_KEYFILE')
EMAIL_SUBJECT_PREFIX = '[NetBox] '
EMAIL_USE_SSL = EMAIL.get('USE_SSL', False)
EMAIL_USE_TLS = EMAIL.get('USE_TLS', False)
EMAIL_TIMEOUT = EMAIL.get('TIMEOUT', 10)
SERVER_EMAIL = EMAIL.get('FROM_EMAIL')


#
# Django core settings
#

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.forms',
    'corsheaders',
    'debug_toolbar',
    'django_filters',
    'django_htmx',
    'django_tables2',
    'django_prometheus',
    'strawberry_django',
    'mptt',
    'rest_framework',
    'social_django',
    'sorl.thumbnail',
    'taggit',
    'timezone_field',
    'core',
    'account',
    'circuits',
    'dcim',
    'ipam',
    'extras',
    'tenancy',
    'users',
    'utilities',
    'virtualization',
    'vpn',
    'wireless',
    # 'django_rq',  # Disabled: no Redis/tasks in in-memory setup
    'drf_spectacular',
    'drf_spectacular_sidecar',
]
if not DEBUG and 'collectstatic' not in sys.argv:
    INSTALLED_APPS.remove('debug_toolbar')

# Middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'netbox.middleware.RemoteUserMiddleware',
    'netbox.middleware.CoreMiddleware',
    'netbox.middleware.MaintenanceModeMiddleware',
]

if DEBUG:
    MIDDLEWARE = [
        "strawberry_django.middlewares.debug_toolbar.DebugToolbarMiddleware",
        *MIDDLEWARE,
    ]

if METRICS_ENABLED:
    # If metrics are enabled, add the before & after Prometheus middleware
    MIDDLEWARE = [
        'netbox.middleware.PrometheusBeforeMiddleware',
        *MIDDLEWARE,
        'netbox.middleware.PrometheusAfterMiddleware',
    ]

# URLs
ROOT_URLCONF = 'netbox.urls'

# Templates
TEMPLATES_DIR = BASE_DIR + '/templates'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATES_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': [
                'utilities.templatetags.builtins.filters',
                'utilities.templatetags.builtins.tags',
            ],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'netbox.context_processors.settings',
                'netbox.context_processors.config',
                'netbox.context_processors.registry',
                'netbox.context_processors.preferences',
            ],
        },
    },
]

# This allows us to override Django's stock form widget templates
FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

# Set up authentication backends
if type(REMOTE_AUTH_BACKEND) not in (list, tuple):
    REMOTE_AUTH_BACKEND = [REMOTE_AUTH_BACKEND]
AUTHENTICATION_BACKENDS = [
    *REMOTE_AUTH_BACKEND,
    'netbox.authentication.ObjectPermissionBackend',
]

# Use our custom User model
AUTH_USER_MODEL = 'users.User'

# Authentication URLs
LOGIN_URL = f'/{BASE_PATH}login/'
LOGIN_REDIRECT_URL = f'/{BASE_PATH}'

# Use timezone-aware datetime objects
USE_TZ = True

# Toggle language translation support
USE_I18N = TRANSLATION_ENABLED

# WSGI
WSGI_APPLICATION = 'netbox.wsgi.application'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Static files (CSS, JavaScript, Images)
STATIC_ROOT = BASE_DIR + '/static'
STATIC_URL = f'/{BASE_PATH}static/'
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'project-static', 'dist'),
    os.path.join(BASE_DIR, 'project-static', 'img'),
    os.path.join(BASE_DIR, 'project-static', 'js'),
    ('docs', os.path.join(BASE_DIR, 'project-static', 'docs')),  # Prefix with /docs
)

# Media URL
MEDIA_URL = f'/{BASE_PATH}media/'

# Disable default limit of 1000 fields per request. Needed for bulk deletion of objects. (Added in Django 1.10.)
DATA_UPLOAD_MAX_NUMBER_FIELDS = None

# Messages
MESSAGE_TAGS = {
    messages.ERROR: 'danger',
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SERIALIZATION_MODULES = {
    'json': 'utilities.serializers.json',
}


#
# Permissions & authentication
#

# Exclude potentially sensitive models from wildcard view exemption. These may still be exempted
# by specifying the model individually in the EXEMPT_VIEW_PERMISSIONS configuration parameter.
EXEMPT_EXCLUDE_MODELS = (
    ('extras', 'configrevision'),
    ('users', 'group'),
    ('users', 'objectpermission'),
    ('users', 'token'),
    ('users', 'user'),
)

# All URLs starting with a string listed here are exempt from maintenance mode enforcement
MAINTENANCE_EXEMPT_PATHS = (
    f'/{BASE_PATH}extras/config-revisions/',  # Allow modifying the configuration
    LOGIN_URL,
    LOGIN_REDIRECT_URL,
    LOGOUT_REDIRECT_URL
)


#
# Sentry
#

if SENTRY_ENABLED:
    try:
        import sentry_sdk
    except ModuleNotFoundError:
        raise ImproperlyConfigured("SENTRY_ENABLED is True but the sentry-sdk package is not installed.")

    # Construct default Sentry initialization parameters from legacy SENTRY_* config parameters
    sentry_config = {
        'dsn': SENTRY_DSN,
        'sample_rate': SENTRY_SAMPLE_RATE,
        'send_default_pii': SENTRY_SEND_DEFAULT_PII,
        'traces_sample_rate': SENTRY_TRACES_SAMPLE_RATE,
        # TODO: Support proxy routing
        'http_proxy': HTTP_PROXIES.get('http') if HTTP_PROXIES else None,
        'https_proxy': HTTP_PROXIES.get('https') if HTTP_PROXIES else None,
    }
    # Override/extend the default parameters with any provided via SENTRY_CONFIG
    sentry_config.update(SENTRY_CONFIG)
    # Check for a DSN
    if not sentry_config.get('dsn'):
        raise ImproperlyConfigured(
            "Sentry is enabled but a DSN has not been specified. Set one under the SENTRY_CONFIG parameter."
        )

    # Initialize the SDK
    sentry_sdk.init(
        release=RELEASE.full_version,
        **sentry_config
    )
    # Assign any configured tags
    for k, v in SENTRY_TAGS.items():
        sentry_sdk.set_tag(k, v)


#
# Census collection
#

# Calculate a unique deployment ID from the secret key
DEPLOYMENT_ID = hashlib.sha256(SECRET_KEY.encode('utf-8')).hexdigest()[:16]
CENSUS_URL = 'https://census.netbox.oss.netboxlabs.com/api/v1/'


#
# Django social auth
#

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'netbox.authentication.user_default_groups_handler',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

# Load all SOCIAL_AUTH_* settings from the user configuration
for param in dir(configuration):
    if param.startswith('SOCIAL_AUTH_'):
        globals()[param] = getattr(configuration, param)

# Force usage of PostgreSQL's JSONB field for extra data
SOCIAL_AUTH_JSONFIELD_ENABLED = True
SOCIAL_AUTH_CLEAN_USERNAME_FUNCTION = 'users.utils.clean_username'

SOCIAL_AUTH_USER_MODEL = AUTH_USER_MODEL

#
# Django Prometheus
#

PROMETHEUS_EXPORT_MIGRATIONS = False


#
# Django filters
#

FILTERS_NULL_CHOICE_LABEL = 'None'
FILTERS_NULL_CHOICE_VALUE = 'null'


#
# Django REST framework (API)
#

REST_FRAMEWORK_VERSION = '.'.join(RELEASE.version.split('-')[0].split('.')[:2])  # Use major.minor as API version
REST_FRAMEWORK = {
    'ALLOWED_VERSIONS': [REST_FRAMEWORK_VERSION],
    'COERCE_DECIMAL_TO_STRING': False,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'netbox.api.authentication.TokenAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_METADATA_CLASS': 'netbox.api.metadata.BulkOperationMetadata',
    'DEFAULT_PAGINATION_CLASS': 'netbox.api.pagination.OptionalLimitOffsetPagination',
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'netbox.api.authentication.TokenPermissions',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'netbox.api.renderers.FormlessBrowsableAPIRenderer',
    ),
    'DEFAULT_SCHEMA_CLASS': 'core.api.schema.NetBoxAutoSchema',
    'DEFAULT_VERSION': REST_FRAMEWORK_VERSION,
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'SCHEMA_COERCE_METHOD_NAMES': {
        # Default mappings
        'retrieve': 'read',
        'destroy': 'delete',
        # Custom operations
        'bulk_destroy': 'bulk_delete',
    },
    'VIEW_NAME_FUNCTION': 'utilities.api.get_view_name',
}

#
# DRF Spectacular
#

SPECTACULAR_SETTINGS = {
    'TITLE': 'NetBox REST API',
    'LICENSE': {'name': 'Apache v2 License'},
    'VERSION': RELEASE.full_version,
    'COMPONENT_SPLIT_REQUEST': True,
    'REDOC_DIST': 'SIDECAR',
    'SERVERS': [{
        'url': BASE_PATH,
        'description': 'NetBox',
    }],
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'POSTPROCESSING_HOOKS': [],
}

#
# Events backend (Django RQ) disabled for in-memory setup
#
RQ_PARAMS = {
    'HOST': 'localhost',
    'PORT': 0,
}
RQ_QUEUES = {
    RQ_QUEUE_HIGH: RQ_PARAMS,
    RQ_QUEUE_DEFAULT: RQ_PARAMS,
    RQ_QUEUE_LOW: RQ_PARAMS,
}
# Add any queues defined in QUEUE_MAPPINGS (use same dummy params)
RQ_QUEUES.update({
    queue: RQ_PARAMS for queue in set(QUEUE_MAPPINGS.values()) if queue not in RQ_QUEUES
})

#
# Localization
#

# Supported translation languages
LANGUAGES = (
    ('cs', _('Czech')),
    ('da', _('Danish')),
    ('de', _('German')),
    ('en', _('English')),
    ('es', _('Spanish')),
    ('fr', _('French')),
    ('it', _('Italian')),
    ('ja', _('Japanese')),
    ('nl', _('Dutch')),
    ('pl', _('Polish')),
    ('pt', _('Portuguese')),
    ('ru', _('Russian')),
    ('tr', _('Turkish')),
    ('uk', _('Ukrainian')),
    ('zh', _('Chinese')),
)
LOCALE_PATHS = (
    BASE_DIR + '/translations',
)

#
# Strawberry (GraphQL)
#
STRAWBERRY_DJANGO = {
    "DEFAULT_PK_FIELD_NAME": "id",
    "TYPE_DESCRIPTION_FROM_MODEL_DOCSTRING": True,
    "PAGINATION_DEFAULT_LIMIT": 100,
}

#
# Plugins
#

PLUGIN_CATALOG_URL = 'https://api.netbox.oss.netboxlabs.com/v1/plugins'

EVENTS_PIPELINE = list(EVENTS_PIPELINE)
if 'extras.events.process_event_queue' not in EVENTS_PIPELINE:
    EVENTS_PIPELINE.insert(0, 'extras.events.process_event_queue')

# Register any configured plugins
for plugin_name in PLUGINS:
    try:
        # Import the plugin module
        plugin = importlib.import_module(plugin_name)
    except ModuleNotFoundError as e:
        if getattr(e, 'name') == plugin_name:
            raise ImproperlyConfigured(
                f"Unable to import plugin {plugin_name}: Module not found. Check that the plugin module has been "
                f"installed within the correct Python environment."
            )
        raise e

    try:
        # Load the plugin's AppConfig (PluginConfig) without importing the netbox.plugins module here
        plugin_config = plugin.config
    except AttributeError:
        raise ImproperlyConfigured(
            f"Plugin {plugin_name} does not provide a 'config' variable. This should be defined in the plugin's "
            f"__init__.py file and point to the PluginConfig subclass."
        )

    # Validate version compatibility and user-provided configuration settings and assign defaults
    if plugin_name not in PLUGINS_CONFIG:
        PLUGINS_CONFIG[plugin_name] = {}
    try:
        plugin_config.validate(PLUGINS_CONFIG[plugin_name], RELEASE.version)
    except IncompatiblePluginError as e:
        warnings.warn(f'Unable to load plugin {plugin_name}: {e}')
        continue

    # Register the plugin as installed successfully
    registry['plugins']['installed'].append(plugin_name)

    plugin_module = "{}.{}".format(plugin_config.__module__, plugin_config.__name__)  # type: ignore

    # Gather additional apps to load alongside this plugin
    django_apps = plugin_config.django_apps
    if plugin_name in django_apps:
        django_apps.pop(plugin_name)
    if plugin_module not in django_apps:
        django_apps.append(plugin_module)

    # Test if we can import all modules (or its parent, for PluginConfigs and AppConfigs)
    for app in django_apps:
        if "." in app:
            parts = app.split(".")
            spec = importlib.util.find_spec(".".join(parts[:-1]))
        else:
            spec = importlib.util.find_spec(app)
        if spec is None:
            raise ImproperlyConfigured(
                f"Failed to load django_apps specified by plugin {plugin_name}: {django_apps} "
                f"The module {app} cannot be imported. Check that the necessary package has been "
                f"installed within the correct Python environment."
            )

    INSTALLED_APPS.extend(django_apps)

    # Preserve uniqueness of the INSTALLED_APPS list, we keep the last occurrence
    sorted_apps = reversed(list(dict.fromkeys(reversed(INSTALLED_APPS))))
    INSTALLED_APPS = list(sorted_apps)

    # Add middleware
    plugin_middleware = plugin_config.middleware
    if plugin_middleware and type(plugin_middleware) in (list, tuple):
        MIDDLEWARE.extend(plugin_middleware)

    # Create RQ queues dedicated to the plugin
    # we use the plugin name as a prefix for queue name's defined in the plugin config
    # ex: mysuperplugin.mysuperqueue1
    if type(plugin_config.queues) is not list:
        raise ImproperlyConfigured(f"Plugin {plugin_name} queues must be a list.")
    RQ_QUEUES.update({
        f"{plugin_name}.{queue}": RQ_PARAMS for queue in plugin_config.queues
    })

    events_pipeline = plugin_config.events_pipeline
    if events_pipeline:
        if type(events_pipeline) in (list, tuple):
            EVENTS_PIPELINE.extend(events_pipeline)
        else:
            raise ImproperlyConfigured(f"events_pipline in plugin: {plugin_name} must be a list or tuple")


# UNSUPPORTED FUNCTIONALITY: Import any local overrides.
try:
    from .local_settings import *
    _UNSUPPORTED_SETTINGS = True
except ImportError:
    pass
