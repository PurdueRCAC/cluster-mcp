FROM python:3.14-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy the uv workspace: the root project, its lock, and every member under packages/
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/

# Install the root project, whose dependency cluster-mcp[slurm,rcac] builds the core and both of its
# capability extras, the Slurm and RCAC members, from packages/
RUN uv pip install --system -e .

# Default command
ENTRYPOINT ["cluster-mcp"]
CMD ["-t", "http", "-H", "0.0.0.0", "-p", "8000"]
