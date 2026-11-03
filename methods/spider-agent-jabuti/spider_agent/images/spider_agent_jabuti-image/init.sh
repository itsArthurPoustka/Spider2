#!/bin/bash
# =============================================================================
# JABUTI-SQL PostgreSQL Initialization Script
# =============================================================================
set -e

apt-get update
apt-get install -y postgresql-client postgresql

# Configure default connection environment variables
cat << 'EOF' > /etc/profile.d/jabuti.sh
export PGHOST="${PGHOST:-jabuti-postgres}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-postgres}"
export PGDATABASE="${PGDATABASE:-jabuti_sql}"
EOF

chmod +x /etc/profile.d/jabuti.sh
echo 'source /etc/profile.d/jabuti.sh' >> ~/.bashrc
echo 'source /etc/profile.d/jabuti.sh' >> /etc/bash.bashrc

# Also configure .pgpass or trust authentication defaults
touch ~/.pgpass
chmod 600 ~/.pgpass

cd /workspace
