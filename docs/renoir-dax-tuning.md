# Renoir DAX 튜닝: 커널·컨테이너 대조 및 측정 절차

작성일: 2026-10-23. 단계: 정적 분석과 측정 준비 완료, 청감·음향 튜닝 미완료.
대상은 Mi 11 Lite 5G(renoir) 전용이다. Redwood SW DAP/MiSound 구성은 유지한다.

## 이번 결정

채널 매핑 조사(D) → 앰프·리소스 분석(A) → 실측과 후보 튜닝(C) 순서로 진행한다.
정적 자료로 알 수 있는 경계는 이번에 추적했다. 플래시 후 기기의 실제 경로가
확인되기 전까지 DAX 수치와 앰프 설정을 바꾸지 않는다. 자동 EQ APK는 현재 단계에서
추가하지 않는다. 먼저 아래 도구로 경로를 확인해야 자동화의 입력 조건이 성립한다.

Redwood 값은 **비교 기준**이며, renoir에 최적화되었거나 음향적으로 안전하다고
새로 입증된 값이 아니다. 음질 개선을 완료했다고 보고하지 않는다.

## 커널 비교에서 실제로 확인한 것

자료는 로컬 `kernel/xiaomi/sm8350`의 두 기기 DTS와 각 앰프 드라이버다.
별도의 최신 Redwood 출하 커널을 새로 확보한 것은 아니다.

| 경계 | renoir | Redwood |
|---|---|---|
| 기기 DTS | `renoir-sm7350.dtsi:13–40` | `redwood-sm7325.dtsi:22–71` |
| 상단 | `tfa98xx_1@34`, top pinctrl | `aw882xx_smartpa@35`, TOP 주석 |
| 하단 | `tfa98xx_2@35`, bot pinctrl | `aw882xx_smartpa@34`, BOT 주석 |
| 채널 근거 | 컨테이너 RCV sink 0=slot 0, SPK sink 0=slot 1 | DTS 상단 sound-channel=0, 하단=1 |
| 제어 파서 | TFA PM 컨테이너·bitfield·프로필 | AW 장치 설정·프로필·채널·monitor |
| 보호 관련 경계 | TFA 캘리브레이션 및 ADSP 전달 경로 | AW 온도/전압 monitor와 ipeak/gain/vmax 선택 |

Redwood `aw_device.h:29–30`은 채널 0/1을 PRI_L/PRI_R로 이름 붙인다.
`aw_device.c:1409–1430`은 DTS `sound-channel`을 장치에 저장한다.
이는 드라이버 논리 채널의 근거다. 실제 재생 PCM부터 앰프 입력까지 모두 검증한
것은 아니므로 DAX L/R과 물리 출력의 완전한 동일성으로 확대하지 않는다.
두 AW 드라이버 계열이 소스에 존재한다. 출하 모듈 선택/칩 ID를 런타임에서 읽지
않았으므로 디렉터리 존재만으로 AW88263S 실리콘과 드라이버 변종을 확정하지 않는다.

**중요:** 두 기기의 상·하단 I²C 주소가 반대다. 주소 기준으로 튜닝을 복사하면 안 된다.
RCV/SPK라는 물리적 역할과 L/R이라는 논리 채널은 양립한다. “상·하단이므로 L/R이
아니다”가 아니라, 방향과 라우팅에 따라 L/R이 각 물리 출력으로 매핑된다.

## TFA 컨테이너 재검증

스톡 파일: `vendor/firmware/tfa98xx.cnt`, 3,828B.
SHA-256: `5be2bd9002beef1f7222450be59118b0d34f8d8338c67a35aa1d65c6e071d09e`.
저장 CRC와 커널 방식으로 계산한 CRC 모두 `0xdec118be`다.
컨테이너 대상 문자열은 `9873N1B`이며 실리콘 ID를 읽은 결과는 아니다.

기존 파서에서 빠졌던 device 공통 설정을 복원했다.

| 필드 | RCV 0x34 | SPK 0x35 | 커널 헤더 의미 |
|---|---:|---:|---|
| `TDMSPKS 0x2603` | 0 | 1 | sink 0 TDM 슬롯 |
| `TDMDCS 0x2643` | 1 | 0 | sink 1 TDM 슬롯 |
| `AUDFS 0x0203` | 9 | 9 | 커널 `tfa98xx_sr_from_field()` 기준 96,000Hz |
| `INPLEV 0x0240` | 0 | 0 | TDM output attenuation 제어값 |
| `TDMSPKG 0x5f63` | 6 | 6 | INPLEV에 의존하는 channel 0 gain 제어값 |
| `DCMCC 0x7003` | 9 | 9 | max coil current 제어값 |
| `DCVOS 0x7695` | 46 | 46 | second boost voltage 제어값 |

위 숫자를 dB, A, V 등의 물리 단위로 임의 변환하지 않는다.
96kHz는 컨테이너 설정이고, DAX `tuned_rate=48000`은 DAP 설정이다. 둘의 존재만으로
샘플레이트 오류라고 할 수 없으며, 활성 PCM/ADSP 변환 경로를 따로 확인한다.
`TFA_NON_DSP_SOLUTION` 분기에도 `tfa98xx_adsp_send_calib_values()`가 있다.
매크로 이름이나 `speaker.prot.enable` 하나만으로 보호 유무를 단정하지 않는다.

