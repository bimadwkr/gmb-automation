# GMB Automation - Setup Guide

Panduan lengkap menjalankan GMB Automation di perangkat baru.

## 1. Install Python 3.10+

### Windows
```powershell
# Download dari https://www.python.org/downloads/
# Atau gunakan package manager:
winget install Python.Python.3.12
```

Verify:
```powershell
python --version
```

Harus output: `Python 3.10.x` atau lebih tinggi.

## 2. Copy Project

Ambil folder `GMB_Automation` dari perangkat lama ke perangkat baru:
- `C:\Users\<nama-user>\Downloads\GMB_Automation\`

Atau dari cloud (OneDrive, Google Drive, GitHub, etc).

## 3. Install Dependencies

Buka PowerShell di folder project:

```powershell
cd C:\Users\<nama-user>\Downloads\GMB_Automation
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

Tunggu instalasi selesai. Harus ada: selenium, python-dotenv, undetected-chromedriver.

## 4. Siapkan File Konfigurasi

### 4a. File `.env`

Copy dari template:
```powershell
Copy-Item -Path ".env.example" -Destination ".env"
```

Edit `.env` dengan notepad:
```env
DESCRIPTION=Book your stay today and enjoy our special price
PHOTO=photos/GG.jpg
CTA=Book
WA_LINK=https://wa.me/628123456789?text=Halo
DRY_RUN=true
MAX_STORES=1
CHROME_PROFILE=./chrome-profile
```

**Keterangan:**
- `DESCRIPTION` — text postingan (sama untuk semua store)
- `PHOTO` — path ke foto (harus ada di folder `photos/`)
- `CTA` — tombol CTA (Book, Order, Call, etc)
- `WA_LINK` — WhatsApp link (untuk test, bisa diganti per store di `stores.txt`)
- `DRY_RUN=true` — preview saja, tidak publish. Ganti `false` untuk publish.
- `MAX_STORES=1` — proses hanya 1 store. Ganti `0` untuk semua.

### 4b. File `stores.txt`

Buat file `stores.txt` di folder project. Format:
```
STORE_CODE_001|https://wa.me/628123456789?text=Halo
STORE_CODE_002|https://wa.me/628123456790?text=Halo
STORE_CODE_003|https://wa.me/628123456791?text=Halo
```

**Format:** `store_code|wa_link` (pipe-separated)

Setiap baris = 1 store. URL bisa berbeda per store.

### 4c. Foto

Simpan foto ke folder `photos/`:
```
GMB_Automation/
  photos/
    GG.jpg
    YOGA0913.jpg
```

Foto harus sudah ada sebelum run. Ukuran recommended: 1200x900px atau lebih.

## 5. Login Pertama Kali

Run automation pertama kali:
```powershell
py gmb_automation.py
```

Script akan:
1. Tanya mode: ketik `1` (Add Post) atau `2` (Delete Post)
2. Buka Chrome window untuk login Google
3. Manual: login ke akun Google Business Profile
4. Setelah login, kembali ke terminal, tekan Enter

Session tersimpan di `./chrome-profile/`. Run berikutnya skip login step.

## 6. Test (Dry Run)

File `.env` harus set `DRY_RUN=true` dan `MAX_STORES=1`.

Run:
```powershell
py gmb_automation.py
```

Pilih mode `1` (Add Post).

Script akan:
- Cari store code di GMB
- Buat post, isi description, foto, CTA, URL
- **Jangan publish** (karena DRY_RUN=true)
- Update `status.csv` → `DRY_RUN_READY`

Check logs:
```powershell
cat logs/gmb_automation.log
```

Jika berhasil, cek status di `status.csv`:
```
store_code,status,timestamp,error
STORE_CODE_001,DRY_RUN_READY,2026-10-13T...
```

## 7. Publish Satu Store

Edit `.env`:
```env
DRY_RUN=false
MAX_STORES=1
```

Run:
```powershell
py gmb_automation.py
```

