# Trading Automation Update

Last updated: 2026-07-01

## สถานะล่าสุด

โปรเจกต์ขยับจากชุดเครื่องมือวิเคราะห์ ไปสู่ระบบเก็บผลลัพธ์และเรียนรู้จาก signal จริงแล้วบางส่วน

ระดับปัจจุบัน:

```text
Level 1: Auto collect signals              - partially done
Level 2: Auto track outcomes               - done for cached forward outcomes
Level 3: Auto paper trade                  - infrastructure done, waiting for fresh eligible signals
Level 4: Auto calibration report           - partially visible in dashboard
Level 5: Auto suggest rule changes         - early readiness-based suggestions
Level 6: Auto adjust weights with limits   - not yet
Level 7: Real-money execution approval     - intentionally not yet
```

สิ่งที่ทำเสร็จแล้ว:

- เพิ่ม `Signal Results` tab ใน dashboard
- เพิ่ม `scripts/signal_ledger.py`
  - ตาราง `signal_ledger`
  - ตาราง `signal_outcome`
  - ingest thesis จาก `state/theses`
  - track forward outcomes ที่ 5D / 20D / 60D จาก `price_bar`
- เพิ่ม `scripts/auto_paper.py`
  - dry-run เป็น default
  - เปิด paper trade เฉพาะเมื่อใช้ `--execute`
  - กัน stale signal
  - กัน duplicate open paper position
  - link paper trade กลับไปที่ signal ledger
- เพิ่ม tests:
  - `scripts/tests/test_signal_ledger.py`
  - `scripts/tests/test_auto_paper.py`

ผลจากข้อมูลปัจจุบัน:

```text
Ledger signals: 28
Forward-tested signals: 27
vcp-screener 5D outcomes: 27
vcp-screener 5D win rate: 44%
vcp-screener avg 5D return: +0.2%
vcp-screener 20D outcomes: 11
vcp-screener avg 20D return: +2.2%
Auto-paper eligible: 0
```

เหตุผลที่ `Auto-paper eligible = 0`:

- signal ปัจจุบันมาจาก 2026-05-25
- gate ปัจจุบันรับเฉพาะ signal อายุไม่เกิน 10 วัน
- ไม่มี signal สดที่ผ่าน `score >= 70`

นี่เป็นพฤติกรรมที่ถูกต้อง เพราะระบบไม่ควรเปิด paper trade จาก signal เก่าจนกลายเป็น backfill หลอกตัวเอง

## คำสั่งใช้งานปัจจุบัน

Ingest thesis เข้า signal ledger:

```powershell
uv run python scripts\signal_ledger.py ingest-theses
```

Update forward outcomes:

```powershell
uv run python scripts\signal_ledger.py update-outcomes --market TH
uv run python scripts\signal_ledger.py update-outcomes --market US
```

ดู summary:

```powershell
uv run python scripts\signal_ledger.py summary --market TH
```

Auto-paper dry-run:

```powershell
uv run python scripts\auto_paper.py --market TH --min-score 70 --max-age-days 10
```

Auto-paper execute:

```powershell
uv run python scripts\auto_paper.py --market TH --min-score 70 --max-age-days 10 --execute
```

คำสั่ง `--execute` เปิดเฉพาะ paper trade ไม่ใช่เงินจริง

## แผนพัฒนาส่วนที่เหลือ

### Phase A: ทำ daily automation ให้ครบ

เป้าหมาย:

ให้ระบบทำงานเองหลังตลาดปิด แม้ผู้ใช้ไม่ได้เข้า dashboard

งานที่ต้องทำ:

- สร้าง orchestrator เช่น `scripts/run_daily_signal_pipeline.py`
- ลำดับงาน:
  1. run fresh analysis / screeners
  2. ingest new theses/signals เข้า `signal_ledger`
  3. update forward outcomes ของ signals เก่า
  4. run auto-paper dry-run
  5. ถ้า config อนุญาต ให้ auto-paper execute
  6. export daily summary report
- เพิ่ม config file เช่น `state/automation_config.yaml`
- เพิ่ม Windows Task Scheduler หรือ batch runner

Definition of done:

- รันคำสั่งเดียวแล้วจบครบ loop
- dashboard เห็น signal ใหม่และ outcome ใหม่
- ไม่มี duplicate paper positions
- default ยังไม่แตะเงินจริง

### Phase B: ทำ signal export ให้เป็นมาตรฐาน

เป้าหมาย:

ทุก screener ต้องส่งออก signal format เดียวกัน ไม่ใช่พึ่ง thesis YAML อย่างเดียว

