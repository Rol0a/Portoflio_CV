# Small, single-purpose image: no framework, no exposed port, non-root.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY monitor.py .
RUN useradd -m noc
USER noc
CMD ["python", "monitor.py"]
