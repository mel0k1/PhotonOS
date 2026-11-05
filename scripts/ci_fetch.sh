#!/bin/bash
# Скачивание артефактов CI: scripts/ci_fetch.sh <run_id> [smoke|iso]
set -e
cd /home/z/my-project/PhotonOS
TOKEN=$(git remote get-url origin | sed -E 's#https://[^:]+:([^@]+)@.*#\1#')
RUN=${1:?run_id}
WHAT=${2:-smoke}

hdr=(-H "Authorization: Bearer $TOKEN")
api() { curl -sS "${hdr[@]}" "https://api.github.com/repos/mel0k1/PhotonOS/$1"; }

case $WHAT in
  smoke) NAME=photon-smoke; DEST=/home/z/qemu/ci_smoke ;;
  iso)   NAME=PhotonOS-live-amd64; DEST=/home/z/qemu/iso ;;
esac

mkdir -p "$DEST"
# zip-архив артефакта (API: /artifacts -> id -> /zip)
ART_ID=$(api "actions/runs/$RUN/artifacts" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d.get('artifacts',[]):
    if a['name']=='$NAME':
        print(a['id']); break
")
[ -n "$ART_ID" ] || { echo "артефакт $NAME не найден"; exit 1; }
echo "артефакт $NAME id=$ART_ID -> $DEST"
curl -sL "${hdr[@]}" -o "$DEST/$NAME.zip" \
  "https://api.github.com/repos/mel0k1/PhotonOS/actions/artifacts/$ART_ID/zip"
cd "$DEST"
python3 - "$NAME.zip" <<'EOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
bad = z.testzip()
if bad: raise SystemExit(f"битый zip: {bad}")
z.extractall('.')
print("файлы:")
for n in z.namelist(): print(" ", n)
EOF
