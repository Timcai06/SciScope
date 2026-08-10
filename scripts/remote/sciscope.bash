# Tim's private Bash fallback. It is loaded only by the `tim-bash` entry point
# and deliberately does not replace the shared account's login shell.

export SCISCOPE_ROOT="/home/liu/workspaces/sciscope"
export SCISCOPE_REPO="${SCISCOPE_ROOT}/repo"
export SCISCOPE_DATA="${SCISCOPE_ROOT}/data"
export SCISCOPE_MODELS="${SCISCOPE_ROOT}/models"
export SCISCOPE_ARTIFACTS="${SCISCOPE_ROOT}/artifacts"
export SCISCOPE_LOGS="${SCISCOPE_ROOT}/logs"
export PATH="${HOME}/.local/bin:${PATH}"

if [[ -r /home/liu/miniconda3/etc/profile.d/conda.sh ]]; then
  # shellcheck disable=SC1091
  source /home/liu/miniconda3/etc/profile.d/conda.sh
  conda activate sciscope
fi

alias gs='rtk git status --short'
alias glog='rtk git log --oneline --decorate -15'
alias gpu='watch -n 2 nvidia-smi'
alias cproj='cd "${SCISCOPE_REPO}"'
alias cdata='cd "${SCISCOPE_DATA}"'
alias cmodels='cd "${SCISCOPE_MODELS}"'
alias cartifacts='cd "${SCISCOPE_ARTIFACTS}"'
alias doctor='tim-doctor'