งานที่ต้องทำ:

- กำหนด canonical schema:

```text
signal_id
symbol
market
source_skill
signal_date
direction
raw_score
entry_price
stop_price
target_price
time_horizon
market_regime
reason
payload_json
```

- ปรับ VCP / CANSLIM / PEAD / Thai screeners ให้ export signal records
- เพิ่ม validator สำหรับ signal JSON
- ให้ `signal_ledger.py` ingest ได้ทั้งจาก thesis และ signal JSON

Definition of done:

- ไม่ต้องพึ่ง manual thesis ingestion อย่างเดียว
- signal ใหม่เข้าระบบอัตโนมัติทุกวัน
- dashboard แยก source ได้ถูกต้อง

### Phase C: Auto-paper policy และ risk guard

เป้าหมาย:

ทำให้ Level 3 ปลอดภัยขึ้นและควบคุม risk ของ paper portfolio ได้

งานที่ต้องทำ:

- เพิ่ม policy config:

```yaml
auto_paper:
  enabled: false
  market: TH
  min_score: 70
  max_age_days: 10
  max_new_positions_per_day: 3
  max_open_positions: 10
  default_stop_pct: 8
  target_r: 2
  require_regime_allowed: true
```

- เพิ่ม guard:
  - ห้ามเปิดถ้า market regime เป็น restrictive
  - ห้ามเปิดถ้า source ยังไม่มี sample เพียงพอ แล้วเปิดขนาดเล็กเท่านั้น
  - ห้ามเปิดถ้าซ้ำ symbol
  - จำกัดจำนวน position ต่อวัน
  - จำกัดจำนวน open paper positions รวม

Definition of done:

- auto-paper เปิดได้เฉพาะเมื่อผ่าน policy
- dashboard บอกเหตุผลได้ว่า signal ถูก skip เพราะอะไร

### Phase D: Calibration report แบบจริงจัง

เป้าหมาย:

ให้ dashboard ตอบได้ว่า source ไหนเริ่มน่าเชื่อถือ และควรใช้ใน regime ไหน

งานที่ต้องทำ:

- เพิ่ม metrics:
  - 5D / 20D / 60D win rate
  - average return
  - average R เมื่อมี stop
  - hit stop rate
  - hit target rate
  - MAE / MFE
  - score bucket calibration
  - regime-specific expectancy
- เพิ่ม dashboard sections:
  - Source Reliability
  - Score Bucket Calibration
  - Best/Worst Regime
  - Sample Confidence

Definition of done:

- sample < 30 แสดงเป็น `Collecting`
- sample 30-99 แสดงเป็น `Calibrating`
- sample >= 100 แสดงเป็น `Validated` หรือ `Needs Revision` ตามผลลัพธ์

### Phase E: Postmortem automation

เป้าหมาย:

ปิด loop จาก signal outcome ไปสู่ improvement backlog

งานที่ต้องทำ:

- สร้าง postmortem record เมื่อ:
  - signal ครบ 5D / 20D / 60D
  - paper trade ปิด
- บันทึก:
  - source
  - regime
  - outcome category
  - false positive / true positive
  - notes
- เชื่อมกับ `signal-postmortem`
- สร้าง feedback files สำหรับปรับ rule/weight

Definition of done:

- dashboard เห็น postmortem count > 0
- มี improvement backlog ที่อิงจาก performance จริง ไม่ใช่แค่ readiness

### Phase F: Rule improvement engine

เป้าหมาย:

ให้ระบบเสนอการปรับปรุงจากหลักฐานจริง

งานที่ต้องทำ:

- สร้าง rule suggestions:
  - reduce weight ใน regime ที่ false positive สูง
  - เพิ่ม min score
  - ลด/เพิ่ม stop pct
  - เปลี่ยน holding period
  - disable source ชั่วคราวถ้า edge decay
- ใส่ sample confidence:

```text
sample < 30: warning only
30 <= sample < 100: soft suggestion
sample >= 100: rule change candidate
```

Definition of done:

- suggestion ทุกอันมี evidence
- ไม่มี auto-adjust จาก sample เล็ก
- ผู้ใช้ approve ก่อนเปลี่ยน rule จริง

### Phase G: Scheduler / unattended mode

เป้าหมาย:

ให้ระบบทำงานเองตามเวลา

งานที่ต้องทำ:

- Windows batch เช่น `run_daily_pipeline.bat`
- optional Task Scheduler setup doc
- logging:
  - `logs/daily_signal_pipeline.log`
  - `reports/daily_signal_summary_YYYY-MM-DD.md`
