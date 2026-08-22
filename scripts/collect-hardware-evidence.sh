#!/bin/sh

set -eu
umask 077

PROGRAM=${0##*/}
COLLECTOR_VERSION=1

usage() {
  cat <<EOF
Usage:
  $PROGRAM snapshot [absolute-output-directory]
  $PROGRAM soak [absolute-output-directory] [interval-seconds] [sample-count]

The default soak schedule is 73 samples at 3600-second intervals (72 hours).
The output directory must not already exist. No credentials or complete NVRAM
dump are collected.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  snapshot|soak)
    MODE=$1
    shift
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

timestamp=$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || date +%s)
OUTPUT_DIR=${1:-/tmp/rm2100-hardware-evidence-$timestamp}
if [ "$#" -gt 0 ]; then
  shift
fi

case "$OUTPUT_DIR" in
  /*) ;;
  *)
    printf '%s\n' "error: output directory must be absolute: $OUTPUT_DIR" >&2
    exit 2
    ;;
esac

if [ -e "$OUTPUT_DIR" ]; then
  printf '%s\n' "error: output directory already exists: $OUTPUT_DIR" >&2
  exit 2
fi

INTERVAL=${1:-3600}
SAMPLES=${2:-73}
if [ "$MODE" = snapshot ] && [ "$#" -ne 0 ]; then
  printf '%s\n' "error: snapshot accepts only an optional output directory" >&2
  exit 2
fi
if [ "$MODE" = soak ] && [ "$#" -gt 2 ]; then
  printf '%s\n' "error: soak accepts at most interval and sample count" >&2
  exit 2
fi

case "$INTERVAL" in
  ''|*[!0-9]*)
    printf '%s\n' "error: interval must be a positive integer" >&2
    exit 2
    ;;
esac
case "$SAMPLES" in
  ''|*[!0-9]*)
    printf '%s\n' "error: sample count must be a positive integer" >&2
    exit 2
    ;;
esac
if [ "$INTERVAL" -lt 1 ] || [ "$SAMPLES" -lt 1 ] || [ "$SAMPLES" -gt 10000 ]; then
  printf '%s\n' "error: interval must be >= 1 and sample count must be 1-10000" >&2
  exit 2
fi

mkdir "$OUTPUT_DIR"
STATUS_FILE=$OUTPUT_DIR/collector-status.txt

note() {
  printf '%s\n' "$*" | tee -a "$STATUS_FILE"
}

capture() {
  output_name=$1
  shift
  if "$@" >"$OUTPUT_DIR/$output_name" 2>&1; then
    return 0
  else
    result=$?
    note "capture failed ($result): $output_name"
  fi
  return 0
}

capture_if_available() {
  output_name=$1
  command_name=$2
  shift 2
  if command -v "$command_name" >/dev/null 2>&1; then
    capture "$output_name" "$command_name" "$@"
  else
    note "command unavailable: $command_name"
  fi
}

capture_file() {
  output_name=$1
  source_file=$2
  if [ -r "$source_file" ]; then
    capture "$output_name" cat "$source_file"
  else
    note "file unavailable: $source_file"
  fi
}

collect_safe_nvram() {
  if ! command -v nvram >/dev/null 2>&1; then
    printf '%s\n' "nvram command unavailable"
    return 0
  fi

  # Keep this an explicit allowlist. Never replace it with `nvram show`.
  for key in productid firmver buildno extendno \
    rt_country_code wl_country_code sfe_enable http_access http_proto \
    sshd_enable telnetd_enable; do
    value=$(nvram get "$key" 2>/dev/null || true)
    printf '%s=%s\n' "$key" "$value"
  done
}

collect_sfe() {
  printf '%s\n' "[modules]"
  if [ -r /proc/modules ]; then
    grep -E '^(fast_classifier|shortcut_fe|shortcut_fe_ipv6)[[:space:]]' \
      /proc/modules || true
  fi
  printf '%s\n' "[skip_to_bridge_ingress]"
  if [ -r /sys/fast_classifier/skip_to_bridge_ingress ]; then
    cat /sys/fast_classifier/skip_to_bridge_ingress
  else
    printf '%s\n' "unavailable"
  fi
  printf '%s\n' "[exceptions]"
  if [ -r /sys/fast_classifier/exceptions ]; then
    cat /sys/fast_classifier/exceptions
  else
    printf '%s\n' "unavailable"
  fi
}

collect_thermal() {
  found=0
  for sensor in /sys/class/thermal/thermal_zone*/temp \
    /proc/temperature /proc/rt2880/temperature /proc/mt7621/temperature \
    /proc/mtk/temperature; do
    if [ -r "$sensor" ]; then
      value=$(head -n 1 "$sensor" 2>/dev/null || true)
      printf '%s=%s\n' "$sensor" "$value"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    printf '%s\n' "no readable temperature sensor found"
  fi
}

