# Islomiy Hayot — Telegram bot MVP

## Funksiyalar
- `/start` — bosh menyu
- `/prayer` — namozni o‘rganish bo‘yicha boshlang‘ich yo‘l xaritasi
- `/quran` — Qur'on va zikr odatlari
- `/times` — AlAdhan API orqali bugungi namoz vaqtlari
- `/setcity Toshkent` — shaharni sozlash (O‘zbekiston shaharlari uchun)
- `/daily` — kunlik vazifalar, bajarilganini SQLite'da saqlash
- `/reminders_on`, `/reminders_off` — namoz eslatmalarini yoqish/o‘chirish

## Windows / PowerShell
1. BotFather orqali bot yaratib, token oling. Tokenni hech kimga bermang.
2. `.env.example` nusxasini `.env` nomi bilan saqlang va tokenni kiriting.
3. VS Code terminalida:
   ```powershell
   python --version
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python bot.py
   ```
4. Telegram botingizga `/start` yuboring.

Agar PowerShell virtual muhitni faollashtirishni bloklasa:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Muhim eslatmalar
- Namoz vaqtlari tashqi AlAdhan xizmatidan olinadi; mahalliy masjid jadvali bilan solishtiring.
- Hanafiy Asr uchun API'da `school=1` ishlatiladi. Boshqa hisoblash sozlamalari hududga qarab farq qilishi mumkin.
- Eslatmalar bot jarayoni ishlayotgan paytda yuboriladi. Kompyuter o‘chsa yoki bot to‘xtasa, eslatmalar yuborilmaydi.
- Bu boshlang‘ich MVP; diniy matnlar va fiqhiy yo‘riqnomalar ommaga chiqarilishidan oldin ishonchli manbalar/olim bilan tekshirilishi kerak.
- Bu versiya namozning to‘liq fiqh qo‘llanmasi emas va qazo namozlari bo‘yicha hukm bermaydi.
