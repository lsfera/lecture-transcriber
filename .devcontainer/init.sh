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
	;;
*)
	DISPLAY_VALUE="${DISPLAY:-:0}"
	;;
esac

# Ensure the known_hosts file bind-mounted by devcontainer.json exists on the host.
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/known_hosts"

ENV_FILE=".devcontainer/.env"
touch "$ENV_FILE"
grep -v -e '^IP=' -e '^DISPLAY_VALUE=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
echo "DISPLAY_VALUE=$DISPLAY_VALUE" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
