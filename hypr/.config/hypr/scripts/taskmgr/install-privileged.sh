#!/bin/sh
# Install the root-owned PolicyKit helper and action file.
# Run this once after changing privileged_helper.py or the policy file.
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

sudo install -Dm0755 \
    "$script_dir/backend/privileged_helper.py" \
    /usr/local/libexec/taskmgr-privileged
sudo install -Dm0644 \
    "$script_dir/privileged/org.aditya.taskmgr.policy" \
    /usr/share/polkit-1/actions/org.aditya.taskmgr.policy

echo "Installed /usr/local/libexec/taskmgr-privileged"
echo "Installed /usr/share/polkit-1/actions/org.aditya.taskmgr.policy"