Check di `status.csv` → `SUCCESS` atau `FAILED`.

Kalo `SUCCESS`, post sudah live di GMB.

## 8. Publish Multiple Stores

Edit `.env`:
```env
DRY_RUN=false
MAX_STORES=0
```

Atau set ke jumlah tertentu: `MAX_STORES=10`

Run:
```powershell
py gmb_automation.py
```

Script process semua pending stores. Check `status.csv` untuk summary.

## 9. Status Tracking

File `status.csv` tracks status setiap store:

```
store_code,status,timestamp,error
STORE_CODE_001,SUCCESS,2026-10-13T10:30:00.123456
STORE_CODE_002,DRY_RUN_READY,2026-10-13T10:31:00.654321
STORE_CODE_003,FAILED,2026-10-13T10:32:00.987654,Store code not found
```

**Status meanings:**
- `PENDING` — belum diproses
- `PROCESSING` — sedang diproses
- `DRY_RUN_READY` — preview selesai, siap publish
- `SUCCESS` — published
- `FAILED` — error (lihat kolom `error`)

Automation idempotent — hanya process `PENDING` stores. Aman restart.

## 10. Debug

Cek logs:
```powershell
cat logs/gmb_automation.log
```

Cek screenshots error:
```powershell
ls logs/screenshots/
```

Jika button tidak ketemu, screenshot akan save ke `logs/screenshots/{store_code}_publish_button_not_found.png`.

## 11. Troubleshooting

### Chrome tidak buka
- Pastikan port Chrome tidak blocked (jalankan antivirus scan)
- Clear Chrome profile: `rm -r chrome-profile/` (hapus folder), run lagi

### Store code tidak ketemu
- Cek GMB, store code harus sudah ada
- Cek search hasil manual di business.google.com

### Photo not found error
- Cek path di `.env` → `PHOTO=photos/GG.jpg`
- Foto harus ada di `GMB_Automation/photos/GG.jpg`
- Cek extension case-sensitive (`.jpg` vs `.JPG`)

### Login stuck
- Tekan Ctrl+C di terminal, retry
- Clear Chrome profile: `rm -r chrome-profile/`, run lagi

### Button tidak ketemu saat publish
- Set `DRY_RUN=false` untuk benar-benar sampai publish step
- Check debug screenshot di `logs/screenshots/`
- Check log untuk button list yang ditemukan

## 12. Next Runs

Run setiap kali di perangkat:
```powershell
cd C:\Users\<nama-user>\Downloads\GMB_Automation
py gmb_automation.py
```

Tanya mode → pilih → process.

Session login tersimpan, tidak perlu login ulang.

## File Structure

```
GMB_Automation/
├── gmb_automation.py           # Main script
├── requirements.txt            # Dependencies
├── SETUP.md                    # Panduan ini
├── README.md                   # Info teknis
├── .env.example               # Template config
├── .env                       # Config (gitignored)
├── stores.txt                 # Store codes + URLs
├── status.csv                 # Status tracking
├── photos/
│   └── GG.jpg
├── chrome-profile/            # Chrome persistent profile (gitignored)
└── logs/
    ├── gmb_automation.log
    └── screenshots/
        ├── STORE_CODE_001_error.png
        └── ...
```

## Summary

```powershell
# 1. Install Python
winget install Python.Python.3.12

# 2. Copy folder ke perangkat baru

# 3. Install dependencies
cd C:\Users\<user>\Downloads\GMB_Automation
py -m pip install -r requirements.txt

# 4. Setup files
Copy-Item .env.example .env
# Edit .env (notepad)
# Buat stores.txt
# Copy photos ke folder photos/

# 5. Login pertama
py gmb_automation.py
# Pilih mode 1, login manual

# 6. Test dry-run
# DRY_RUN=true di .env
py gmb_automation.py

# 7. Publish
# DRY_RUN=false di .env
py gmb_automation.py
```

Done.