collect_process_status() {
  found=0
  for status_file in /proc/[0-9]*/status; do
    if [ -r "$status_file" ]; then
      awk '/^(Name|State|Pid|PPid|VmPeak|VmSize|VmRSS|Threads):/ { print }' \
        "$status_file"
      printf '\n'
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    printf '%s\n' "no readable process status found"
  fi
}

first_temperature() {
  for sensor in /sys/class/thermal/thermal_zone*/temp \
    /proc/temperature /proc/rt2880/temperature /proc/mt7621/temperature \
    /proc/mtk/temperature; do
    if [ -r "$sensor" ]; then
      value=$(head -n 1 "$sensor" 2>/dev/null | tr -cd '0-9.-' || true)
      if [ -n "$value" ]; then
        printf '%s' "$value"
        return 0
      fi
    fi
  done
  printf '%s' "NA"
}

collect_events() {
  pattern='sfe|fast_classifier|watchdog|oom|out of memory|panic|thermal|temperature|mt7615|mt76x3|error|failed'
  sensitive='pass(word|wd)?|pre.?shared|psk|secret|token|private.?key'
  if command -v dmesg >/dev/null 2>&1; then
    printf '%s\n' "[dmesg]"
    dmesg 2>/dev/null | grep -Ei "$pattern" |
      grep -Eiv "$sensitive" | tail -n 500 || true
  fi
  if command -v logread >/dev/null 2>&1; then
    printf '%s\n' "[logread]"
    logread 2>/dev/null | grep -Ei "$pattern" |
      grep -Eiv "$sensitive" | tail -n 500 || true
  fi
}

collect_clock_log() {
  if command -v dmesg >/dev/null 2>&1; then
    dmesg 2>/dev/null |
      grep -Ei 'CPU/OCP/SYS frequency|CPU.*MHz|clock.*MHz' |
      tail -n 50 || true
  fi
}

collect_radio_stats() {
  if ! command -v iwpriv >/dev/null 2>&1; then
    printf '%s\n' "iwpriv command unavailable"
    return 0
  fi
  for interface in ra0 rai0; do
    printf '[%s]\n' "$interface"
    iwpriv "$interface" stat 2>&1 || true
  done
}

