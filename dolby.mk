#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Dolby Atmos (Redwood HyperOS software DAP) for renoir.
#
# Enable from a device tree with:
#   $(call inherit-product, vendor/xiaomi/dolby-renoir/dolby.mk)
# The renoir device and board files gate the integration with
# TARGET_ENABLE_XIAOMI_DOLBY; set false to restore the stock audio config.
#
# The shima SKU is the one renoir actually boots with
# (ro.boot.product.vendor.sku=shima). Do not install this effects file for
# sku_lahaina/sku_yupik.
#

PRODUCT_SOONG_NAMESPACES += \
    vendor/xiaomi/dolby-renoir

# Redwood software DAP + Dolby MultiStream (DMS) HAL.
PRODUCT_PACKAGES += \
    libdapparamstorage \
    libdlbdsservice \
    libswdap \
    vendor.dolby.hardware.dms@2.0 \
    vendor.dolby.hardware.dms@2.0-impl \
    vendor.dolby.hardware.dms@2.0-service \
    dolby-dax-default.xml \
    vendor.dolby.hardware.dms@2.0-service.rc

# Settings entry, Quick Settings tile and the persistent effect owner.
PRODUCT_PACKAGES += \
    DolbyControl

# DolbyControl is privileged on /system. Platform signing does not replace
# the privileged allowlist on this build (missing entry aborts system_server).
PRODUCT_COPY_FILES += \
    vendor/xiaomi/dolby-renoir/configs/permissions/privapp-permissions-dolby-renoir.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/privapp-permissions-dolby-renoir.xml

# Ported MiSound: the original UI, profiles and equalizer, with the effect
# UUIDs rewritten to the software DAP. Built by tools/import-misound.sh, which
# verifies the input hash before patching. See README.md.
PRODUCT_PACKAGES += \
    MiSound

# MiSound is platform-signed and installed as a non-privileged product app.
# Signature permissions are resolved by PackageManager, not a privapp allowlist.

# Install the Dolby-extended effects config for the SKU renoir uses, keeping
# every existing effect. There is exactly one source for this destination:
# device/xiaomi/sm8350-common/common.mk no longer installs the stock
# sku_shima/audio_effects.xml (see that file), because AOSP keeps only the
# first PRODUCT_COPY_FILES entry per destination and the shared makefile is
# inherited first.
PRODUCT_COPY_FILES += \
    vendor/xiaomi/dolby-renoir/configs/audio/audio_effects_dolby.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio/sku_shima/audio_effects.xml

# Dolby advertises support to MiSound and to the settings entry. This is a
# vendor property read by the app (SystemProperties.getBoolean), so it must be
# in the vendor partition's build.prop.
PRODUCT_VENDOR_PROPERTIES += \
    ro.vendor.audio.dolby.dax.support=true

# SELinux policy for the DMS service domain and its private data directory is
# NOT added here. These are board variables: product makefiles are checked with
# them kept in a separate scope, so setting them here has no effect. The device
# BoardConfig must add:
#
#   BOARD_VENDOR_SEPOLICY_DIRS += vendor/xiaomi/dolby-renoir/sepolicy/vendor
#   SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS += vendor/xiaomi/dolby-renoir/sepolicy/public
#
# Public policy declares the HAL attributes; vendor policy grants the actual
# binderized audio effect host (hal_audio_default) DMS access. See README.md.

# The init.rc fragment is installed by the
# vendor.dolby.hardware.dms@2.0-service.rc prebuilt_etc module above
# (sub_dir "init"), so it must not be copied twice.
