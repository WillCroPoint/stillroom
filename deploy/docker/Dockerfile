FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# Binary wheels include libheif; fail rather than unexpectedly compiling native packages.
COPY requirements.txt /app/requirements.txt
RUN pip install --only-binary=:all: -r requirements.txt \
    && mkdir /data && chown 1000:1000 /data
COPY *.py /app/
COPY web/ /app/web/
COPY LICENSE /app/LICENSE
COPY deploy/docker/healthcheck.py /app/healthcheck.py
USER 1000:1000
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "/app/healthcheck.py"]
CMD ["python", "gui.py", "-n", "-b", "0.0.0.0", "-p", "8080", "-c", "/data/frames.json"]
