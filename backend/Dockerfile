FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml constraints-linux-cpu.txt ./

# Install the CPU wheel from PyTorch's CPU index before resolving Sentence
# Transformers. The exact constraint prevents a later resolver from replacing
# it with the default PyPI CUDA-enabled Linux distribution.
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.8.0+cpu" \
    && python -c 'import tomllib; from pathlib import Path; p=tomllib.loads(Path("pyproject.toml").read_text()); deps=p["build-system"]["requires"] + p["project"]["dependencies"] + p["project"]["optional-dependencies"]["dev"]; Path("/tmp/knowflow-requirements.txt").write_text("\n".join(deps) + "\n")' \
    && python -m pip install --no-cache-dir \
        --constraint constraints-linux-cpu.txt \
        --requirement /tmp/knowflow-requirements.txt

# Source is copied after the dependency layer so ordinary code edits do not
# reinstall Python dependencies. Runtime imports resolve from WORKDIR (/app).
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY tests ./tests

RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
