# CleanPadavan RM2100 Firmware

This context defines the build and release language for the Redmi AC2100 firmware maintained by this repository.

## Language

**Firmware Profile**:
The complete, reviewable feature policy for the RM2100 Linux 3.4 firmware.
_Avoid_: template tweaks, sed customization, clean edition

**Source Lock**:
The immutable upstream source revision and verified external archives used by a build.
_Avoid_: master, latest source, current upstream

**Provisioned Build**:
A build that receives deployment-specific administrator and Wi-Fi credentials through protected files and rejects universal defaults.
_Avoid_: default build, public-password build

**Firmware Bundle**:
One verified RM2100 firmware image plus its manifest and SHA-256 checksums.
_Avoid_: artifact glob, image folder

**Hardware Qualification**:
The recorded device tests that prove a Firmware Bundle can be promoted for production deployment.
_Avoid_: successful compilation, CI green

**Production Release**:
A Firmware Bundle whose Source Lock, software checks, credential policy, and Hardware Qualification all passed.
_Avoid_: nightly, build artifact, release candidate
