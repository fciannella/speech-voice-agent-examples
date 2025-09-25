#!/bin/bash

# Copyright(c) 2021 NVIDIA Corporation. All rights reserved.

# NVIDIA Corporation and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA Corporation is strictly prohibited.

# Utility script to generate NVIDIA ACE Controller Github Release artifacts

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SOURCE_PATH="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TARGET_PATH="/tmp/ace_controller/"

echo "Creating GitHub Release artifacts for NVIDIA ACE Controller ..."

echo "Cleaning up target path ${TARGET_PATH} ..."
rm -rf ${TARGET_PATH}
mkdir -p ${TARGET_PATH}

echo "Copying source code to target path ${TARGET_PATH} ..."

cp -r ${SOURCE_PATH}/{src,pyproject.toml,flake.lock,flake.nix,uv.lock,.envrc,.python-version} ${TARGET_PATH}

# copy README.md, Licenses etc.
cp ${SOURCE_PATH}/{README.md,LICENSE,third_party_oss_license.txt,SECURITY.md,CHANGELOG.md,CLA.md,NVIDIA_PIPECAT.md,.gitignore,CONTRIBUTING.md} ${TARGET_PATH}/

echo "Copying examples to target path ${TARGET_PATH} ..."

mkdir -p ${TARGET_PATH}/examples
cp -r ${SOURCE_PATH}/examples/{speech-to-speech,voice_agent_webrtc,utils,static,README.md} ${TARGET_PATH}/examples/.

echo "Copying unit tests to target path ${TARGET_PATH} ..."

cp -r ${SOURCE_PATH}/tests/ ${TARGET_PATH}/.

# Removing __pycache__ and log files
echo "Removing __pycache__ and log files ..."
rm -rf ${TARGET_PATH}/{.,*,*/*,*/*/*,*/*/*/*,*/*/*/*/*,*/*/*/*/*/*}/__pycache__
rm -rf ${TARGET_PATH}/{.,*,*/*,*/*/*,*/*/*/*,*/*/*/*,*/*/*/*/*,*/*/*/*/*/*}/*.log

echo "GitHub Release artifacts for NVIDIA ACE Controller created successfully at ${TARGET_PATH}"
