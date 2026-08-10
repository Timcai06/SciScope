#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
SCISCOPE_REPO="${SCISCOPE_REPO:-${SCISCOPE_ROOT}/repo}"
SHARE_ROOT="${HOME}/.local/share/tim"
CONFIG_BASE="${HOME}/.config/tim"
CONFIG_ROOT="${CONFIG_BASE}/zsh"
STATE_ROOT="${HOME}/.local/state/tim"

for command_name in git zsh zoxide eza tmux; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing ${command_name}; install the global CLI packages first." >&2
    exit 1
  fi
done

install -d -m 0755 "${SHARE_ROOT}" "${CONFIG_ROOT}" "${STATE_ROOT}" \
  "${HOME}/.local/bin"

if [[ ! -d "${SHARE_ROOT}/oh-my-zsh/.git" ]]; then
  git clone --depth 1 https://github.com/ohmyzsh/ohmyzsh.git \
    "${SHARE_ROOT}/oh-my-zsh"
fi

if [[ ! -d "${SHARE_ROOT}/powerlevel10k/.git" ]]; then
  git clone --depth 1 https://github.com/romkatv/powerlevel10k.git \
    "${SHARE_ROOT}/powerlevel10k"
fi

install -m 0644 "${SCISCOPE_REPO}/scripts/remote/sciscope.zshrc" \
  "${CONFIG_ROOT}/.zshrc"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/sciscope-entry" \
  "${HOME}/.local/bin/tim"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/sciscope-bash-entry" \
  "${HOME}/.local/bin/tim-bash"
install -m 0644 "${SCISCOPE_REPO}/scripts/remote/sciscope.bash" \
  "${CONFIG_BASE}/tim.bash"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/inspect-remote" \
  "${HOME}/.local/bin/tim-doctor"

touch "${STATE_ROOT}/zsh_history"
chmod 0600 "${STATE_ROOT}/zsh_history"

echo "Tim zsh workspace installed. Run: tim"