record_sample() {
  sample_index=$1
  sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)
  epoch=$(date +%s 2>/dev/null || printf '%s' "NA")
  uptime_seconds=$(awk '{print $1}' /proc/uptime 2>/dev/null || printf '%s' "NA")
  load_one=$(awk '{print $1}' /proc/loadavg 2>/dev/null || printf '%s' "NA")
  memory=$(awk '
    /^MemFree:/ { free = $2 }
    /^MemAvailable:/ { available = $2 }
    /^Buffers:/ { buffers = $2 }
    /^Cached:/ { cached = $2 }
    /^SReclaimable:/ { reclaimable = $2 }
    /^Shmem:/ { shmem = $2 }
    END {
      if (!available && free)
        available = free + buffers + cached + reclaimable - shmem
      printf "%s %s", free ? free : "NA", available ? available : "NA"
    }
  ' /proc/meminfo 2>/dev/null || printf '%s' "NA NA")
  network=$(awk '
    NR > 2 {
      gsub(":", "", $1)
      rx_errors += $4
      rx_drops += $5
      tx_errors += $12
      tx_drops += $13
    }
    END { printf "%d %d %d %d", rx_errors, rx_drops, tx_errors, tx_drops }
  ' /proc/net/dev 2>/dev/null || printf '%s' "NA NA NA NA")
  temperature=$(first_temperature)

  # Word splitting is intentional for the fixed-width metric tuples above.
  # shellcheck disable=SC2086
  set -- $memory $network
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$sample_index" "$sample_utc" "$epoch" "$uptime_seconds" "$load_one" \
    "$1" "$2" "$temperature" "$3" "$4" "$5" "$6" >>"$OUTPUT_DIR/samples.tsv"
}

collect_snapshot() {
  capture_if_available uname.txt uname -a
  capture_if_available date-utc.txt date -u
  capture_if_available uptime.txt uptime
  capture process-status.txt collect_process_status
  capture_if_available filesystems.txt df -k
  capture_if_available mounts.txt mount
  capture_if_available interfaces.txt ifconfig -a
  capture_if_available routes.txt route -n
  capture_if_available listeners.txt netstat -lntu
  capture_if_available bridge.txt brctl show
  capture_if_available wireless.txt iwconfig
  capture_file proc-cpuinfo.txt /proc/cpuinfo
  capture_file proc-meminfo.txt /proc/meminfo
  capture_file proc-modules.txt /proc/modules
  capture_file proc-net-dev.txt /proc/net/dev
  capture_file proc-net-wireless.txt /proc/net/wireless
  capture_file proc-net-snmp.txt /proc/net/snmp
  capture_file proc-net-netstat.txt /proc/net/netstat
  capture safe-nvram.txt collect_safe_nvram
  capture sfe.txt collect_sfe
  capture thermal.txt collect_thermal
  capture clock-log.txt collect_clock_log
  capture radio-stats.txt collect_radio_stats
  capture relevant-events.txt collect_events
}

seal_evidence() {
  if ! command -v sha256sum >/dev/null 2>&1; then
    note "command unavailable: sha256sum"
    return 1
  fi
  if ! command -v mktemp >/dev/null 2>&1; then
    note "command unavailable: mktemp"
    return 1
  fi
  checksum_tmp=$(mktemp "${TMPDIR:-/tmp}/rm2100-sha256.XXXXXX")
  if (
    cd "$OUTPUT_DIR" || exit 1
    find . -type f ! -name SHA256SUMS | LC_ALL=C sort |
      while IFS= read -r evidence_file; do
        sha256sum "$evidence_file"
      done >"$checksum_tmp"
  ); then
    mv "$checksum_tmp" "$OUTPUT_DIR/SHA256SUMS"
  else
    result=$?
    rm -f "$checksum_tmp"
    return "$result"
  fi
}

note "collector_version=$COLLECTOR_VERSION"
note "mode=$MODE"
note "output=$OUTPUT_DIR"
note "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"

printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  sample_index utc epoch uptime_seconds load_1m mem_free_kib mem_available_kib \
  temperature_raw rx_errors rx_drops tx_errors tx_drops >"$OUTPUT_DIR/samples.tsv"

collect_snapshot

if [ "$MODE" = snapshot ]; then
  record_sample 0
else
  note "interval_seconds=$INTERVAL"
  note "sample_count=$SAMPLES"
  sample_index=0
  while [ "$sample_index" -lt "$SAMPLES" ]; do
    record_sample "$sample_index"
    sample_index=$((sample_index + 1))
    if [ "$sample_index" -lt "$SAMPLES" ]; then
      sleep "$INTERVAL"
    fi
  done
  capture_file proc-meminfo-final.txt /proc/meminfo
  capture_file proc-net-dev-final.txt /proc/net/dev
  capture sfe-final.txt collect_sfe
  capture thermal-final.txt collect_thermal
  capture relevant-events-final.txt collect_events
fi

note "completed_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
seal_evidence
printf '%s\n' "Hardware evidence: $OUTPUT_DIR"
