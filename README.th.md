<br>

<div align="center">

# Truemoney-Voucher (FastAPI)

**REST API สำหรับแลกรับ TrueMoney Gift Voucher** — Python FastAPI, ไม่มี database

![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)
![Python Version](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
[![Live on Vercel](https://img.shields.io/badge/Live-Vercel-000000?logo=vercel&logoColor=white)](https://truemoney-voucher-fastapi.vercel.app)

[English](README.md) - **ไทย**

</div>

---

FastAPI port ของ [เวอร์ชัน Go](https://github.com/ByteInDev/Truemoney-Voucher-Go)
ที่เรียก `gift.truemoney.com` ผ่าน transport ที่จำลองเบราว์เซอร์ Firefox จริง
ในระดับ TLS และ HTTP/2 wire level เพื่อให้คำขอผ่าน Cloudflare bot detection
มีเพียงคำสั่งเดียว: **แลกรับโค้ด (redeem)** เข้ากับเบอร์โทรศัพท์ไทย

## ความสามารถ

| ความสามารถ | รายละเอียด |
| ----------- | ----------- |
| แลกรับโค้ด | `GET`/`POST /truemoney/{code}/{mobile}` — แลกเข้ากับเบอร์โทรศัพท์ (GET กับ POST ให้ผลเหมือนกัน) |
| รองรับลิงก์เต็ม | ใส่ลิงก์ `gift.truemoney.com/campaign/?v=<code>` ได้ด้วย |
| ตรวจสอบ input | โค้ด ≤ 128 ตัวอักษร; เบอร์ไทย 10 หลักขึ้นต้นด้วย `0` |
| ผ่าน Cloudflare | curl_cffi `impersonate="firefox"` (libcurl-impersonate fingerprint TLS/HTTP2) |
| ปลอดภัย | โค้ดถูก mask ใน log, graceful shutdown |

## เริ่มต้นใช้งาน

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m app.main            # ฟังที่ :3000
```

```bash
docker build -t truemoney-voucher -f deployments/Dockerfile .
docker run -d -p 3000:3000 truemoney-voucher
```

ทดสอบว่า service ทำงาน:

```bash
curl localhost:3000/status           # 200 OK (ว่างเปล่า)
curl localhost:3000/                 # ข้อมูลบริการ + รายการ routes
```

## API Reference

### Endpoints

| Method | Path | คำอธิบาย |
| ------ | ---- | -------- |
| `GET` / `POST` | `/truemoney/{code}/{mobile}` | แลกรับโค้ด (redeem) |
| `GET` / `POST` | `/status` | Liveness probe |
| `GET` / `POST` | `/` | ข้อมูลบริการและรายการ routes |

### พารามิเตอร์ใน path

| พารามิเตอร์ | รูปแบบที่รับได้ |
| ----------- | --------------- |
| `code` | raw code (ตัวอักษร/ตัวเลข + `-`/`_` ยาว ≤ 128 ตัว) หรือลิงก์เต็ม `https://gift.truemoney.com/campaign/?v=<code>` ที่ URL-encode แล้ว |
| `mobile` | เบอร์ไทย 10 หลักขึ้นต้นด้วย `0` (เว้นวรรค/ขีดคั่นถูกลบให้อัตโนมัติ) |

### ตัวอย่าง

```bash
# แลกรับด้วย raw code — GET หรือ POST ก็ได้ ผลเหมือนกัน
curl "localhost:3000/truemoney/ABCD1234EFGH/0812345678"
curl -X POST "localhost:3000/truemoney/ABCD1234EFGH/0812345678"

# แลกรับด้วยลิงก์เต็มที่ URL-encode แล้ว (ใช้ --path-as-is เพื่อกัน curl
# แปลง %2F กลับเป็น /)
curl --path-as-is "localhost:3000/truemoney/https%3A%2F%2Fgift.truemoney.com%2Fcampaign%2F%3Fv%3DABCD1234EFGH/0812345678"
```

### รูปแบบ response

JSON ที่ TrueMoney ตอบกลับถูกส่งผ่าน (passthrough) ตามเดิม รวมถึง error envelope
`{"status": {...}}` ส่วน error ของตัว API เองตอบเป็น `code` + `message` เสมอ:

| HTTP status | Body | เมื่อใด |
| ----------- | ---- | ------- |
| `200` | `{"code": 400, "message": "Bad Request"}` | โค้ด/เบอร์ไม่ถูกต้อง |
| `404` | `{"code": 404, "message": "Not Found"}` | path หรือ method ไม่รู้จัก |
| `200` | `{"code": 500, "message": "Internal Server Error"}` | เรียก TrueMoney แล้วพลาด |
| `500` | `{"code": 500, "message": "Internal Server Error"}` | exception ที่ไม่คาดคิด |

### รหัสสถานะจาก TrueMoney

อยู่ใน `status.code` ของ envelope:

| รหัสสถานะ | ความหมาย |
| ---------- | -------- |
| `SUCCESS` | รับเงินสำเร็จ |
| `TARGET_USER_REDEEMED` | คุณรับซองนี้ไปแล้ว |
| `VOUCHER_OUT_OF_STOCK` | มีคนรับไปแล้ว |
| `VOUCHER_EXPIRED` | ซองวอเลทหมดอายุแล้ว |
| `VOUCHER_NOT_FOUND` | ไม่พบซองในระบบ |
| `CANNOT_GET_OWN_VOUCHER` | รับซองตัวเองไม่ได้ |
| `TARGET_USER_NOT_FOUND` | ไม่พบเบอร์ในระบบ |
| `INTERNAL_ERROR` | ไม่พบซองในระบบ หรือ URL ผิด |

## การตั้งค่า

| ตัวแปร env | ค่าเริ่มต้น | รายละเอียด |
| ----------- | ----------- | ----------- |
| `PORT` | `3000` | พอร์ตที่ HTTP server ฟัง (1-65535) |

```bash
PORT=8080 python -m app.main
```

## Build และ Deploy

```bash
make run           # python -m app.main
make install       # pip install -r requirements.txt
make quality       # python -m compileall -q app
make docker-build  # docker build -t truemoney-voucher
make deploy-local  # docker run -d -p 3000:3000 truemoney-voucher
make deploy        # scp + venv + uvicorn ไปยัง remote server
                   # (host/user ฝังใน Makefile - แก้ไขก่อนใช้งาน!)
make vercel-deploy # vercel --prod (serverless)
```

## สถาปัตยกรรม (โดยย่อ)

- **`app/truemoney.py`** — ตรรกะฝั่ง TrueMoney: validation, headers,
  การแลกรับ, การจัดการ response ใช้ session + cookie jar ตัวเดียวร่วมกัน
  (ทำให้ `cf_clearance` อุ่นอยู่เสมอ)
- **`app/main.py`** — FastAPI app factory + lifespan; uvicorn entrypoint
- **`app/middleware.py`** — request logging (โค้ดถูก mask), raw-path routing
  ให้ลิงก์ที่ encode `%2F` ยัง match ได้ (เหมือน Go ServeMux + `r.PathValue`)
- **`app/config.py`** — จัดการ env `PORT`
- **`app/models.py`** — error envelope ร่วม (`code` + `message`)

### ความต่างจากเวอร์ชัน Go

| Go | Python |
| -- | ------ |
| uTLS `HelloFirefox_148` + HTTP/2 framer ที่เขียนเอง | curl_cffi `impersonate="firefox"` (FF 147 fingerprint, libcurl-impersonate) |
| จัดการ gzip/deflate/br เอง | curl_cffi จัดการให้อัตโนมัติ |
| `net/http` mux + method patterns | FastAPI routes |
| `log/slog` structured logs | stdlib `logging` |

## การทดสอบ

```bash
make test            # pytest (validation + HTTP contract ผ่าน TestClient)
```

ชุดเทสต์รันแบบออฟไลน์ — เซสชัน curl_cffi ตัวจริงถูกแทนด้วย stub ไม่มีการส่ง
request ออกนอกเครื่องเลย

## Deploy บน Vercel

FastAPI preset ของ Vercel ตรวจจับ framework จาก `requirements.txt`
อัตโนมัติ และโหลด instance `app` จาก `app/main.py` (Python entrypoint
ที่รองรับ) — **ไม่ต้องใช้ rewrites เลย** ทุก path ถึง FastAPI router แบบ
ไม่เปลี่ยนรูป `vercel.json` ปรับแค่ฟังก์ชันเดียว (`maxDuration: 60`)
เวอร์ชัน Python pin ด้วย `.python-version` (3.12, default ของ Vercel)
curl_cffi เผยแพร่ manylinux wheels จึงติดตั้งและรันบน Lambda ได้

```bash
make vercel-deploy           # = vercel --prod
```

**ข้อควรระวังแบบ serverless:**

- curl_cffi session สร้างแบบ **lazy** — เฉพาะ redeem ครั้งแรก ไม่ใช่ตอน
  bootstrap ทำให้ `/status`, `/` และ validation error ยังเร็วแม้ instance
  เย็น; และอุ่นค้างข้าม function instance ไม่ได้
- Cold Start เพิ่ม latency (การแลกเปลี่ยนแบบเดียวกับอีกสองพอร์ต)

**ประสิทธิภาพบน Free (Hobby) plan:** ฟังก์ชันรันได้แค่ `iad1` (US East)
— RTT ไทย→เวอร์จิเนีย (~200 ms) แก้ไม่ได้บน free plan
`maxDuration: 60` ใช้ได้ วัดด้วย client แบบ keep-alive (เช่น `httpx`)
อย่าใช้ `curl.exe` ใหม่ทุกครั้งเพื่อดูเวลา server จริง

## ข้อควรระวัง

> **ใช้เพื่อการศึกษาหรือในกรณีที่ผู้ให้บริการอนุญาตเท่านั้น**
> การแลกรับโค้ดไม่สามารถย้อนกลับได้ และอยู่ภายใต้ข้อกำหนดการใช้งาน (ToS) ของ TrueMoney
> โค้ดของขวัญมีค่าเทียบเท่าเงินสด — อย่าเปิดเผย log ที่มีโค้ดเต็มสู่สาธารณะ

## การมีส่วนร่วม

ยินดีต้อนรับทุกการมีส่วนร่วมครับ:

1. กรุณาเปิด issue เพื่อหารือก่อนสำหรับการเปลี่ยนแปลงที่มีนัยสำคัญ
2. รักษา `make quality` ให้ผ่านเสมอ
3. ปฏิบัติตาม code style ที่มีอยู่

## สิทธิ์การใช้งาน

ใช้ภายใต้สัญญาอนุญาต [MIT License](./LICENSE) © 2026 ByteInDev