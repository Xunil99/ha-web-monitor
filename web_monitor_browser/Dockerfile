ARG BUILD_FROM
FROM ${BUILD_FROM}

# This add-on uses Playwright's official Docker image as runtime via switching base.
# However, HA add-on framework needs HA base for s6-overlay/bashio.
# Compromise: install everything fresh on Debian-based HA base image.

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and Playwright dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages in a virtualenv to avoid PEP 668 issues
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    playwright==1.49.1 \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.32.0"

# Install Chromium and all required system libraries via Playwright
RUN playwright install --with-deps chromium

# Copy application and s6 service
COPY rootfs/ /

# Make s6 service script executable
RUN chmod a+x /etc/s6-overlay/s6-rc.d/web-monitor/run
