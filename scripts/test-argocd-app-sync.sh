#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "${tmp_dir}/bin"

cat >"${tmp_dir}/bin/kubectl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

printf 'kubectl' >>"${COMMAND_LOG:?}"
for arg in "$@"; do
  printf '\t%s' "$arg" >>"$COMMAND_LOG"
done
printf '\n' >>"$COMMAND_LOG"

if [ "$*" = "-n argocd get applications -o name" ]; then
  printf '%s\n' application/homebridge application/tuppr
fi
SH

chmod +x "${tmp_dir}/bin/kubectl"

export PATH="${tmp_dir}/bin:${PATH}"
export COMMAND_LOG="${tmp_dir}/commands.log"

APP=tuppr "${repo_root}/scripts/argocd-app-sync.sh"
grep -F $'kubectl\t-n\targocd\tpatch\tapplication/tuppr\t--type\tmerge\t-p\t{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' "$COMMAND_LOG" >/dev/null

: >"$COMMAND_LOG"
"${repo_root}/scripts/argocd-app-sync.sh"
grep -F $'kubectl\t-n\targocd\tget\tapplications\t-o\tname' "$COMMAND_LOG" >/dev/null
grep -F $'kubectl\t-n\targocd\tpatch\tapplication/homebridge\t--type\tmerge\t-p\t{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' "$COMMAND_LOG" >/dev/null
grep -F $'kubectl\t-n\targocd\tpatch\tapplication/tuppr\t--type\tmerge\t-p\t{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' "$COMMAND_LOG" >/dev/null