- failure handling:
  - data fetch fail
  - API key missing
  - no eligible signals
  - DB locked

Definition of done:

- ผู้ใช้ไม่ต้องเปิด dashboard ทุกวัน
- วันไหนไม่มี signal ก็มี summary ว่าไม่มี เพราะอะไร

## สิ่งที่ยังไม่ควรทำตอนนี้

- ยังไม่ควร auto-buyเงินจริง
- ยังไม่ควรปรับ strategy weight อัตโนมัติจาก sample ต่ำ
- ยังไม่ควรเพิ่ม screener ใหม่จำนวนมากก่อน calibration แข็งแรง
- ยังไม่ควร treat win rate 5D เพียงอย่างเดียวเป็นคำตอบสุดท้าย

## ลำดับที่แนะนำต่อจากนี้

1. ทำ `run_daily_signal_pipeline.py`
2. เพิ่ม `automation_config.yaml`
3. ให้ fresh analysis export signal JSON มาตรฐาน
4. ให้ auto-paper execute ได้หลัง dry-run ผ่าน
5. เพิ่ม calibration dashboard แบบ score bucket / horizon / regime
6. เพิ่ม postmortem auto generation
7. เพิ่ม rule suggestion engine

## หลักการสำคัญ

ระบบนี้ควรเป็น autonomous research and paper-trading system ก่อน ไม่ใช่ auto-trading bot

เป้าหมายระยะใกล้:

```text
คุณติดงานได้
ระบบยังเก็บ signal ทุกวัน
ตามผลทุกตัว
เปิด paper เฉพาะตัวที่ผ่าน gate
สรุปว่า source ไหนเริ่มใช้ได้
แล้วเสนอ improvement จากหลักฐานจริง
```

## Implementation Update: 2026-07-01

งานที่ลงมือเพิ่มแล้ว:

- แก้ syntax error ใน `skills/macro-regime-detector/scripts/fmp_client.py` ที่ทำให้ pytest collection หยุด
- แก้ error handling ใน `skills/paper-trade-simulator/scripts/paper_trade.py`
  - ถ้า discipline warning check ล้มเหลว ระบบยังเปิด paper position ได้
  - เพิ่ม warning กลับไปในผลลัพธ์แทนการทำให้ flow ล้มทั้งก้อน
- เพิ่ม `scripts/run_daily_signal_pipeline.py`
  - optional analysis trigger ผ่าน dashboard API
  - ingest thesis เข้า signal ledger
  - update forward outcomes
  - run auto-paper แบบ dry-run หรือ execute ตาม config
  - export daily summary เป็น JSON และ Markdown
- เพิ่ม `state/automation_config.yaml`
  - default ปลอดภัย: `analysis.enabled=false`
  - default auto-paper เป็น dry-run: `auto_paper.execute=false`
- เพิ่ม `scripts/tests/test_daily_signal_pipeline.py`
- ปรับ `scripts/signal_ledger.py` ให้ update outcomes ไม่ล้มเมื่อ DB ใหม่ยังไม่มี `price_bar`

คำสั่ง daily pipeline:

```powershell
uv run python scripts\run_daily_signal_pipeline.py --config state\automation_config.yaml --market TH
```

ถ้าต้องการระบุวันทดสอบ:

```powershell
uv run python scripts\run_daily_signal_pipeline.py --config state\automation_config.yaml --market TH --as-of 2026-07-01
```

ผล dry-run ล่าสุด:

```text
Ingest: 28 total, 0 inserted, 28 updated
Outcomes updated: 84
Complete outcomes: 38
Auto-paper eligible: 0
Auto-paper opened: 0
Dry-run: true
```

รายงานถูกสร้างที่:

```text
reports/daily-signal-pipeline/daily_signal_pipeline_2026-07-01.json
reports/daily-signal-pipeline/daily_signal_pipeline_2026-07-01.md
```

Verification ล่าสุด:

```text
21 passed
ruff: all checks passed for touched files
py_compile: passed for touched Python files
```

หมายเหตุ:

`uv run pytest -q` ทั้ง repo ยังไม่ green ทั้งหมด มี failure เดิมจำนวนมากใน skill อื่น ๆ และ encoding issue บน Windows test บางชุด ดังนั้นตอนนี้ถือว่า verified เฉพาะระบบที่แก้/เพิ่มในรอบนี้ก่อน

## Implementation Update: Canonical Signal Ingest

