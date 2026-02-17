FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libssl-dev \
    libffi-dev \
    wkhtmltopdf \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Neutral workdir (IMPORTANT)
WORKDIR /app

# deps - install Odoo requirements first, then extras (which may upgrade some deps)
COPY requirements.txt requirements-extra.txt ./
RUN uv pip install --system -r requirements.txt
RUN uv pip install --system -r requirements-extra.txt
# Upgrade psycopg2-binary — the pinned 2.9.5 bundles an old libpq that fails SCRAM auth on arm64
RUN uv pip install --system 'psycopg2-binary>=2.9.9'

RUN playwright install chromium && playwright install-deps chromium

# source
COPY odoo /opt/odoo/odoo
COPY setup.py setup.cfg /opt/odoo/
COPY setup /opt/odoo/setup
COPY entrypoint.sh /entrypoint.sh

# install odoo
RUN uv pip install --system -e /opt/odoo

# user
RUN useradd -m -s /bin/bash odoo && \
    mkdir -p /var/lib/odoo /var/log/odoo /etc/odoo && \
    chown -R odoo:odoo /var/lib/odoo /var/log/odoo /etc/odoo /opt/odoo

RUN chmod +x /entrypoint.sh

USER odoo

EXPOSE 8069 8072

ENTRYPOINT ["/entrypoint.sh"]
CMD ["-c", "/etc/odoo/odoo.conf"]
