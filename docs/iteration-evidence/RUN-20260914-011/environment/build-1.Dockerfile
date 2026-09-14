FROM python:3.10-slim
WORKDIR /workspace
COPY . /workspace/
RUN pip install --no-cache-dir pytest
