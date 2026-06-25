# คู่มือการติดตั้งและใช้งานบนเครื่องใหม่ (Setup Guide)

คู่มือนี้สำหรับแนะนำขั้นตอนการติดตั้งและรันระบบ **Claude Trading Skills** บนเครื่องคอมพิวเตอร์เครื่องใหม่ โดยละเอียดและเข้าใจง่าย

---

## 📋 สิ่งที่ต้องเตรียมก่อนเริ่มติดตั้ง (Prerequisites)

1. **Python 3.9 ขึ้นไป**
   - ตรวจสอบโดยใช้คำสั่ง: `python --version` หรือ `python3 --version`
   - หากยังไม่มี สามารถดาวน์โหลดได้จาก [python.org](https://www.python.org/downloads/) (แนะนำติ๊กเลือก "Add Python to PATH" ตอนติดตั้งบน Windows)

2. **Astral 'uv' (แนะนำ)**
   - โครงการนี้ใช้ `uv` ในการจัดการ library ต่างๆ ซึ่งมีความเร็วสูงมาก
   - ตัวสคริปต์ `install.py` จะพยายามติดตั้ง `uv` ให้โดยอัตโนมัติหากตรวจไม่พบ
   - หรือท่านสามารถติดตั้งล่วงหน้าได้โดยใช้คำสั่ง:
     - **Windows (PowerShell):** `irm https://astral.sh/uv/install.ps1 | iex`
     - **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 🚀 ขั้นตอนการติดตั้ง (Installation Steps)

### ขั้นตอนที่ 1: แตกไฟล์โปรเจกต์
นำไฟล์ `claude-trading-skills.zip` ที่สร้างได้ ไปแตกไฟล์ (Extract) ลงในโฟลเดอร์ที่ต้องการบนเครื่องใหม่

### ขั้นตอนที่ 2: ตั้งค่า API Keys (.env)
1. คัดลอกไฟล์ `.env.template` แล้วเปลี่ยนชื่อเป็น `.env` ในโฟลเดอร์หลักของโปรเจกต์
2. เปิดไฟล์ `.env` ด้วย Text Editor (เช่น Notepad, VS Code) และใส่ API Key ของท่าน:
   - **FMP_API_KEY:** คีย์จาก Financial Modeling Prep (จำเป็นสำหรับการดึงข้อมูลหุ้นพื้นฐาน)
   - **FINVIZ_API_KEY:** คีย์จาก FINVIZ Elite (ไม่จำเป็น/ถ้ามีจะช่วยดึงข้อมูลสแกนเร็วขึ้นมาก)
   - **ALPACA_API_KEY & SECRET:** คีย์จาก Alpaca Trading (สำหรับระบบบริหารพอร์ตโฟลิโอ)
   - **ALPACA_PAPER:** ตั้งเป็น `true` สำหรับพอร์ตจำลอง (Paper Trade) หรือ `false` สำหรับเทรดจริง

### ขั้นตอนที่ 3: รันสคริปต์ติดตั้งสภาพแวดล้อม
เปิด Terminal หรือ PowerShell เข้ามายังโฟลเดอร์โปรเจกต์ จากนั้นรันคำสั่ง:
```bash
python install.py
```
**สคริปต์นี้จะจัดการให้โดยอัตโนมัติ ดังนี้:**
- ตรวจสอบเวอร์ชัน Python
- ติดตั้ง `uv` (หากยังไม่มีในเครื่อง)
- สร้าง Virtual Environment (`.venv`) และติดตั้ง Library ทั้งหมดที่จำเป็นจาก `pyproject.toml`
- สร้างโฟลเดอร์เก็บข้อมูล ได้แก่ `reports`, `state`, `logs`, และ `scratch`
- สร้างฐานข้อมูล SQLite Cache (`state/market_cache.db`)
- ตรวจสอบความถูกต้องของ API Keys ในระบบ

---

## 🖥️ วิธีการรันระบบ (Running the Dashboard)

โครงการนี้มีหน้าจอ Dashboard สำหรับสรุปข้อมูลการสแกนและผลการวิเคราะห์

### สำหรับ Windows:
- สามารถรันได้ง่ายๆ โดยการดับเบิลคลิกไฟล์ `run_dashboard.bat` ที่อยู่ในโฟลเดอร์หลัก
- หน้าจอคอนโซลจะเปิดและรันเว็บเซิร์ฟเวอร์ (Flask App) บนพอร์ต `5050` ให้ทันที

### สำหรับ macOS / Linux:
เปิด Terminal ในโฟลเดอร์โปรเจกต์แล้วรันคำสั่ง:
```bash
.venv/bin/python dashboard/app.py
```

เมื่อระบบเริ่มทำงานสำเร็จ ให้เปิดเว็บเบราว์เซอร์ไปที่:
👉 **[http://localhost:5050](http://localhost:5050)**

---

## 🛠️ ตัวอย่างการเรียกใช้คำสั่งสแกนด้วยตนเอง (Manual Execution Examples)

เมื่อระบบสร้าง virtual environment เรียบร้อยแล้ว ท่านสามารถรันสคริปต์วิเคราะห์หุ้นต่างๆ ผ่านคอมมานด์ไลน์ได้ ตัวอย่างเช่น:

### 1. การดึงปฏิทินเศรษฐกิจ (Economic Calendar):
```bash
# Windows
.venv\Scripts\python skills/economic-calendar-fetcher/scripts/get_economic_calendar.py

# macOS / Linux
.venv/bin/python skills/economic-calendar-fetcher/scripts/get_economic_calendar.py
```

### 2. การสแกนหาจุดกลับตัวของปันผลเติบโต (Dividend Growth Pullback):
```bash
.venv\Scripts\python skills/dividend-growth-pullback-screener/scripts/screen_dividend_growth.py --max-candidates 40
```

### 3. การตรวจสอบคุณภาพไฟล์ผลลัพธ์ (Data Quality Checker):
```bash
.venv\Scripts\python skills/data-quality-checker/scripts/validate_reports.py
```

*รายงานการสแกนทั้งหมดจะถูกเซฟเก็บไว้โดยอัตโนมัติในโฟลเดอร์ `reports/` ซึ่งท่านสามารถเปิดดูผ่านหน้าเว็บ Dashboard ได้ทันที*
