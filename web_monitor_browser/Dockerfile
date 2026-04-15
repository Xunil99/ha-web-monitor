ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    nodejs \
    npm

# Install Python packages
RUN pip3 install --no-cache-dir --break-system-packages \
    playwright==1.49.1 \
    fastapi==0.115.0 \
    uvicorn[standard]==0.32.0 \
    websockets==13.1

# Install Playwright browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --with-deps 2>/dev/null || true

# Alternative: use system chromium if playwright install fails
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Copy application
COPY rootfs/ /

# Make run script executable
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
