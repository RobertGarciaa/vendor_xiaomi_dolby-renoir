# MiSound 권한과 서명

대상은 Redwood OS2.0.17.0.UMSMIXM의 `com.miui.misound`이며, 이 포팅은 UUID와
MIUI shim만 수정하고 원본 manifest의 요청 권한은 축소하지 않는다.

## 실제 부여 방식

MiSound는 `/product/app`의 **비특권 앱**이지만 플랫폼 인증서로 서명한다.
`signature|privileged` 권한은 플랫폼 서명 일치로 부여될 수 있다.
`privapp-permissions`는 비특권 앱에 권한을 부여하거나 플랫폼 서명 권한을 제한하는
목록이 아니다. 종전의 3개 권한만 부여된다는 설명은 잘못됐으며 해당 XML은 제거했다.

- `MODIFY_AUDIO_SETTINGS`: normal 권한. session-0 효과 제어에 사용.
- `WRITE_SECURE_SETTINGS`, `MODIFY_AUDIO_ROUTING`: 플랫폼 서명 경로의 권한.
- 그 밖에 원본이 요청한 플랫폼 signature 권한도 같은 서명으로 부여될 수 있다.
- `RECORD_AUDIO`, 위치, 전화, Bluetooth 등 runtime 권한은 서명만으로 일괄 허용되지
  않는다. 실제 부여 상태는 빌드의 기본 권한 정책과 사용자 선택을 별도로 확인한다.

DolbyControl은 `MODIFY_AUDIO_SETTINGS`, `RECEIVE_BOOT_COMPLETED` 및 audioserver
생존 콜백에 필요한 `MODIFY_AUDIO_ROUTING`을 요청한다. 마지막 권한의 근거는
AudioService의 `checkMonitorAudioServerStatePermission()`이다.

## 검증과 제한

부팅 후 `dumpsys package com.miui.misound` 및 `org.lineageos.dolby`에서 requested,
install/runtime permissions와 서명을 확인한다. 플랫폼 서명을 사용하므로 원본 APK가
요청하는 모든 signature 권한을 검토 대상으로 취급해야 한다. 최소 권한 manifest
재작성은 이번 변경에 포함하지 않았고, 기능별 사용 관계를 증명하기 전 제거하지 않는다.

원본 manifest 전문은 저장하지 않는다. OTA APK에서 `aapt2 dump xmltree`로 확인한다.
앱 자체의 `HEAR_PROTECT_SERVICE`, `CHILD_PROTECT_SERVICE`,
`AUDOO_ROUTE_CHOOSER` 정의는 원본 APK에 남으며, 추가 플랫폼 정의는 하지 않는다.
