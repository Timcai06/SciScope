# Tim's private zsh configuration. Loaded through ZDOTDIR by the `tim`
# entry point; it never replaces the shared account's ~/.zshrc or login shell.

if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

export SCISCOPE_ROOT="/home/liu/workspaces/sciscope"
export SCISCOPE_REPO="${SCISCOPE_ROOT}/repo"
export SCISCOPE_DATA="${SCISCOPE_ROOT}/data"
export SCISCOPE_MODELS="${SCISCOPE_ROOT}/models"
export SCISCOPE_ARTIFACTS="${SCISCOPE_ROOT}/artifacts"
export SCISCOPE_LOGS="${SCISCOPE_ROOT}/logs"
export PATH="${HOME}/.local/bin:${PATH}"

export ZSH="${HOME}/.local/share/tim/oh-my-zsh"
ZSH_THEME=""
plugins=(git docker python pip)
zstyle ':omz:update' mode disabled
source "${ZSH}/oh-my-zsh.sh"

source "${HOME}/.local/share/tim/powerlevel10k/powerlevel10k.zsh-theme"
[[ -r "${ZDOTDIR}/.p10k.zsh" ]] && source "${ZDOTDIR}/.p10k.zsh"

HISTFILE="${HOME}/.local/state/tim/zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_REDUCE_BLANKS

if [[ -r /usr/share/doc/fzf/examples/completion.zsh ]]; then
  source /usr/share/doc/fzf/examples/completion.zsh
fi
if [[ -r /usr/share/doc/fzf/examples/key-bindings.zsh ]]; then
  source /usr/share/doc/fzf/examples/key-bindings.zsh
fi

if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init zsh)"
fi

export CONDA_CHANGEPS1=false
if [[ -r /home/liu/miniconda3/etc/profile.d/conda.sh ]]; then
  source /home/liu/miniconda3/etc/profile.d/conda.sh
  conda activate sciscope
fi

alias ls='eza --icons=auto --group-directories-first'
alias ll='eza -lah --icons=auto --group-directories-first --git'
alias lt='eza --tree --level=2 --icons=auto'
alias gs='rtk git status --short'
alias gd='rtk git diff'
alias glog='rtk git log --oneline --decorate -15'
alias gpu='watch -n 2 nvidia-smi'
alias gpuonce='nvidia-smi'
alias cproj='cd "${SCISCOPE_REPO}"'
alias cdata='cd "${SCISCOPE_DATA}"'
alias cmodels='cd "${SCISCOPE_MODELS}"'
alias cartifacts='cd "${SCISCOPE_ARTIFACTS}"'
alias doctor='tim-doctor'

# Syntax highlighting should be sourced after all widgets and aliases.
[[ -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] && \
  source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
[[ -r /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] && \
  source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
