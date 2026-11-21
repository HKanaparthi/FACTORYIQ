FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy seed script and tag model from simulator
COPY seed_baseline.py .
COPY ../simulator/tag_model.py .

CMD ["python", "seed_baseline.py"]
