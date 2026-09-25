# =============================================================================
# JABUTI-SQL Docker Image for spider-agent-lite
# =============================================================================
#
# ADAPTATION NOTE:
# ────────────────
# This Dockerfile extends the existing spider_agent_postgres-image concept but
# is specifically tailored for the JABUTI-SQL benchmark.  Key differences:
#
# 1. Uses PostgreSQL 15 (matching the existing spider_agent_postgres-image).
# 2. Creates a `jabuti_sql` database (instead of `xlangdb`).
# 3. Adds psycopg2-binary for any Python-based PostgreSQL access.
# 4. The init.sh script starts PostgreSQL and creates the database.
#
# The DDL and data must be loaded separately after container startup via
# the setup_controller's execute_setup mechanism (or manually via psql).
#
# BUILD:
#   cd methods/spider-agent-lite
#   docker build -t spider_agent_jabuti-image \
#       -f spider_agent/images/spider_agent_jabuti-image/Dockerfile \
#       spider_agent/images/spider_agent_jabuti-image/
#
# ALTERNATIVELY, just use the existing spider_agent_postgres-image and load
# the jabuti_sql database at runtime.
# =============================================================================

FROM python:3.11

WORKDIR /workspace

# Update and install dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python packages
RUN pip install --upgrade pip

RUN pip install google-cloud-bigquery pyarrow db-dtypes pandas matplotlib \
    scikit-learn seaborn numpy scipy statsmodels xgboost plotly tabulate \
    snowflake-connector-python duckdb openpyxl psycopg2-binary

# Copy and run the init script (installs and configures PostgreSQL)
COPY init.sh .
RUN chmod +x init.sh && ./init.sh
RUN rm init.sh

CMD ["/bin/bash"]
