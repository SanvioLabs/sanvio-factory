# The factory's dev container: Python 3.12 on Debian bookworm, with a non-root user called vscode.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# git for the worktrees, tmux for the loop's session. No official feature installs tmux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tmux \
    && rm -rf /var/lib/apt/lists/*

# The two sign-in volumes mount here. Making the folders now, owned by vscode, stops their
# first use creating them owned by root, where Claude Code and gh couldn't write their sign-ins.
RUN mkdir -p /home/vscode/.claude /home/vscode/.config/gh \
    && chown -R vscode:vscode /home/vscode/.claude /home/vscode/.config/gh \
    && chown vscode:vscode /home/vscode/.config