프로필 `DEFAULT` 뒤의 값은 일반 활성 설정이 아닌 복원 영역이다. handset은
TDMSPKG=11, TDMDCE=0, DCVOS=34를 사용하고, DEFAULT 뒤에는 6/1/46이 있다.
기존 파서처럼 양쪽을 한 목록으로 읽어 마지막 값을 활성값으로 취급하면 틀린다.
커널 `tfaContWriteRegsProf()`는 DEFAULT에서 멈춘다. 이전 프로필의 복원 처리도
관여하므로, 파서 출력은 실행 순서를 완전히 에뮬레이션한 현재 레지스터 상태가 아니다.

일반 stereo/left/right 항목에서 EQ FILTER를 발견하지 못했다. 공통 PATCH는
`TFA9873N1B0_dummy.patch`이고, calibrate.cal에는 원본 calibration 메시지 파일들이
있다. 이것은 **해당 컨테이너에 일반 재생 EQ 계수가 보이지 않는다**는 뜻이다.
ACDB/ADSP/MiSound와 실제 칩의 다른 상태까지 EQ가 없다는 증거는 아니다.

## DAX GEQ와 optimizer 관계

현재 추출본 `libswdap.so`에서 별도 상태와 별도 setter가 확인됐다.

| 함수 RVA | 관측 |
|---|---|
| `0x11e97c` graphic_equalizer_enable_set | DAP 인스턴스 `+0xbac`에 enable 저장 |
| `0x11e9d4` graphic_equalizer_bands_set | 인스턴스 `+0xb48`을 GEQ configure에 전달 |
| `0x11ecc8` audio_optimizer_enable_set | `*(instance+0x10b8)+0x78`에 enable 저장 |
| `0x11ed30` audio_optimizer_bands_set | `*(instance+0x10b8)`을 optimizer configure에 전달 |
| `0x118d1c` optimizer_configure | 채널별 포인터 배열을 순회하여 gains 처리 |
| `0x119444` graphic_equalizer_configure | 한 개 gains 벡터 처리 |

따라서 GEQ의 20개 값이 optimizer의 L/R 40개 값을 직접 덮어쓴다는 전제는 맞지 않는다.
Java controller의 param 110은 GEQ 제어로 선언되어 있다. 같은 주파수 표를 쓴다는
이유로 물리 스피커별 optimizer 보정의 대체 수단으로 사용할 수 없다.

두 필터가 활성일 때 최종 응답이 어떻게 결합되는지, limiter/virtualizer 등 다른
단계를 거친 뒤 dB 단위로 단순 가산할 수 있는지는 아직 검증하지 않았다.
configure 내부 GEQ에는 ±576, optimizer에는 ±480의 raw 경계값을 전달하는 코드가
있지만, 그것을 사용자 입력의 허용 범위나 dB 환산식으로 확정하지 않는다.
자동 보정 구현 전에 param 전달, 단위, enable, output route, readback을 함께 검증한다.

현재 DAX 3.3 파일에서 확인한 speaker tuning은 landscape와 portrait **두 개**다.
landscape는 20/20 밴드가 nonzero이며 전부 L/R 비대칭, portrait는 20/20 zero다.
두 프로필 모두 optimizer enable=true다. 이 파일에는 별도 landscape180 tuning이
없다. 과거 다른 DAX 파일의 미러 관계를 이 추출본에 적용하지 않는다.

## ACDB·MiSound 분석 범위

- `Forte_Speaker_cal.acdb`: 847,317B, QCMSNDDB/AVDB. 8-byte tag + u32 length
  형태의 62개 최상위 청크를 파일 끝까지 범위 검사하며 분해했다. AVOLLUT0,
  AFE LUT0 등의 청크 존재를 확인했다. 내부 module/parameter·LUT 및 계수 단위는
  아직 해석하지 않았다. 최신 SM8450 ACDB 파서는 이 구형 형식과 달라 재사용하지 않았다.
- `misound_res_spk.bin`: 18,524B. SPKD/SPMD/MMFD, MODL 0–3 후보, 20개 SMPR/NSOS/COEF
  태그 위치를 기록했다. SMPR 뒤에 44100/48000/88200/96000/192000이 관측된다.
  바이너리 내 문자열 패턴 관측이지 완전한 파일 문법 검증이 아니다. COEF 뒤 값을
  chunk 길이라고 해석하면 틀린다. SOS 계수 순서/부호/적용 모드가 미확정이므로
  이 자료에서 역필터나 새 DAX 곡선을 계산하지 않았다.

## 추가·개선한 도구

- `tools/tfa-cnt-dump.py`: CRC/크기/경계 검사, devid 필드 정정, device 공통 설정,
  chip-specific bitfield 이름·register/shift/width/mask, DEFAULT 복원 영역,
  embedded file 이름/크기/해시. 쓰기 기능 없음.
