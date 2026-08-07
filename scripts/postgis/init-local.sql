SELECT 'CREATE DATABASE openskagit_test OWNER openskagit_local'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openskagit_test')\gexec
