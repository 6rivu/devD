import psycopg2
import sys

passwords = ['', 'postgres', 'cvolve_local_2026', 'admin', 'root', 'arpit']
working_password = None

print("Checking passwords...")
for pw in passwords:
    try:
        conn = psycopg2.connect(
            host='127.0.0.1',
            port=5432,
            user='postgres',
            password=pw,
            connect_timeout=3
        )
        print(f"SUCCESS: Connected to postgres with password: '{pw}'")
        working_password = pw
        conn.close()
        break
    except Exception as e:
        print(f"FAILED: Password '{pw}' failed: {e}")

if working_password is None:
    print("None of the standard passwords worked. Please check PostgreSQL config.")
    sys.exit(1)

# Check if cvolvepro database exists
try:
    conn = psycopg2.connect(
        host='127.0.0.1',
        port=5432,
        user='postgres',
        password=working_password
    )
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='cvolvepro'")
    exists = cursor.fetchone()
    if exists:
        print("Database 'cvolvepro' already exists.")
    else:
        print("Database 'cvolvepro' does not exist. Creating it...")
        cursor.execute("CREATE DATABASE cvolvepro OWNER postgres")
        print("Database 'cvolvepro' created successfully.")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Failed to check/create database: {e}")