- `tools/test_tfa_cnt_dump.py`: 정상·복원 영역, CRC 손상, truncation/size,
  유효 CRC를 갖는 잘못된 descriptor 경계 검사. 합성 데이터만 사용.
- `tools/dax-speaker-audit.py`: speaker optimizer/GEQ preset 원시값 및 비대칭 목록.
- `tools/audio-tuning-inventory.py`: ACDB 청크와 MiSound 태그 관측 목록. 원본 미수정.
- `tools/make-channel-probe.py`: PCM16 stereo/48kHz, 750Hz, peak −36dBFS,
  0.5초 L → 무음 → 0.5초 R WAV와 타임라인 JSON. 생성만 하고 재생하지 않는다.
- `tools/collect-audio-route.py`: 명시 실행 시 읽기 전용 ADB 스냅샷. root 전환,
  calibration 읽기/쓰기, mixer 쓰기, 앱 설치, 볼륨·EQ 변경을 하지 않는다.

재현 예시(저장소 루트):

```sh
python3 tools/tfa-cnt-dump.py "$STOCK/vendor/firmware/tfa98xx.cnt" \
  --field-header "$KERNEL/techpack/audio/asoc/codecs/tfa98xx/inc/tfa9873_tfafieldnames.h" \
  --json /tmp/renoir-tfa.json
python3 -m unittest discover -s tools -p 'test_tfa_cnt_dump.py' -v
python3 tools/dax-speaker-audit.py proprietary/vendor/etc/dolby/dax-default.xml \
  --json /tmp/dax-speaker.json
python3 tools/audio-tuning-inventory.py \
  "$STOCK/vendor/etc/acdbdata/Forte/Forte_Speaker_cal.acdb" \
  "$STOCK/vendor/lib/rfsa/adsp/misound_res_spk.bin" --json /tmp/stock-audio.json
python3 tools/make-channel-probe.py /tmp/renoir-channel-probe.wav
```

`STOCK`과 `KERNEL`은 각각 스톡 덤프와 커널 루트로 설정한다. 출력 파일을
저장소에 블롭으로 추가하지 않는다. probe 생성기는 기존 파일 덮어쓰기를 거부한다.

## 플래시 후 수행할 채널 매핑 게이트

1. 현재 빌드/부팅 상태와 TFA 파일 SHA-256, Dolby 실제 effect descriptor·제어권·
   profile/GEQ readback을 기록한다. 서비스 존재만으로 효과 활성이라 판단하지 않는다.
2. 낮은 미디어 볼륨에서 probe를 재생하고 상단/하단 각각 L/R 구간의 실제 출력을
   기록한다. PCM −36dBFS는 패널 음압 보증이 아니다. 최초에는 짧게 청취한다.
   원본 file은 수정하지 않으며 mono accessibility·player remix 여부도 기록한다.
3. Dolby OFF/ON, 세로/가로 양방향, PCM/offload 가능한 경로별로 별도 기록한다.
   ON에서 virtualizer가 양쪽으로 소리를 퍼뜨리면 단일 채널=단일 앰프로 강제 해석하지 않는다.
4. 재생 중 `python3 tools/collect-audio-route.py /tmp/audio-portrait-off`처럼
   **매회 새 디렉터리**에 mixer, AudioFlinger, audio policy 상태를 수집한다.
   실패한 명령은 manifest returncode로 구분한다. mixer 값 쓰기는 하지 않는다.
5. HAL `Swap channel`/speaker-reverse 전환, TFA Profile 및 DAX orientation 선택과
   실제 물리 출력을 연결한다. 재생 중 마이크 캡처를 켜면 HAL의 concurrent capture
   분기에서 swap이 억제될 수 있어, 캡처 유무를 반드시 나눈다.

한 가지 방향에서 상단=L로 들렸다는 결과만으로 모든 방향/모드의 매핑을 확정하지 않는다.

## 그다음 튜닝과 합격 기준

매핑 확정 → 동일 볼륨/위치의 baseline 반복 측정 → optimizer 후보 하나 변경 →
readback·양 채널 응답·왜곡·클리핑·상태 복원 비교 순서다. 내장 마이크 기록은 상대
비교 자료이며 마이크 응답과 자동 처리가 섞여 절대 평탄화 목표로 쓰지 않는다.

GEQ는 먼저 사용자 음색 조정용으로 유지한다. 별도 채널별 optimizer 후보는 물리
측정과 실제 DAP 단위·경로를 확인한 뒤 구성한다. RCV의 저역 제한을 완화하거나
Redwood의 328/469Hz 감쇠를 임의로 되돌리지 않는다. DAX regulator/MBDRC와
renoir TFA/ACDB 보호는 별개 경계이므로 gain만 보고 보호 동등성을 주장하지 않는다.

완료 조건은 소리 출력뿐 아니라 ON/OFF, preset/EQ 변경, 방향 전환, 볼륨 단계,
수화부 통화 경로 회귀, 유선/BT 출력 분리, 재부팅 복원 및 SELinux 검증이다.
현재는 이 실측을 수행하지 않았다. ROM 빌드·플래시, 기기 연결/재생, DAX/앰프
값 변경은 이번 정적 분석 작업에 포함하지 않았다.
