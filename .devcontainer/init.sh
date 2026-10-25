#!/usr/bin/env bash
# Runs on the HOST before the container is created (devcontainer.json initializeCommand).
# Writes DISPLAY_VALUE to .env for X11 forwarding and allows local Docker clients to
# connect to the host X server, without clobbering any other vars in .env.
#   macOS: XQuartz over the LAN IP (falls back to host.docker.internal)
#   Linux: the host's own $DISPLAY via the mounted /tmp/.X11-unix socket
set -uo pipefail

if command -v xhost >/dev/null 2>&1; then
	xhost +local:docker >/dev/null 2>&1 || true
fi

case "$(uname -s)" in
Darwin)
	IP=""
	for iface in en0 en1 en2; do
		IP="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
		[ -n "$IP" ] && break
	done
	DISPLAY_VALUE="${IP:-host.docker.internal}:0"
	# Docker Desktop proxies the host agent at this path.
	SSH_SOCK_HOST="/run/host-services/ssh-auth.sock"
	;;
*)
	DISPLAY_VALUE="${DISPLAY:-:0}"
	# Native Linux: forward the host agent socket directly.
	SSH_SOCK_HOST="${SSH_AUTH_SOCK:-/run/host-services/ssh-auth.sock}"
	;;
esac

# Ensure the known_hosts file bind-mounted by devcontainer.json exists on the host.
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/known_hosts"

# Make sure the host ssh-agent has a key to forward into the container. Non-fatal.
# Only macOS can fix this here (launchd already runs an agent); on Linux a script
# cannot start an agent that outlives it, so just warn.
if ! ssh-add -l >/dev/null 2>&1; then
	if [ "$(uname -s)" = "Darwin" ]; then
		echo "No keys in the host ssh-agent; running setup-ssh-agent.sh" >&2
		bash "$(dirname "$0")/scripts/setup-ssh-agent.sh" >&2 ||
			echo "Warning: SSH agent setup failed; run .devcontainer/scripts/setup-ssh-agent.sh manually" >&2
	else
		echo "Warning: no usable ssh-agent/keys on host; start an agent and ssh-add a key, then rebuild" >&2
	fi
fi

ENV_FILE=".devcontainer/.env"
touch "$ENV_FILE"
grep -v -e '^IP=' -e '^DISPLAY_VALUE=' -e '^SSH_SOCK_HOST=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
echo "DISPLAY_VALUE=$DISPLAY_VALUE" >> "$ENV_FILE.tmp"
echo "SSH_SOCK_HOST=$SSH_SOCK_HOST" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
