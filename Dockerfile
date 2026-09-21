FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 REPORT_BIND=0.0.0.0 REPORT_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home monitor && mkdir /data && chown monitor:monitor /data
COPY worker ./worker
COPY cloud ./cloud
COPY schema.sql ./
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "cloud.server"]
