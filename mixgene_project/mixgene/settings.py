# Django settings for mixgene project.
MAIN_LOG_LEVEL = "DEBUG"
DEBUG = True

from local_settings import *

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql', # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': DATABASE_NAME,                      # Or path to database file if using sqlite3.
        # The following settings are not used with sqlite3:
        'USER': DATABASE_USER,
        'PASSWORD': DATABASE_PASSWORD,
        'HOST': '',                      # Empty for localhost through domain sockets or '127.0.0.1' for localhost through TCP.
        'PORT': '',                      # Set to empty string for default.
        "init_command": 'SET storage_engine=INNODB,    \
              SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
    }
}

#TODO: use redis

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/var/tmp/django_cache',
    }
}

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

## Celery
import djcelery
djcelery.setup_loader()

BROKER_URL = 'redis://%s:%s/0' % (REDIS_HOST, REDIS_PORT)
BROKER_TRANSPORT_OPTIONS = {'visibility_timeout': 360000} # 100-hours
CELERY_RESULT_BACKEND = BROKER_URL

CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = 'Europe/Prague'
CELERY_IMPORTS = (
    "webapp.tasks",
    "workflow.common_tasks",
    # "wrappers.gt",
    # "wrappers.pca",
    # "wrappers.svm",
    # "wrappers.aggregation",
)
CELERYD_HIJACK_ROOT_LOGGER = False
CELERY_ACCEPT_CONTENT = ['pickle', 'json']

## End celery settings

#BASE_DIR = '/var/run/mixgene'  # from local settings
# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/var/www/example.com/media/"

R_LIB_CUSTOM_PATH = BASE_DIR + '/media/data/R'

#R: .libPaths(c("/home/kost/res/mixgene_workdir/data/R",.libPaths()))


# Hosts/domain names that are valid for this site; required if DEBUG is False
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
# ALLOWED_HOSTS = []

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'Europe/Prague'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True


MEDIA_ROOT = BASE_DIR + '/media'

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://example.com/media/", "http://media.example.com/"
MEDIA_URL = ''

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = BASE_DIR + '/static'

# URL prefix for static files.
# Example: "http://example.com/static/", "http://static.example.com/"
STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    SOURCE_DIR + '/static/',
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)



# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    #'django.middleware.cache.UpdateCacheMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',

    #'django.middleware.cache.FetchFromCacheMiddleware',
)

ROOT_URLCONF = 'mixgene.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'mixgene.wsgi.application'

# SOURCE


INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'south',
    'djcelery',
    'django_extensions',

    'webapp',
    'workflow',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    #'django_nose',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
)

#TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOG_DIR = BASE_DIR + "/logs"

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s|%(levelname)s][%(module)s:%(lineno)s:%(funcName)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'celery_fmt': {
            'format': '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'file_info': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'formatter': 'verbose',
            'filename': LOG_DIR + '/info.log',
            'when': 'midnight',
            'interval': 1,
            'backupCount': 3,
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'formatter': 'verbose',
            'filename': LOG_DIR + '/debug.log',
            'when': 'midnight',
            'interval': 1,
            'backupCount': 3,
        },
        'console': {
            'level': 'DEBUG',
            'formatter': 'verbose',
            'class': 'logging.StreamHandler'
        },
    },
    'loggers': {
        'mixgene': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'workflow': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'converters': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'wrappers': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'webapp': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'environment': {
            'handlers': ['file_debug', 'file_info', 'console'],
            'level': MAIN_LOG_LEVEL,
            'propagate': True,
        },
        'django.request': {
            'handlers': ['file_info', 'file_debug', 'console'],
            'level': 'INFO',
            'propagate': True,
        }
    }
}
