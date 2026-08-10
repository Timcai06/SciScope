#!/usr/bin/env bash
set -Eeuo pipefail

SCISCOPE_ROOT="${SCISCOPE_ROOT:-/home/liu/workspaces/sciscope}"
ARCHIVE="${SCISCOPE_XUNFEI_ARCHIVE:-${SCISCOPE_ROOT}/data/incoming/xunfei/environment.tar.gz}"
RECEIPT="${ARCHIVE}.sha256"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "Xunfei archive not found: ${ARCHIVE}" >&2
  exit 1
fi

if [[ -e "${ARCHIVE}.aria2" ]]; then
  echo "Xunfei archive is still downloading: ${ARCHIVE}.aria2 exists" >&2
  exit 1
fi

expected_bytes=15419870954
actual_bytes="$(stat -c '%s' "${ARCHIVE}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
  echo "Unexpected archive size: ${actual_bytes} bytes; expected ${expected_bytes}" >&2
  exit 1
fi

echo "Checking gzip stream integrity without extracting the archive..."
gzip -t "${ARCHIVE}"

echo "Recording the received-artifact SHA-256 (not a publisher-provided checksum)..."
sha256sum "${ARCHIVE}" | tee "${RECEIPT}"
chmod 0644 "${RECEIPT}"

echo "Xunfei delivery passed transport-level checks."
echo "No archive content was extracted, admitted, indexed, or embedded."

