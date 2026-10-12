FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 AIC_HOST=0.0.0.0 AIC_PORT=8000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
COPY scripts/install.py scripts/install.py
# install.py loads the actual model, so copy the runtime before installation.
COPY app.py notation.py practice.py alignment.py site_security.py ./
COPY web/ web/
COPY scripts/start.py scripts/start.py
COPY third_party/ third_party/
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python scripts/install.py \
    && useradd --uid 10001 --create-home aic \
    && mkdir -p /app/var /app/.cache \
    && chown -R aic:aic /app
USER aic
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD .venv/bin/python -c "import os,urllib.request; port=os.environ.get('PORT',os.environ.get('AIC_PORT','8000')); urllib.request.urlopen('http://127.0.0.1:'+port+'/api/health',timeout=3)"
CMD [".venv/bin/python", "scripts/start.py"]
