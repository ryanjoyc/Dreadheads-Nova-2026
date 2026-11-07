FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN pip install --no-deps --no-build-isolation -e .
CMD ["uvicorn", "nova_backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
