#!/usr/bin/env python3
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

    # Temporary SQL debug wrapper: monkey-patch cursor.execute to log SQL statements
    import logging
    logging.basicConfig(filename='sql_debug.log', level=logging.DEBUG)
    from django.db import connections
    original_cursor_execute = None
    try:
        # We'll monkey-patch the sqlite3 and psycopg2 cursors when possible
        def _wrap_execute(cursor):
            if hasattr(cursor, '_orig_execute'):
                return
            orig = cursor.execute
            def exec_and_log(sql, params=None):
                try:
                    logging.debug(sql)
                except Exception:
                    pass
                return orig(sql, params) if params is not None else orig(sql)
            cursor._orig_execute = orig
            cursor.execute = exec_and_log
        # Attach wrapper to connection creation hook
        for conn in connections.all():
            try:
                cur = conn.cursor()
                _wrap_execute(cur)
            except Exception:
                pass
    except Exception:
        pass

    from django.core.management import execute_from_command_line

    try:
        execute_from_command_line(sys.argv)
    except Exception as e:
        # Attempt to dump last few lines of sql_debug.log
        try:
            with open('sql_debug.log') as f:
                lines = f.read().splitlines()[-50:]
            print('Last SQL statements (tail of sql_debug.log):')
            for l in lines:
                print(l)
        except Exception:
            print('Could not read sql_debug.log')
        raise

