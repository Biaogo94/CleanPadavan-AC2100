#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOCK_FILE="${LOCK_FILE:-$REPOSITORY/config/build-lock.json}"
PROFILE_FILE="${PROFILE_FILE:-$REPOSITORY/config/rm2100-3.4.config}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPOSITORY/dist}"
CACHE_DIR="${CACHE_DIR:-$REPOSITORY/.cache/downloads}"
PYTHON="${PYTHON:-python3}"
CPU_FREQUENCY="${CPU_FREQUENCY:-bootloader}"
ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE:-$REPOSITORY/config/default-admin-password}"
WIFI_PASSWORD_FILE="${WIFI_PASSWORD_FILE:-$REPOSITORY/config/default-wifi-password}"
export LC_ALL=C

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

lock_value() {
  "$PYTHON" "$REPOSITORY/tools/firmware.py" lock-value "$LOCK_FILE" "$1"
}

download_checked() {
  local url="$1"
  local expected_sha256="$2"
  local target="$3"
  local temporary="${target}.part.$$"

  if [[ -f "$target" ]] && printf '%s  %s\n' "$expected_sha256" "$target" | sha256sum --check --status; then
    return
  fi

  curl --fail --location --silent --show-error \
    --retry 5 --retry-all-errors --connect-timeout 20 \
    --output "$temporary" "$url"
  printf '%s  %s\n' "$expected_sha256" "$temporary" | sha256sum --check --status \
    || die "SHA-256 mismatch for $url"
  mv -- "$temporary" "$target"
}

for command_name in curl date fakeroot find git sha256sum tar tee; do
  require_command "$command_name"
done

[[ -f "$ADMIN_PASSWORD_FILE" ]] || die "administrator password file not found: $ADMIN_PASSWORD_FILE"
[[ -f "$WIFI_PASSWORD_FILE" ]] || die "Wi-Fi password file not found: $WIFI_PASSWORD_FILE"

"$PYTHON" "$REPOSITORY/tools/firmware.py" validate-lock "$LOCK_FILE"
"$PYTHON" "$REPOSITORY/tools/firmware.py" validate-profile "$PROFILE_FILE"
"$PYTHON" "$REPOSITORY/tools/firmware.py" validate-credentials \
  "$ADMIN_PASSWORD_FILE" "$WIFI_PASSWORD_FILE"

SOURCE_URL="$(lock_value source.url)"
SOURCE_COMMIT="$(lock_value source.commit)"
SOURCE_DATE_EPOCH="$(lock_value source.source_date_epoch)"
TOOLCHAIN_URL="$(lock_value archives.toolchain.url)"
TOOLCHAIN_SHA256="$(lock_value archives.toolchain.sha256)"
OPENSSL_URL="$(lock_value archives.openssl.url)"
OPENSSL_SHA256="$(lock_value archives.openssl.sha256)"
KBUILD_BUILD_TIMESTAMP="$(date --utc --date="@$SOURCE_DATE_EPOCH" '+%a %b %d %H:%M:%S UTC %Y')"
export SOURCE_DATE_EPOCH
export TZ=UTC
export KBUILD_BUILD_TIMESTAMP
export KBUILD_BUILD_USER=cleanpadavan
export KBUILD_BUILD_HOST=reproducible
export KBUILD_BUILD_VERSION=1

if [[ -z "${BUILD_ROOT:-}" ]]; then
  BUILD_ROOT="$(mktemp -d -t cleanpadavan-rm2100.XXXXXXXX)"
  REMOVE_BUILD_ROOT=1
else
  mkdir -p -- "$BUILD_ROOT"
  REMOVE_BUILD_ROOT=0
fi

cleanup() {
  if [[ "$REMOVE_BUILD_ROOT" == 1 && "${KEEP_BUILD_ROOT:-0}" != 1 ]]; then
    rm -rf -- "$BUILD_ROOT"
  fi
}
trap cleanup EXIT

SOURCE_DIR="$BUILD_ROOT/rt-n56u"
[[ ! -e "$SOURCE_DIR" ]] || die "build source path already exists: $SOURCE_DIR"
RENDERED_PROFILE="$BUILD_ROOT/rm2100-3.4.config"
BUILD_LOG="$BUILD_ROOT/build.log"
WARNING_REPORT="$BUILD_ROOT/build-warning-policy.json"
"$PYTHON" "$REPOSITORY/tools/firmware.py" configure-profile \
  "$PROFILE_FILE" "$RENDERED_PROFILE" --cpu-frequency "$CPU_FREQUENCY"
mkdir -p -- "$CACHE_DIR"
mkdir -p -- "$OUTPUT_DIR"
if find "$OUTPUT_DIR" -mindepth 1 -print -quit | grep -q .; then
  die "output directory must be empty: $OUTPUT_DIR"
