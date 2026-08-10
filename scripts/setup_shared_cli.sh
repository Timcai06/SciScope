#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_REPO="${SCISCOPE_REPO:-/home/liu/workspaces/sciscope/repo}"
CONFIG_ROOT="${HOME}/.config/shared-compute"
SOURCE_FILE="${CONFIG_ROOT}/bashrc"
MARKER='# >>> shared compute cli >>>'

install -d -m 0755 "${CONFIG_ROOT}"
install -m 0644 "${SCISCOPE_REPO}/scripts/remote/shared-compute.bash" \
  "${SOURCE_FILE}"

if ! grep -Fq "${MARKER}" "${HOME}/.bashrc"; then
  printf '\n%s\n' "${MARKER}" >>"${HOME}/.bashrc"
  printf '%s\n' '[[ -r "$HOME/.config/shared-compute/bashrc" ]] && source "$HOME/.config/shared-compute/bashrc"' >>"${HOME}/.bashrc"
  printf '%s\n' '# <<< shared compute cli <<<' >>"${HOME}/.bashrc"
fi

echo 'Shared compute helpers installed. Open a new SSH shell or run: source ~/.bashrc'

