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

# An init as PID 1 reaps the processes a call leaves to it: a completed call's watchdog exits after
# the program it watches, and whatever a command left running exits after the call. Run as PID 1, the
# server would never wait for them, and each would stay a zombie.
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

# Default command
ENTRYPOINT ["/usr/bin/tini", "--", "cluster-mcp"]
CMD ["-t", "http", "-H", "0.0.0.0", "-p", "8000"]