fi

TOOLCHAIN_ARCHIVE="$CACHE_DIR/mipsel-linux-uclibc.tar.xz"
OPENSSL_ARCHIVE="$CACHE_DIR/openssl-1.1.1w.tar.gz"
download_checked "$TOOLCHAIN_URL" "$TOOLCHAIN_SHA256" "$TOOLCHAIN_ARCHIVE"
download_checked "$OPENSSL_URL" "$OPENSSL_SHA256" "$OPENSSL_ARCHIVE"

git init --quiet "$SOURCE_DIR"
git -C "$SOURCE_DIR" remote add origin "$SOURCE_URL"
git -C "$SOURCE_DIR" fetch --quiet --depth=1 origin "$SOURCE_COMMIT"
git -C "$SOURCE_DIR" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$SOURCE_DIR" rev-parse HEAD)" == "$SOURCE_COMMIT" ]] \
  || die "upstream checkout does not match the Source Lock"

mkdir -p -- "$SOURCE_DIR/toolchain-mipsel/toolchain-3.4.x"
tar -xJf "$TOOLCHAIN_ARCHIVE" -C "$SOURCE_DIR/toolchain-mipsel/toolchain-3.4.x"
cp -- "$OPENSSL_ARCHIVE" "$SOURCE_DIR/trunk/libs/libssl/openssl-1.1.1w.tar.gz"

"$PYTHON" "$REPOSITORY/tools/firmware.py" prepare-source "$SOURCE_DIR" \
  --profile "$RENDERED_PROFILE" \
  --admin-password-file "$ADMIN_PASSWORD_FILE" \
  --wifi-password-file "$WIFI_PASSWORD_FILE"
"$PYTHON" "$REPOSITORY/tools/firmware.py" verify-source-policy "$SOURCE_DIR" \
  --report "$BUILD_ROOT/runtime-policy.json"

(
  cd -- "$SOURCE_DIR/trunk"
  fakeroot ./build_firmware RM2100
) 2>&1 | tee "$BUILD_LOG"
"$PYTHON" "$REPOSITORY/tools/firmware.py" verify-build-log "$BUILD_LOG" \
  --report "$WARNING_REPORT"

mapfile -d '' images < <(find "$SOURCE_DIR/trunk/images" -maxdepth 1 -type f \
  -name 'RM2100_3.4*.trx' -print0)
[[ "${#images[@]}" == 1 ]] \
  || die "expected one RM2100 3.4 firmware image, found ${#images[@]}"

image_name="$(basename -- "${images[0]}")"
case "$CPU_FREQUENCY" in
  bootloader) cpu_variant="cpu-bootloader" ;;
  800|900|1000) cpu_variant="cpu-${CPU_FREQUENCY}mhz" ;;
  *) die "unsupported CPU frequency: $CPU_FREQUENCY" ;;
esac
bundle_image_name="${image_name%.trx}-${cpu_variant}.trx"
cp -- "${images[0]}" "$OUTPUT_DIR/$bundle_image_name"
cp -- "$LOCK_FILE" "$OUTPUT_DIR/build-lock.json"
cp -- "$RENDERED_PROFILE" "$OUTPUT_DIR/rm2100-3.4.config"
cp -- "$SOURCE_DIR/trunk/linux-3.4.x/.config" "$OUTPUT_DIR/kernel-3.4.config"
cp -- "$BUILD_ROOT/runtime-policy.json" "$OUTPUT_DIR/runtime-policy.json"
cp -- "$WARNING_REPORT" "$OUTPUT_DIR/build-warning-policy.json"

"$PYTHON" "$REPOSITORY/tools/firmware.py" verify-kernel-config \
  "$OUTPUT_DIR/kernel-3.4.config" \
  --cpu-frequency "$CPU_FREQUENCY" \
  --report "$OUTPUT_DIR/performance-profile.json"

BUILDER_COMMIT="$(git -C "$REPOSITORY" rev-parse HEAD)"
"$PYTHON" "$REPOSITORY/tools/firmware.py" verify-image "$OUTPUT_DIR/$bundle_image_name" \
  --manifest "$OUTPUT_DIR/manifest.json" \
  --profile "$RENDERED_PROFILE" \
  --source-commit "$SOURCE_COMMIT" \
  --builder-commit "$BUILDER_COMMIT" \
  --expected-timestamp "$SOURCE_DATE_EPOCH"

(
  cd -- "$OUTPUT_DIR"
  sha256sum "$bundle_image_name" manifest.json build-lock.json \
    rm2100-3.4.config kernel-3.4.config performance-profile.json \
    runtime-policy.json build-warning-policy.json > SHA256SUMS
)

printf 'Firmware Bundle: %s\n' "$OUTPUT_DIR"
