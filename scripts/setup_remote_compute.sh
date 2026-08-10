#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
SCISCOPE_REPO="${SCISCOPE_REPO:-${SCISCOPE_ROOT}/repo}"
CONDA_ROOT="${CONDA_ROOT:-/home/liu/miniconda3}"
CONDA_ENV="${CONDA_ENV:-sciscope}"
SCISCOPE_GIT_URL="${SCISCOPE_GIT_URL:-https://github.com/Timcai06/SciScope.git}"
TARGET_USER="${SUDO_USER:-${USER}}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This setup script only supports Linux." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify the Linux distribution." >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "Expected Ubuntu, found ${ID:-unknown}." >&2
  exit 1
fi

if [[ ! -x "${CONDA_ROOT}/bin/conda" ]]; then
  echo "Expected Conda at ${CONDA_ROOT}; refusing to modify another installation." >&2
  exit 1
fi

install -d -m 0750 "${SCISCOPE_ROOT}" "${SCISCOPE_REPO}"

echo "[1/7] Refreshing apt metadata and installing base CLI tools"
sudo -v
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git git-lfs tmux curl ca-certificates gnupg \
  build-essential make pkg-config \
  ripgrep fd-find fzf bat tree aria2 htop nvtop ncdu lsof \
  postgresql-client jq rsync unzip p7zip-full shellcheck \
  zsh zoxide zsh-autosuggestions zsh-syntax-highlighting eza pv pigz

if [[ ! -d "${SCISCOPE_REPO}/.git" ]]; then
  echo "[1b/7] Cloning the SciScope main branch into the prepared workspace"
  clone_dir="$(mktemp -d "${SCISCOPE_ROOT}/.repo-clone.XXXXXX")"
  git clone --branch main --single-branch "${SCISCOPE_GIT_URL}" "${clone_dir}"
  rsync -a "${clone_dir}/" "${SCISCOPE_REPO}/"
  rm -rf -- "${clone_dir}"
fi

if [[ ! -f "${SCISCOPE_REPO}/backend/requirements.txt" ]]; then
  echo "SciScope source checkout is incomplete after clone." >&2
  exit 1
fi

echo "[2/7] Installing Docker Engine from Docker's official apt repository"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

docker_source="$(mktemp)"
trap 'rm -f "${docker_source}"' EXIT
cat >"${docker_source}" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-${VERSION_CODENAME}}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo install -m 0644 "${docker_source}" /etc/apt/sources.list.d/docker.sources
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "${TARGET_USER}"

echo "[3/7] Creating user-level command compatibility links"
install -d -m 0755 "${HOME}/.local/bin"
ln -sfn "$(command -v fdfind)" "${HOME}/.local/bin/fd"
ln -sfn "$(command -v batcat)" "${HOME}/.local/bin/bat"

echo "[4/7] Installing Rust Token Killer for Linux"
if ! command -v rtk >/dev/null 2>&1; then
  rtk_installer="$(mktemp)"
  curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh \
    -o "${rtk_installer}"
  sh "${rtk_installer}"
  rm -f "${rtk_installer}"
fi

echo "[5/7] Creating isolated Conda Python 3.11 environment"
# shellcheck disable=SC1091
source "${CONDA_ROOT}/etc/profile.d/conda.sh"
if ! conda env list | awk '{print $1}' | grep -Fxq "${CONDA_ENV}"; then
  conda create -n "${CONDA_ENV}" python=3.11 pip -y
fi
conda activate "${CONDA_ENV}"
python -m pip install --upgrade pip setuptools wheel

echo "[6/7] Installing GPU PyTorch and SciScope backend dependencies"
python -m pip install torch --index-url https://download.pytorch.org/whl/cu118
python -m pip install -r "${SCISCOPE_REPO}/backend/requirements.txt"

echo "[7/7] Configuring the project-scoped shell entry point"
install -d -m 0755 "${HOME}/.config/tim" "${HOME}/.local/bin"
install -m 0644 "${SCISCOPE_REPO}/scripts/remote/sciscope.bash" \
  "${HOME}/.config/tim/tim.bash"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/sciscope-entry" \
  "${HOME}/.local/bin/tim"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/inspect-remote" \
  "${HOME}/.local/bin/tim-doctor"
install -m 0755 "${SCISCOPE_REPO}/scripts/remote/sciscope-bash-entry" \
  "${HOME}/.local/bin/tim-bash"

if ! grep -Fq '# >>> sciscope remote >>>' "${HOME}/.bashrc"; then
  cat >>"${HOME}/.bashrc" <<'EOF'

# >>> sciscope remote >>>
export PATH="$HOME/.local/bin:$PATH"
# <<< sciscope remote <<<
EOF
fi

git -C "${SCISCOPE_REPO}" lfs install --local

echo
echo "Setup completed. Docker group membership takes effect after reconnecting."
echo "Reconnect, then run: tim"
