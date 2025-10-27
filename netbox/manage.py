#!/usr/bin/env python3
import os
import sys

if __name__ == "__main__":
    # Use testing configuration when running tests
    if 'test' in sys.argv:
        os.environ.setdefault("NETBOX_CONFIGURATION", "netbox.configuration_testing")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
