#!/bin/bash
# Load an SSH key into the local platform's agent so it can be forwarded
# into the devcontainer via Docker Desktop's /run/host-services/ssh-auth.sock
# (see .devcontainer/devcontainer.json).
set -euo pipefail

KEY="${1:-$HOME/.ssh/id_ed25519}"

if [ ! -f "$KEY" ]; then
    echo "No key found at $KEY" >&2
    exit 1
fi

case "$(uname -s)" in
    Darwin)
        # macOS: launchd already runs ssh-agent (SSH_AUTH_SOCK is preset).
        # --apple-use-keychain persists the passphrase across reboots.
        ssh-add --apple-use-keychain "$KEY"

        CONFIG="$HOME/.ssh/config"
        touch "$CONFIG"
        if ! grep -q "UseKeychain yes" "$CONFIG" 2>/dev/null; then
            {
                echo ""
                echo "Host *"
                echo "  AddKeysToAgent yes"
                echo "  UseKeychain yes"
                echo "  IdentityFile $KEY"
            } >> "$CONFIG"
            echo "Added Host * block to $CONFIG"
        fi
        ;;
    Linux)
        # WSL2 counts as Linux here and behaves the same way.
        if [ -z "${SSH_AUTH_SOCK:-}" ] || ! ssh-add -l >/dev/null 2>&1; then
            eval "$(ssh-agent -s)"
            RC="$HOME/.bashrc"
            grep -q 'eval "$(ssh-agent -s)"' "$RC" 2>/dev/null || {
                echo ""
                echo "# Auto-start ssh-agent"
                echo 'eval "$(ssh-agent -s)" >/dev/null'
                echo "ssh-add -l >/dev/null 2>&1 || ssh-add $KEY >/dev/null 2>&1"
            } >> "$RC"
            echo "Added ssh-agent bootstrap to $RC"
        fi
        ssh-add "$KEY"
        ;;
    *)
        echo "Unrecognized platform: $(uname -s)" >&2
        echo "On native Windows (no WSL2), use the OpenSSH Agent service instead:" >&2
        echo "  Set-Service ssh-agent -StartupType Automatic; Start-Service ssh-agent; ssh-add $KEY" >&2
        echo "Note: native Windows also needs npiperelay for SSH_AUTH_SOCK forwarding into Docker;" >&2
        echo "using Docker Desktop's WSL2 backend avoids this entirely." >&2
        exit 1
        ;;
esac

echo "Loaded keys:"
ssh-add -l
