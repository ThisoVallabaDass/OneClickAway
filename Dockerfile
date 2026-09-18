FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY static ./static
COPY scripts ./scripts
RUN useradd --create-home studio && mkdir -p /var/lib/oneclick-away/data /var/lib/oneclick-away/output \
    && chown -R studio:studio /var/lib/oneclick-away
USER studio
ENV PYTHONUNBUFFERED=1 \
    STUDIO_DATA_DIR=/var/lib/oneclick-away/data \
    STUDIO_OUTPUT_DIR=/var/lib/oneclick-away/output
EXPOSE 8765
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765"]
