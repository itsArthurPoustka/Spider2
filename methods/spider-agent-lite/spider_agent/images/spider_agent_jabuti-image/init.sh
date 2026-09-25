#!/bin/bash
# =============================================================================
# JABUTI-SQL PostgreSQL Initialization Script
# =============================================================================
#
# PURPOSE:
# This script is run during Docker image build to install and configure
# PostgreSQL inside the container.  It creates:
#   - A PostgreSQL server instance (v15)
#   - A database named `jabuti_sql`
#   - A user `postgres` with trust authentication (no password needed)
#
# HOW THE DATABASE GETS POPULATED:
# The DDL and data are NOT loaded during image build (the dump file is too
# large for the Docker build context).  Instead, the DDL is loaded at
# container startup time via the setup_controller's copy_all_subfiles
# mechanism + execute_setup commands in the task config.
#
# The `~/.bashrc` trick ensures PostgreSQL starts automatically when the
# container starts (the spider-agent framework doesn't run systemd).
# =============================================================================

# Define a function to execute a command and check the return value
execute_command() {
    "$@"
    local status=$?
    if [ $status -ne 0 ]; then
        echo "Command execution failed: $1"
        return 1
    fi
}

# Array of commands
commands=("apt update" "pip install --upgrade pip" "apt install -y postgresql")

# Loop to execute commands until all are successful
for cmd in "${commands[@]}"; do
    while true; do
        execute_command $cmd && break
    done
done

# Start PostgreSQL service
service postgresql start

# Create the jabuti_sql database
su - postgres <<EOF
psql -c "CREATE DATABASE jabuti_sql;"
psql -c "ALTER DATABASE jabuti_sql OWNER TO postgres;"
EOF

# Configure PostgreSQL to listen on all interfaces (needed for container networking)
echo "listen_addresses = 'localhost'" >> /etc/postgresql/15/main/postgresql.conf
echo "listen_addresses = '*'" >> /etc/postgresql/15/main/postgresql.conf

# Configure authentication (trust for local connections)
echo 'local   all             all                                     trust' >> /etc/postgresql/15/main/pg_hba.conf
echo 'host    all             all             0.0.0.0/0               trust' >> /etc/postgresql/15/main/pg_hba.conf

# Ensure PostgreSQL starts on container startup
echo 'service postgresql restart' >> ~/.bashrc
service postgresql restart

cd /workspace
