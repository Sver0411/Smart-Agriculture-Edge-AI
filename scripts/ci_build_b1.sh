#!/usr/bin/env bash
set -euo pipefail
profile=${1:?lab, light-sleep, lora-prototype or deep-sleep-experimental}
output=${2:?absolute isolated output directory}
case "$profile" in lab|light-sleep|lora-prototype|deep-sleep-experimental) ;; *) exit 2 ;; esac
case "$output" in /*) ;; *) echo 'Output must be absolute'; exit 2 ;; esac
root=$(cd "$(dirname "$0")/.." && pwd)
project="$root/firmware/b1"
mkdir -p "$output"
# A fresh configuration prevents private local sdkconfig from entering the build.
if [[ -e "$output/sdkconfig" ]]; then echo 'Use a fresh output directory'; exit 2; fi
idf.py --version | tee "$output/idf-version.log"
[[ $(idf.py --version) == 'ESP-IDF v5.4.4' ]] || { echo 'ESP-IDF v5.4.4 required'; exit 2; }
idf.py -C "$project" -B "$output/build" -D "SDKCONFIG=$output/sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$project/sdkconfig.defaults;$project/ci/public.defaults;$project/ci/$profile.defaults" \
    -D IDF_TARGET=esp32s3 build 2>&1 | tee "$output/build.log"
# Verify dependencies did not silently disable the requested profile.
if [[ "$profile" == light-sleep ]]; then
    grep -q '^CONFIG_B1_LIGHT_SLEEP=y$' "$output/sdkconfig"
    grep -q '^CONFIG_PM_ENABLE=y$' "$output/sdkconfig"
    grep -q '^CONFIG_FREERTOS_USE_TICKLESS_IDLE=y$' "$output/sdkconfig"
fi
if [[ "$profile" == lora-prototype || "$profile" == deep-sleep-experimental ]]; then
    grep -q '^CONFIG_B1_USE_E220=y$' "$output/sdkconfig"
    grep -q '^CONFIG_B1_E220_EXPECTED_REGISTERS="[^"]\+"$' "$output/sdkconfig"
fi
if [[ "$profile" == deep-sleep-experimental ]]; then
    grep -q '^CONFIG_B1_DEEP_SLEEP_EXPERIMENTAL=y$' "$output/sdkconfig"
fi
idf.py -C "$project" -B "$output/build" size 2>&1 | tee "$output/size.log"
python - "$output/build/smart_agriculture_b1.bin" "$output/manifest.json" "$profile" "$output/sdkconfig" "$root" <<'PY'
import hashlib,json,pathlib,sys,subprocess
binary=pathlib.Path(sys.argv[1])
pathlib.Path(sys.argv[2]).write_text(json.dumps({'idf':'v5.4.4','target':'esp32s3','profile':sys.argv[3],
    'binary_bytes':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
    'sdkconfig_sha256':hashlib.sha256(pathlib.Path(sys.argv[4]).read_bytes()).hexdigest(),
    'revision':subprocess.check_output(['git','-C',sys.argv[5],'rev-parse','HEAD'],text=True).strip(),
    'dirty':bool(subprocess.check_output(['git','-C',sys.argv[5],'status','--porcelain'],text=True)),
    'compiler':subprocess.check_output(['xtensa-esp32s3-elf-gcc','--version'],text=True).splitlines()[0],
    'source_sha256':{p:hashlib.sha256((pathlib.Path(sys.argv[5])/p).read_bytes()).hexdigest()
        for p in subprocess.check_output(['git','-C',sys.argv[5],'ls-files','firmware/b1','third_party','scripts/ci_build_b1.sh'],text=True).splitlines()
        if (pathlib.Path(sys.argv[5])/p).is_file()}},indent=2)+'\n')
PY