งานที่ลงมือเพิ่มแล้ว:

- เพิ่ม source normalization:
  - `vcp` → `vcp-screener`
  - `vcp_screener` → `vcp-screener`
  - `canslim` / `canslim_screener` → `canslim-screener`
  - `thai_swing_dip` → `thai-swing-dip`
  - `thai_swing_momentum` → `thai-swing-momentum`
- เพิ่ม canonical signal JSON ingest ใน `scripts/signal_ledger.py`
  - รองรับ `signals[]` schema กลาง
  - รองรับ fallback จาก report เดิม:
    - `reports/vcp_screener_*.json`
    - `reports/canslim_screener_*.json`
    - `reports/thai_swing_*.json`
  - ดึง `entry/stop/target` จาก `plan` ของ Thai swing ได้
- เพิ่มคำสั่ง:

```powershell
uv run python scripts\signal_ledger.py ingest-signals reports\thai_swing_2026-07-01_171537.json
```

- ต่อ daily pipeline ให้ ingest signal files จาก config:

```yaml
signal_files:
  enabled: true
  patterns:
    - state/signals/*.json
    - state/signals/*.yaml
    - reports/vcp_screener_*.json
    - reports/canslim_screener_*.json
    - reports/thai_swing_*.json
  max_files_per_pattern: 3
```

ผล dry-run ล่าสุดหลัง ingest signal files:

```text
Ledger signals: 82
canslim-screener: 40
vcp-screener: 28
thai-swing-momentum: 12
thai-swing-dip: 2
Auto-paper eligible: 3
Auto-paper opened: 0
```

Auto-paper candidates ล่าสุด:

```text
EASTW.BK  thai-swing-momentum  score 80.2  entry 4.60  stop 4.37  target 5.05
AH.BK     thai-swing-dip       score 79.3  entry 13.90 stop 13.59 target 14.52
INET.BK   thai-swing-momentum  score 72.8  entry 4.26  stop 4.08  target 4.62
```

Dashboard API verified:

```text
paper_sources: thai-swing-dip, vcp-screener
source_readiness rows: canslim-screener, thai-swing-dip, thai-swing-momentum, vcp-screener
```

Verification:

```text
22 passed
ruff: all checks passed for touched files
py_compile: passed
dashboard API: eligible=3 and vcp source normalized
```

## Implementation Update: GCP Online Automation

งานที่ลงมือเพิ่มแล้ว:

- เพิ่ม `scripts/run_gcp_daily_pipeline.sh`
  - wrapper สำหรับ cron/systemd บน GCP VM
  - รัน `scripts/run_daily_signal_pipeline.py`
  - เขียน log แยกตาม market:
    - `logs/daily_signal_pipeline_TH.log`
    - `logs/daily_signal_pipeline_US.log`
  - ใช้ lock file ผ่าน `flock` ถ้ามี เพื่อกัน pipeline รันซ้อน
- เขียน `scripts/setup_gcp_cron.sh` ใหม่เป็น ASCII ทั้งไฟล์
  - แก้ปัญหาอักขระเพี้ยนเดิม
  - คง dashboard scan jobs เดิม
  - เพิ่ม signal pipeline follow-up jobs หลัง scan
- อัปเดต `.github/workflows/deploy.yml`
  - หลัง push เข้า `main` แล้ว deploy ไป GCP VM จะ:
    1. `git pull origin main`
    2. `uv sync`
    3. สร้าง `logs/`, `reports/daily-signal-pipeline/`, `state/`
    4. `chmod +x` automation scripts
    5. รัน `bash scripts/setup_gcp_cron.sh`
    6. restart `dashboard.service`
- เพิ่มเอกสาร `GCP_ONLINE_UPDATE.md`

Cron schedule ที่ตั้งไว้:

```text
TH scan:      10:15, 16:15 Mon-Fri
TH pipeline:  10:45, 16:45 Mon-Fri
US scan:      20:30 Mon-Fri
US pipeline:  21:00 Mon-Fri
```

คำสั่งตรวจบน GCP VM หลัง push:

```bash
cd ~/tong_trading
crontab -l
sudo systemctl status dashboard.service
bash scripts/run_gcp_daily_pipeline.sh TH
tail -n 80 logs/daily_signal_pipeline_TH.log
```

หมายเหตุ:

ผมตรวจ live GCP VM จากเครื่องนี้ไม่ได้ เพราะไม่มี SSH credentials / GitHub secrets ใน workspace นี้ ต้องดูผลจริงหลัง push ผ่าน GitHub Actions และ log บน VM
